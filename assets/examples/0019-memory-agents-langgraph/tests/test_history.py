from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage, RemoveMessage
from langgraph.graph.message import add_messages

from app.history import (
    delete_messages,
    memory_updates,
    summarize_history,
    trim_history,
)
from tests.support import StubModel


def conversation(count: int):
    messages = []
    for index in range(count):
        cls = HumanMessage if index % 2 == 0 else AIMessage
        messages.append(cls(content=f"message {index}", id=f"m{index}"))
    return messages


def test_trim_keeps_recent_messages_and_starts_on_human() -> None:
    messages = conversation(8)

    trimmed = trim_history(messages, max_tokens=30)

    assert trimmed[-1] is messages[-1]
    assert trimmed[0].type == "human"
    assert len(trimmed) < len(messages)


def test_summarize_is_a_no_op_below_the_threshold() -> None:
    messages = conversation(8)

    result = summarize_history(messages, StubModel(), keep_last=2, threshold_tokens=10_000)

    assert result is None


def test_summarize_replaces_old_messages_with_a_state_key() -> None:
    messages = conversation(8)

    result = summarize_history(messages, StubModel(), keep_last=2, threshold_tokens=1)

    assert result is not None
    summary, removals = result
    assert summary
    assert len(removals) == 6
    assert all(isinstance(removal, RemoveMessage) for removal in removals)

    merged = add_messages(messages, removals)

    # Only the two recent messages remain; the summary lives in its own key.
    assert [message.content for message in merged] == ["message 6", "message 7"]
    assert memory_updates(summary, removals)["summary"] == summary


def test_delete_messages_targets_exact_ids() -> None:
    updates = delete_messages(["m1", "m3"])

    assert [update.id for update in updates] == ["m1", "m3"]
    assert all(isinstance(update, RemoveMessage) for update in updates)
