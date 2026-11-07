from __future__ import annotations

from typing import Any

from langchain_core.messages import AIMessage

from app.config import Settings


class StubModel:
    """Deterministic test double. The app itself always uses a real provider."""

    def __init__(self, facts: list[str] | None = None) -> None:
        self.facts = facts or []
        self.system_prompts: list[str] = []
        self.message_counts: list[int] = []
        self.calls = 0

    def invoke(self, messages: Any, *args: Any, **kwargs: Any) -> AIMessage:
        self.calls += 1
        if isinstance(messages, dict):
            messages = [messages]
        self.message_counts.append(len(messages))

        first = messages[0]
        content = (
            str(first.get("content", ""))
            if isinstance(first, dict)
            else str(first.content)
        )
        if "Extract up to" in content:
            import json

            return AIMessage(content=json.dumps(self.facts))

        system = next((m for m in messages if getattr(m, "type", "") == "system"), None)
        if system is not None:
            self.system_prompts.append(str(system.content))
        last = messages[-1]
        text = last.get("content", "") if isinstance(last, dict) else last.content
        return AIMessage(content=f"reply to: {text}")


def make_settings(**overrides: Any) -> Settings:
    values = dict(
        api_key="test-key",
        base_url="https://example.invalid",
        model="test-model",
        database_url=None,
        embed_model=None,
        embed_base_url=None,
        embed_api_key=None,
        embed_dims=1536,
        max_context_tokens=2000,
        keep_last_messages=6,
        recall_limit=5,
    )
    values.update(overrides)
    return Settings(**values)
