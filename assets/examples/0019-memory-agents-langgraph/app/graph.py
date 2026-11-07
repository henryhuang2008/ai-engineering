"""The combined graph: retrieve from LTM, answer with STM, write new facts.

The article's Part 10 finance agent put these in a global ``store`` and two
nodes that each re-read the same profile. This version keeps one retrieval
node, declares every state key it writes, and compiles with both the
checkpointer and the store.
"""

from __future__ import annotations

from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.store.memory import InMemoryStore

from app.config import Settings
from app.history import summarize_history, trim_history
from app.ltm import extract_facts, recall_facts, remember_facts


class MemoryState(MessagesState):
    """Messages plus the keys the memory nodes read and write."""

    user_id: str
    memory_context: str
    summary: str


SYSTEM_TEMPLATE = """You are a helpful assistant with access to the user's long-term memory.

Known facts about this user:
{context}

Use them when relevant. If they conflict with what the user says now, trust the
new statement and say so briefly."""


def last_human_message(state: MemoryState) -> str:
    for message in reversed(state["messages"]):
        if message.type == "human":
            return str(message.content)
    return ""


def create_memory_graph(
    model: BaseChatModel,
    store: InMemoryStore,
    *,
    settings: Settings,
    checkpointer: BaseCheckpointSaver | None = None,
    semantic: bool = False,
) -> Any:
    def compress(state: MemoryState) -> dict:
        result = summarize_history(
            state["messages"],
            model,
            keep_last=settings.keep_last_messages,
            threshold_tokens=settings.max_context_tokens * 2,
        )
        if result is None:
            return {}
        summary, removals = result
        return {"summary": summary, "messages": removals}

    def retrieve(state: MemoryState) -> dict:
        facts = recall_facts(
            store,
            state["user_id"],
            query=last_human_message(state) or None,
            semantic=semantic,
            limit=settings.recall_limit,
        )
        context = "\n".join(f"- {fact}" for fact in facts) if facts else "(nothing yet)"
        return {"memory_context": context}

    def agent(state: MemoryState) -> dict:
        # The model sees a trimmed window; the checkpointer keeps the full thread.
        visible = trim_history(state["messages"], settings.max_context_tokens)
        system_content = SYSTEM_TEMPLATE.format(
            context=state.get("memory_context", "(nothing yet)")
        )
        if state.get("summary"):
            system_content += (
                "\n\nSummary of the earlier conversation:\n" + state["summary"]
            )
        response = model.invoke([SystemMessage(content=system_content), *visible])
        return {"messages": [response]}

    def extract(state: MemoryState, config: RunnableConfig) -> dict:
        text = last_human_message(state)
        if not text:
            return {}
        thread_id = str(config.get("configurable", {}).get("thread_id", "unknown"))
        facts = extract_facts(model, text)
        if facts:
            remember_facts(store, state["user_id"], facts, thread_id=thread_id)
        return {}

    builder = StateGraph(MemoryState)
    builder.add_node("compress", compress)
    builder.add_node("retrieve", retrieve)
    builder.add_node("agent", agent)
    builder.add_node("extract", extract)
    builder.add_edge(START, "compress")
    builder.add_edge("compress", "retrieve")
    builder.add_edge("retrieve", "agent")
    builder.add_edge("agent", "extract")
    builder.add_edge("extract", END)
    return builder.compile(checkpointer=checkpointer or InMemorySaver(), store=store)


def run_turn(graph: Any, user_id: str, thread_id: str, text: str) -> str:
    result = graph.invoke(
        {
            "messages": [HumanMessage(content=text)],
            "user_id": user_id,
            "memory_context": "",
            "summary": "",
        },
        {"configurable": {"thread_id": thread_id}},
    )
    return str(result["messages"][-1].content)
