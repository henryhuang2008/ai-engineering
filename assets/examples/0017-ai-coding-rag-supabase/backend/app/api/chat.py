from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from openai import OpenAIError
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator
from pydantic_ai.exceptions import ModelAPIError, UnexpectedModelBehavior, UsageLimitExceeded
from sqlalchemy.exc import SQLAlchemyError

from app.assistant.outputs import CitationSource, ValidatedAnswer
from app.auth.dependencies import AuthenticatedSession, get_authenticated_session
from app.chat.dependencies import ChatOrchestratorDependency
from app.chat.orchestrator import ChatOrchestrator
from app.chat.streaming import stream_error, stream_progress, stream_validated_answer
from app.database.chats import ChatRepository, get_chat_repository
from app.grounding.validator import GroundingError

router = APIRouter(prefix="/chat", tags=["chat"])
logger = structlog.get_logger(__name__)
MAX_USER_QUESTION_LENGTH = 2_000
CHAT_TURN_TIMEOUT_SECONDS = 120


class CreateThreadRequest(BaseModel):
    title: str = Field(default="New chat", min_length=1, max_length=255)

    @field_validator("title")
    @classmethod
    def strip_title(cls, title: str) -> str:
        title = title.strip()
        if not title:
            raise ValueError("The chat title cannot be blank.")
        return title


class ThreadSummary(BaseModel):
    id: UUID
    title: str
    created_at: datetime
    updated_at: datetime


class ChatMessageResponse(BaseModel):
    id: UUID
    role: Literal["user", "assistant"]
    content: str
    created_at: datetime
    citations: list[CitationSource] = Field(default_factory=list)


class ThreadHistory(ThreadSummary):
    messages: list[ChatMessageResponse]


class TextPart(BaseModel):
    type: Literal["text"]
    text: str = Field(max_length=20_000)


class CitationDataPart(BaseModel):
    type: Literal["data-citation"]
    data: dict[str, object]
    id: str | None = None
    transient: bool | None = None


class UIMessage(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str = Field(min_length=1, max_length=200)
    role: Literal["user", "assistant"]
    parts: list[TextPart | CitationDataPart] = Field(max_length=100)

    @property
    def text(self) -> str:
        return "".join(part.text for part in self.parts if isinstance(part, TextPart))


class ChatStreamRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    thread_id: UUID = Field(alias="threadId")
    messages: list[UIMessage] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def validate_last_message(self) -> ChatStreamRequest:
        if self.messages[-1].role != "user":
            raise ValueError("The final chat message must be from the user.")
        if not self.messages[-1].text.strip():
            raise ValueError("The final user message must contain text.")
        if len(self.messages[-1].text) > MAX_USER_QUESTION_LENGTH:
            raise ValueError("The final user message is too long.")
        return self

    @property
    def last_user_text(self) -> str:
        return self.messages[-1].text.strip()


@router.post("/threads", response_model=ThreadSummary, status_code=status.HTTP_201_CREATED)
async def create_thread(
    request: CreateThreadRequest,
    repository: Annotated[ChatRepository, Depends(get_chat_repository)],
) -> ThreadSummary:
    thread = await repository.create_thread(request.title)
    return ThreadSummary.model_validate(thread)


@router.get("/threads", response_model=list[ThreadSummary])
async def list_threads(
    repository: Annotated[ChatRepository, Depends(get_chat_repository)],
) -> list[ThreadSummary]:
    threads = await repository.list_threads()
    return [ThreadSummary.model_validate(thread) for thread in threads]


@router.get("/threads/{thread_id}", response_model=ThreadHistory)
async def get_thread_history(
    thread_id: UUID,
    repository: Annotated[ChatRepository, Depends(get_chat_repository)],
) -> ThreadHistory:
    thread = await repository.get_thread(thread_id)
    messages = await repository.get_messages(thread_id)
    return ThreadHistory.model_validate({**thread, "messages": messages})


@router.post("/stream")
async def stream_chat(
    request: ChatStreamRequest,
    repository: Annotated[ChatRepository, Depends(get_chat_repository)],
    session: Annotated[AuthenticatedSession, Depends(get_authenticated_session)],
    orchestrator: ChatOrchestratorDependency,
) -> StreamingResponse:
    await repository.get_thread(request.thread_id)
    history = await repository.get_recent_context(request.thread_id)
    return StreamingResponse(
        _stream_chat_turn(
            repository=repository,
            orchestrator=orchestrator,
            session=session,
            thread_id=request.thread_id,
            question=request.last_user_text,
            history=history,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "x-vercel-ai-ui-message-stream": "v1",
            "x-accel-buffering": "no",
        },
    )


async def _stream_chat_turn(
    *,
    repository: ChatRepository,
    orchestrator: ChatOrchestrator,
    session: AuthenticatedSession,
    thread_id: UUID,
    question: str,
    history: list[dict[str, object]],
) -> AsyncIterator[bytes]:
    yield stream_progress("Searching filings and verifying citations...")
    progress_events: asyncio.Queue[bytes | None] = asyncio.Queue()

    def report_progress(message: str) -> None:
        progress_events.put_nowait(stream_progress(message))

    async def prepare_turn() -> tuple[ValidatedAnswer, UUID] | bytes:
        try:
            async with asyncio.timeout(CHAT_TURN_TIMEOUT_SECONDS):
                answer = await orchestrator.complete_turn(
                    user_id=session.user.id,
                    thread_id=thread_id,
                    question=question,
                    history=history,
                    report_progress=report_progress,
                )
                report_progress("Saving the verified conversation...")
                assistant_message_id = await repository.save_turn(
                    thread_id,
                    question,
                    answer.text,
                    answer.citations,
                )
                return answer, assistant_message_id
        except TimeoutError:
            return stream_error(
                "This request timed out while preparing a verified answer. Please try again."
            )
        except (GroundingError, ValidationError):
            return stream_error(
                "The generated answer could not be verified against retrieved passages."
            )
        except (ModelAPIError, UnexpectedModelBehavior, UsageLimitExceeded, OpenAIError) as exc:
            logger.exception("answer_provider_failed", error=str(exc))
            return stream_error("The answer provider failed to complete the request.")
        except SQLAlchemyError:
            return stream_error("The filing retrieval database is unavailable.")
        except HTTPException as exc:
            if exc.status_code == status.HTTP_401_UNAUTHORIZED:
                message = "Your sign-in session has expired. Please sign in again."
            elif exc.status_code == status.HTTP_503_SERVICE_UNAVAILABLE:
                message = "The database is temporarily unavailable. Please try again."
            else:
                message = "The completed answer could not be saved. Please try again."
            return stream_error(message)
        finally:
            progress_events.put_nowait(None)

    turn_task = asyncio.create_task(prepare_turn())
    try:
        while (event := await progress_events.get()) is not None:
            yield event
        result = await turn_task
    finally:
        if not turn_task.done():
            turn_task.cancel()
            await asyncio.gather(turn_task, return_exceptions=True)

    if isinstance(result, bytes):
        yield result
        return

    answer, assistant_message_id = result
    for event in stream_validated_answer(answer, assistant_message_id):
        yield event
