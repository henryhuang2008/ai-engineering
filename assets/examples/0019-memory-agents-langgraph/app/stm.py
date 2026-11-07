"""Short-term memory: thread-scoped state behind a checkpointer.

This is the article's Part 2-4 shape: a one-node graph over MessagesState,
compiled with a checkpointer. The different thread_ids get different states;
the same thread_id reloads its history.
"""

from __future__ import annotations

from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, MessagesState, StateGraph


def build_stm_graph(
    model: BaseChatModel,
    checkpointer: BaseCheckpointSaver | None = None,
) -> Any:
    """A message-only graph whose only memory is the checkpointer."""

    def agent(state: MessagesState) -> dict:
        response = model.invoke(state["messages"])
        return {"messages": [response]}

    builder = StateGraph(MessagesState)
    builder.add_node("agent", agent)
    builder.add_edge(START, "agent")
    builder.add_edge("agent", END)
    return builder.compile(checkpointer=checkpointer or InMemorySaver())


def thread_config(thread_id: str) -> dict[str, dict[str, str]]:
    return {"configurable": {"thread_id": thread_id}}


def send(graph: Any, thread_id: str, text: str) -> str:
    """Send one turn on a thread and return the assistant's reply."""
    result = graph.invoke(
        {"messages": [HumanMessage(content=text)]},
        thread_config(thread_id),
    )
    return str(result["messages"][-1].content)


def history(graph: Any, thread_id: str) -> list[Any]:
    """Read the stored messages for a thread without invoking the model."""
    snapshot = graph.get_state(thread_config(thread_id))
    return list(snapshot.values.get("messages", []))
