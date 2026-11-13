"""The agent: a LangGraph state machine with a model node and a tools node.

Same shape as the original project, with DeepSeek doing the reasoning:

    START -> assistant -> (tool calls?) -> tools -> assistant -> ... -> END
"""

from __future__ import annotations

import os
from typing import AsyncGenerator, List

from langchain_core.messages import AIMessageChunk, HumanMessage, SystemMessage
from langchain_core.tools import BaseTool
from langchain_deepseek import ChatDeepSeek
from langgraph.checkpoint.memory import InMemorySaver
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

If the user says they are finished, asks to close the program, or says goodbye,
reply with one short goodbye and nothing else.

The active customer_id is {customer_id}. Pass it to every tool call.
"""


def build_model(name: str | None = None) -> ChatDeepSeek:
    """DeepSeek, thinking off: a voice turn needs the first token fast."""
    return ChatDeepSeek(
        model=name or os.environ.get("DEEPSEEK_MODEL", DEFAULT_MODEL),
        temperature=0,
        extra_body={"thinking": {"type": "disabled"}},
    )


class Agent:
    def __init__(
        self,
        name: str = "Luna",
        model: str | None = None,
        tools: List[BaseTool] | None = None,
        system_prompt: str = SYSTEM_PROMPT,
    ) -> None:
        self.name = name
        self.model = model or os.environ.get("DEEPSEEK_MODEL", DEFAULT_MODEL)
        self.tools = tools or []
        self.system_prompt = system_prompt
        self.llm = build_model(self.model).bind_tools(self.tools)
        self.graph = self.build_graph()

    def build_graph(self) -> CompiledStateGraph:
        builder = StateGraph(AgentState)

        def assistant(state: AgentState):
            system_prompt = self.system_prompt.format(
                customer_id=state.customer_id or "(none)",
                expense_categories=CATEGORY_NAMES,
            )
            response = self.llm.invoke([SystemMessage(content=system_prompt)] + state.messages)
            return {"messages": [response]}

        builder.add_node("assistant", assistant)
        builder.add_node("tools", ToolNode(self.tools))
        builder.set_entry_point("assistant")
        builder.add_conditional_edges("assistant", tools_condition)
        builder.add_edge("tools", "assistant")

        return builder.compile(checkpointer=InMemorySaver())


async def stream_graph_response(
    input: dict, graph: CompiledStateGraph, config: dict, show_tools: bool = True
) -> AsyncGenerator[str, None]:
    """Yield the reply as it is generated; tool calls are printed, not spoken."""
    async for mode, chunk in graph.astream(
        input=input, config=config, stream_mode=["messages", "values"]
    ):
        if mode != "messages":
            continue
        message_chunk, _metadata = chunk
        if not isinstance(message_chunk, AIMessageChunk):
            continue
        if message_chunk.tool_call_chunks:
            if show_tools:
                for call in message_chunk.tool_call_chunks:
                    if call.get("name"):
                        yield f"\n  < tool: {call['name']} "
                    if call.get("args"):
                        yield call["args"]
            continue
        if message_chunk.content:
            yield message_chunk.content


def last_ai_text(messages) -> str:
    """The final assistant message as plain text."""
    for message in reversed(messages):
        if getattr(message, "type", "") == "ai" and not getattr(message, "tool_calls", None):
            content = message.content
            if isinstance(content, str):
                return content.strip()
            if isinstance(content, list):
                return " ".join(
                    part.get("text", "") for part in content if isinstance(part, dict)
                ).strip()
    return ""


def intro_message() -> HumanMessage:
    return HumanMessage(
        content=(
            "Briefly introduce yourself in one sentence and ask what expense "
            "they need help with today."
        )
    )
