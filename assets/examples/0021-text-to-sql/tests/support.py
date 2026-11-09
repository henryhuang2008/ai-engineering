from __future__ import annotations

from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import Field

from app.config import Settings


class ScriptedModel(BaseChatModel):
    """Deterministic test double. The app itself always uses a real provider."""

    responses: list[AIMessage] = Field(default_factory=list)
    seen: list[list[Any]] = Field(default_factory=list)

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def bind_tools(self, tools: Any, **kwargs: Any) -> "ScriptedModel":  # noqa: ARG002
        return self

    def _generate(
        self,
        messages: list[Any],
        stop: list[str] | None = None,  # noqa: ARG002
        run_manager: Any = None,  # noqa: ARG002
        **kwargs: Any,  # noqa: ARG002
    ) -> ChatResult:
        self.seen.append(list(messages))
        if not self.responses:
            return ChatResult(
                generations=[
                    ChatGeneration(message=AIMessage(content="no scripted reply"))
                ]
            )
        return ChatResult(generations=[ChatGeneration(message=self.responses.pop(0))])


def tool_call(sql: str, call_id: str = "call-1") -> AIMessage:
    return AIMessage(
        content="",
        tool_calls=[
            {
                "name": "run_query",
                "args": {"query": sql},
                "id": call_id,
                "type": "tool_call",
            }
        ],
    )


def make_settings(db_path: Any, *, max_attempts: int = 3) -> Settings:
    return Settings(
        api_key="test-key",
        base_url="https://example.invalid",
        model="test-model",
        db_path=db_path,
        max_attempts=max_attempts,
    )
