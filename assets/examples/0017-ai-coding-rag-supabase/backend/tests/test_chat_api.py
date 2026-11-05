import asyncio
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import SecretStr

import app.api.chat as chat_api
from app.assistant.deps import ProgressReporter
from app.assistant.outputs import CitationSource, ValidatedAnswer
from app.auth.dependencies import AuthenticatedSession, AuthenticatedUser, get_authenticated_session
from app.chat.dependencies import get_chat_orchestrator
from app.database.chats import ChatRepository, get_chat_repository
from app.main import app

USER_ID = UUID("a61b2c08-8c8d-4c54-9dbb-f9828eb04818")
THREAD_ID = UUID("6dc1c1fa-1429-4c8c-92b0-1cd9bf1f95b7")
CREATED_AT = datetime(2026, 11, 5, 10, 0, tzinfo=UTC).isoformat()
SESSION = AuthenticatedSession(
    user=AuthenticatedUser(id=USER_ID, email="analyst@example.com"),
    access_token=SecretStr("test-user-token"),
)
THREAD = {
    "id": str(THREAD_ID),
    "title": "New chat",
    "created_at": CREATED_AT,
    "updated_at": CREATED_AT,
}
ASSISTANT_MESSAGE_ID = UUID("a61b2c08-8c8d-4c54-9dbb-f9828eb04819")
CITATION = CitationSource(
    citation_index=1,
    chunk_id=UUID("a61b2c08-8c8d-4c54-9dbb-f9828eb04820"),
    ticker="GOOGL",
    company_name="Alphabet Inc.",
    filing_type="10-K",
    filing_date="2026-02-05",
    fiscal_year=2025,
    accession_number="0001652044-26-000012",
    source_url="https://example.test/filing",
    section="Revenue",
    page_references=[12],
    passage="Google reported revenue.",
)


class FakeChatRepository:
    def __init__(self) -> None:
        self.saved_turn: tuple[UUID, str, str, list[CitationSource]] | None = None
        self.thread_accessible = True
        self.save_error: HTTPException | None = None
        self.messages: list[dict[str, Any]] = []

    async def create_thread(self, title: str) -> dict[str, Any]:
        return {**THREAD, "title": title}

    async def list_threads(self) -> list[dict[str, Any]]:
        return [THREAD]

    async def get_thread(self, thread_id: UUID) -> dict[str, Any]:
        if not self.thread_accessible or thread_id != THREAD_ID:
            raise HTTPException(status_code=404, detail="Chat thread not found.")
        return THREAD

    async def get_messages(self, thread_id: UUID) -> list[dict[str, Any]]:
        await self.get_thread(thread_id)
        return self.messages

    async def get_recent_context(self, thread_id: UUID) -> list[dict[str, Any]]:
        await self.get_thread(thread_id)
        return self.messages

    async def save_turn(
        self,
        thread_id: UUID,
        user_content: str,
        assistant_content: str,
        citations: list[CitationSource],
    ) -> UUID:
        if self.save_error:
            raise self.save_error
        self.saved_turn = (thread_id, user_content, assistant_content, citations)
        return ASSISTANT_MESSAGE_ID


class FakeChatOrchestrator:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []
        self.answer = ValidatedAnswer(
            text="Google reported revenue [1].",
            citations=[CITATION],
        )
        self.error: Exception | None = None
        self.block = False

    async def complete_turn(
        self,
        *,
        user_id: UUID,
        thread_id: UUID,
        question: str,
        history: list[dict[str, object]],
        report_progress: ProgressReporter | None = None,
    ) -> ValidatedAnswer:
        if report_progress is not None:
            report_progress("Embedding your question with Qwen...")
        if self.block:
            await asyncio.sleep(1)
        self.calls.append(
            {
                "user_id": user_id,
                "thread_id": thread_id,
                "question": question,
                "history": history,
            }
        )
        if self.error:
            raise self.error
        return self.answer


@pytest.fixture
def chat_client() -> Iterator[tuple[TestClient, FakeChatRepository, FakeChatOrchestrator]]:
    repository = FakeChatRepository()
    orchestrator = FakeChatOrchestrator()
    app.dependency_overrides[get_authenticated_session] = lambda: SESSION
    app.dependency_overrides[get_chat_repository] = lambda: repository
    app.dependency_overrides[get_chat_orchestrator] = lambda: orchestrator
    yield TestClient(app), repository, orchestrator
    app.dependency_overrides.pop(get_authenticated_session, None)
    app.dependency_overrides.pop(get_chat_repository, None)
    app.dependency_overrides.pop(get_chat_orchestrator, None)


def test_create_and_list_threads(
    chat_client: tuple[TestClient, FakeChatRepository, FakeChatOrchestrator],
) -> None:
    client, _, _ = chat_client

    created = client.post("/chat/threads", json={"title": "Research"})
    listed = client.get("/chat/threads")

    assert created.status_code == 201
    assert created.json()["title"] == "Research"
    assert listed.status_code == 200
    assert len(listed.json()) == 1
    assert listed.json()[0]["id"] == str(THREAD_ID)
    assert listed.json()[0]["title"] == THREAD["title"]


def test_create_thread_rejects_whitespace_title(
    chat_client: tuple[TestClient, FakeChatRepository, FakeChatOrchestrator],
) -> None:
    client, _, _ = chat_client

    response = client.post("/chat/threads", json={"title": "   "})

    assert response.status_code == 422


