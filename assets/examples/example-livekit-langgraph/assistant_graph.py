"""The agent: the same LangGraph state machine, driven by LiveKit.

    START -> assistant -> (tool calls?) -> tools -> assistant -> ... -> END

LiveKit calls `stream_reply()` once per user turn and speaks the chunks as they
come out. The graph is compiled without a checkpointer: LiveKit's `ChatContext`
is the conversation history, so the whole thread is passed in on every turn and
there is only one source of truth.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from typing import List

from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage, SystemMessage
from langchain_core.tools import BaseTool
from langchain_deepseek import ChatDeepSeek
from langgraph.graph import StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from categories import CATEGORY_NAMES
from state import AgentState

DEFAULT_MODEL = "deepseek-flash"

SYSTEM_PROMPT = """You are Luna, the company's expense manager. You help an employee
create, update, delete and query their expenses.

Your replies are read aloud by a text-to-speech engine, so write for the ear:
- one or two short sentences
- no markdown, no bullet lists, no tables, no emoji
- say amounts as words when it reads better ("fifteen dollars")
- never read raw JSON or an id aloud; summarise it instead

When creating an expense, put it in exactly one of these categories:
{expense_categories}

If it does not fit any of them, use "other". If you are unsure about the amount
or the item, ask one short question instead of guessing.

The active customer_id is {customer_id}. Pass it to every tool call.
"""


def build_model(name: str | None = None) -> ChatDeepSeek:
    return ChatDeepSeek(
        model=name or os.environ.get("DEEPSEEK_MODEL", DEFAULT_MODEL),
        temperature=0,
        extra_body={"thinking": {"type": "disabled"}},
    )


def build_graph(tools: List[BaseTool]) -> CompiledStateGraph:
    llm = build_model().bind_tools(tools)

    def assistant(state: AgentState):
        system_prompt = SYSTEM_PROMPT.format(
            customer_id=state.customer_id or "(none)",
            expense_categories=CATEGORY_NAMES,
        )
        response = llm.invoke([SystemMessage(content=system_prompt)] + state.messages)
        return {"messages": [response]}

    builder = StateGraph(AgentState)
    builder.add_node("assistant", assistant)
    builder.add_node("tools", ToolNode(tools))
    builder.set_entry_point("assistant")
    builder.add_conditional_edges("assistant", tools_condition)
    builder.add_edge("tools", "assistant")
    return builder.compile()


def to_langchain(chat_ctx) -> list:
    """LiveKit's ChatContext -> LangChain messages, newest last."""
    items = chat_ctx.messages() if callable(chat_ctx.messages) else chat_ctx.messages
    messages = []
    for item in items:
        text = item.text_content
        if not text or not text.strip():
            continue
        if item.role == "user":
            messages.append(HumanMessage(text))
        elif item.role == "assistant":
            messages.append(AIMessage(text))
    return messages


async def stream_reply(graph: CompiledStateGraph, chat_ctx, customer_id: str) -> AsyncIterator[str]:
    """Yield the reply token by token; tool calls are silent, the answer is not."""
    history = to_langchain(chat_ctx)
    if not history:
        return

    state = {"messages": history, "customer_id": customer_id}
    async for chunk, _metadata in graph.astream(state, stream_mode="messages"):
        if not isinstance(chunk, AIMessageChunk):
            continue
        if chunk.tool_call_chunks:
            continue
        text = chunk.content
        if isinstance(text, str) and text:
            yield text
