"""Bounding short-term memory: trim, summarize, or delete.

Three strategies from the article's Part 5, with the two errors in its code
fixed:

* ``trim_history`` keeps the most recent messages under a token budget.
* ``summarize_history`` returns a summary plus ``RemoveMessage`` entries for
  the messages it replaces. It does not append ``[summary] + recent`` to the
  message list: ``add_messages`` preserves existing positions, so that would
  leave the summary at the end and duplicate nothing only by luck.
* ``delete_messages`` deletes explicitly, by id.
"""

from __future__ import annotations

from typing import Any, Sequence

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import (
    BaseMessage,
    RemoveMessage,
    trim_messages,
)
from langchain_core.messages.utils import count_tokens_approximately

SUMMARY_PROMPT = (
    "Summarize the following conversation in 2-3 sentences. Keep names, "
    "decisions, and open questions; drop small talk.\n\n"
)


def trim_history(
    messages: Sequence[BaseMessage],
    max_tokens: int,
) -> list[BaseMessage]:
    """Keep the most recent messages that fit the budget, starting on a human."""
    return trim_messages(
        list(messages),
        strategy="last",
        token_counter=count_tokens_approximately,
        max_tokens=max_tokens,
        start_on="human",
        include_system=True,
    )


def summarize_history(
    messages: Sequence[BaseMessage],
    model: BaseChatModel,
    *,
    keep_last: int = 6,
    threshold_tokens: int = 3000,
) -> tuple[str, list[RemoveMessage]] | None:
    """Summarize everything older than ``keep_last`` messages.

    Returns ``(summary, removals)`` or ``None`` when nothing should change.
    The caller stores ``summary`` in its own state key and applies the removals;
    messages keep their ids, so the recent window is untouched.
    """
    messages = list(messages)
    if count_tokens_approximately(messages) < threshold_tokens:
        return None
    if len(messages) <= keep_last:
        return None

    old = messages[:-keep_last]
    transcript = "\n".join(f"{message.type}: {message.content}" for message in old)
    response = model.invoke([{"role": "user", "content": SUMMARY_PROMPT + transcript}])

    removals = [RemoveMessage(id=message.id) for message in old if message.id]
    return str(response.content), removals


def delete_messages(message_ids: Sequence[str]) -> list[RemoveMessage]:
    """Delete exactly the messages named, in the order given."""
    return [RemoveMessage(id=message_id) for message_id in message_ids]


def memory_updates(
    summary: str | None,
    removals: list[Any] | None = None,
) -> dict[str, Any]:
    """Shape the update a LangGraph node returns for compression."""
    updates: dict[str, Any] = {}
    if summary is not None:
        updates["summary"] = summary
    if removals:
        updates["messages"] = removals
    return updates