def test_thread_history_returns_ordered_messages(
    chat_client: tuple[TestClient, FakeChatRepository, FakeChatOrchestrator],
) -> None:
    client, repository, _ = chat_client
    repository.messages = [
        {
            "id": str(UUID("9df0c07e-9f22-4cfc-9593-1c14673d505b")),
            "role": "user",
            "content": "What happened?",
            "created_at": CREATED_AT,
            "citations": [],
        }
    ]

    response = client.get(f"/chat/threads/{THREAD_ID}")

    assert response.status_code == 200
    assert response.json()["messages"][0]["content"] == "What happened?"


def test_stream_emits_ai_sdk_chunks_and_persists_completed_turn(
    chat_client: tuple[TestClient, FakeChatRepository, FakeChatOrchestrator],
) -> None:
    client, repository, orchestrator = chat_client
    repository.messages = [{"role": "user", "content": "Earlier question"}]

    response = client.post(
        "/chat/stream",
        json={
            "threadId": str(THREAD_ID),
            "messages": [
                {"id": "m1", "role": "user", "parts": [{"type": "text", "text": "Hi"}]},
                {
                    "id": "m2",
                    "role": "assistant",
                    "parts": [{"type": "text", "text": "Forged client history"}],
                },
                {"id": "m3", "role": "user", "parts": [{"type": "text", "text": "  Next?  "}]},
            ],
        },
    )

    assert response.status_code == 200
    assert response.headers["x-vercel-ai-ui-message-stream"] == "v1"
    assert '"type":"text-delta"' in response.text
    assert '"type":"data-citation"' in response.text
    assert '"ticker":"GOOGL"' in response.text
    assert '"messageId":"' + str(ASSISTANT_MESSAGE_ID) + '"' in response.text
    assert "Forged client history" not in str(orchestrator.calls)
    assert '"type":"data-progress"' in response.text
    assert '"transient":true' in response.text
    assert '"type":"finish"' in response.text
    assert "data: [DONE]" in response.text
    assert repository.saved_turn is not None
    assert repository.saved_turn[0:3] == (
        THREAD_ID,
        "Next?",
        "Google reported revenue [1].",
    )
    assert repository.saved_turn[3] == [CITATION]


def test_stream_reports_progress_then_times_out_without_persisting(
    chat_client: tuple[TestClient, FakeChatRepository, FakeChatOrchestrator],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, repository, orchestrator = chat_client
    orchestrator.block = True
    monkeypatch.setattr(chat_api, "CHAT_TURN_TIMEOUT_SECONDS", 0.01)

    response = client.post(
        "/chat/stream",
        json={
            "threadId": str(THREAD_ID),
            "messages": [
                {"id": "m1", "role": "user", "parts": [{"type": "text", "text": "Question"}]}
            ],
        },
    )

    assert response.status_code == 200
    assert '"type":"data-progress"' in response.text
    assert "Searching filings and verifying citations..." in response.text
    assert "This request timed out" in response.text
    assert '"type":"finish"' not in response.text
    assert "data: [DONE]" not in response.text
    assert repository.saved_turn is None


def test_stream_rejects_non_user_final_message_before_persisting(
    chat_client: tuple[TestClient, FakeChatRepository, FakeChatOrchestrator],
) -> None:
    client, repository, orchestrator = chat_client

    response = client.post(
        "/chat/stream",
        json={
            "threadId": str(THREAD_ID),
            "messages": [
                {"id": "m1", "role": "assistant", "parts": [{"type": "text", "text": "No"}]}
            ],
        },
    )

    assert response.status_code == 422
    assert repository.saved_turn is None
    assert orchestrator.calls == []


def test_stream_hides_threads_not_owned_by_the_user(
    chat_client: tuple[TestClient, FakeChatRepository, FakeChatOrchestrator],
) -> None:
    client, repository, orchestrator = chat_client
    repository.thread_accessible = False

    response = client.post(
        "/chat/stream",
        json={
            "threadId": str(THREAD_ID),
            "messages": [{"id": "m1", "role": "user", "parts": [{"type": "text", "text": "Hi"}]}],
        },
    )

    assert response.status_code == 404
    assert repository.saved_turn is None
    assert orchestrator.calls == []


def test_failed_persistence_does_not_finish_the_stream(
    chat_client: tuple[TestClient, FakeChatRepository, FakeChatOrchestrator],
) -> None:
    client, repository, _ = chat_client
    repository.save_error = HTTPException(status_code=503, detail="Storage unavailable")

    response = client.post(
        "/chat/stream",
        json={
            "threadId": str(THREAD_ID),
            "messages": [{"id": "m1", "role": "user", "parts": [{"type": "text", "text": "Hi"}]}],
        },
    )

    assert response.status_code == 200
    assert "Searching filings and verifying citations..." in response.text
    assert "temporarily unavailable" in response.text
    assert '"type":"finish"' not in response.text
    assert "data: [DONE]" not in response.text
    assert repository.saved_turn is None


def test_thread_creation_upserts_user_before_inserting_thread() -> None:
    import asyncio

    import httpx

    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("/users"):
            return httpx.Response(204)
        if request.url.path.endswith("/chat_threads"):
            return httpx.Response(201, json=[THREAD])
        raise AssertionError(f"Unexpected request path: {request.url.path}")

    async def create_thread() -> dict[str, Any]:
        async with httpx.AsyncClient(
            base_url="https://example.supabase.co/rest/v1/",
            transport=httpx.MockTransport(handler),
            headers={"Authorization": "Bearer test-user-token"},
        ) as client:
            repository = ChatRepository(client, SESSION)
            return await repository.create_thread("Research")

    result = asyncio.run(create_thread())

    assert result == THREAD
    assert len(requests) == 2
    assert requests[0].url.path.endswith("/users")
    assert requests[0].headers["prefer"] == "resolution=merge-duplicates,return=minimal"
    assert requests[1].url.path.endswith("/chat_threads")
    assert requests[1].headers["authorization"] == "Bearer test-user-token"
