"""0002-first-llm-api - chat, streaming, tools, and structured output with LangChain.

One model handle, four stages:

  1. chat       SystemMessage + HumanMessage -> AIMessage, and a second turn where
                the whole history is re-sent
  2. streaming  model.stream() -> AIMessageChunk pieces; join them and you have
                exactly what invoke() returned
  3. tools      bind_tools() -> AIMessage.tool_calls -> your code runs the tool ->
                ToolMessage -> one more call. ONE round trip, not an agent loop.
  4. structured model.with_structured_output(SupportTicket) -> a validated pydantic
                instance, via DeepSeek's tool calling

This lab talks to the live DeepSeek API. Set DEEPSEEK_API_KEY first:

  PowerShell (this session):  $env:DEEPSEEK_API_KEY = "sk-..."
  PowerShell (persist):       setx DEEPSEEK_API_KEY "sk-..."   # reopen the terminal

Get a key at https://platform.deepseek.com/api_keys. No key -> exit 1 with these
instructions, never a guess.
"""

from __future__ import annotations

import os
import sys
from typing import Any, Literal

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.tools import BaseTool, tool
from pydantic import BaseModel, Field

MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-flash")
BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")

SYSTEM = "You are a terse support assistant. Answer in one sentence."
QUESTION_1 = "My invoice charged me twice. What should I do?"
QUESTION_2 = "And how long does the refund take?"
QUESTION_3 = "Where is order A-1042?"
TICKET_TEXT = "My invoice charged me twice for order A-1042. Fix it now."

# --- the world the tool can touch (fixture) --------------------------------

ORDERS = {
    "A-1042": "shipped from the Sydney warehouse, arriving Thursday",
    "A-2001": "processing, ships Friday",
}


@tool
def get_order_status(order_id: str) -> str:
    """Look up an order's fulfilment status by its id, for example A-1042."""
    if order_id not in ORDERS:
        return f"no order found for {order_id}"
    return ORDERS[order_id]


class SupportTicket(BaseModel):
    """A support ticket, classified into typed fields."""

    category: Literal["billing", "bug", "question"] = Field(
        description="billing, bug, or question"
    )
    urgency: int = Field(ge=1, le=5, description="1-5, 5 being most urgent")
    summary: str = Field(description="one sentence, no invented facts")
    order_id: str | None = Field(default=None, description="order id if mentioned")


# --- model wiring ----------------------------------------------------------


def missing_key_message() -> str:
    return (
        "DEEPSEEK_API_KEY is not set.\n"
        '  PowerShell (this session):  $env:DEEPSEEK_API_KEY = "sk-..."\n'
        '  PowerShell (persist):       setx DEEPSEEK_API_KEY "sk-..."   # reopen terminal\n'
        "  Get a key:                  https://platform.deepseek.com/api_keys"
    )


def build_model() -> Any:
    """Return a live ChatDeepSeek handle, or explain exactly what is missing."""
    if not os.getenv("DEEPSEEK_API_KEY"):
        raise RuntimeError(missing_key_message())

    from langchain_deepseek import ChatDeepSeek

    return ChatDeepSeek(
        model=os.getenv("DEEPSEEK_MODEL", MODEL),
        api_key=os.getenv("DEEPSEEK_API_KEY"),
        api_base=os.getenv("DEEPSEEK_BASE_URL", BASE_URL),
        temperature=0,
        max_retries=2,
        timeout=60,
        # DeepSeek thinks by default; this lab is about message plumbing,
        # so keep replies short and cheap. Delete this to watch it reason.
        extra_body={"thinking": {"type": "disabled"}},
    )


# --- output helpers --------------------------------------------------------


def describe(message: BaseMessage) -> str:
    text = message.content if isinstance(message.content, str) else str(message.content)
    return f"{message.type:<6} {text}"


def print_trace(messages: list[BaseMessage]) -> None:
    for index, message in enumerate(messages, start=1):
        print(f"  {index} {describe(message)}")


def describe_tool(tool_obj: BaseTool) -> str:
    schema = tool_obj.args_schema
    if hasattr(schema, "model_json_schema"):
        schema = schema.model_json_schema()
    required = schema.get("required", []) if isinstance(schema, dict) else []
    return f"{tool_obj.name}{required}"


# --- stages ----------------------------------------------------------------


def stage_chat(model: Any) -> list[BaseMessage]:
    print("== 1. chat: a list of messages ===========================")
    messages = [SystemMessage(content=SYSTEM), HumanMessage(content=QUESTION_1)]
    print(f"turn 1: {len(messages)} messages sent")
    print_trace(messages)
    reply = model.invoke(messages)
    print(f"reply 1: {reply.content}")

    messages = messages + [reply, HumanMessage(content=QUESTION_2)]
    print(f"turn 2: {len(messages)} messages sent (the whole history is re-sent)")
    print_trace(messages)
    reply = model.invoke(messages)
    print(f"reply 2: {reply.content}")
    print()
    return messages


def stage_stream(model: Any) -> None:
    print("== 2. streaming: the same reply, in pieces ===============")
    messages = [SystemMessage(content=SYSTEM), HumanMessage(content=QUESTION_1)]
    baseline = model.invoke(messages).content
    chunks = list(model.stream(messages))
    pieces = [str(chunk.content) for chunk in chunks if chunk.content]
    joined = "".join(pieces)
    print(f"chunks: {len(chunks)} ({len(pieces)} with text, {len(chunks) - len(pieces)} empty)")
    print(f"joined == invoke(): {joined == baseline}")
    print(f'first chunk: "{pieces[0]}"')
    print(f'last text chunk: "{pieces[-1]}"')
    print()


def stage_tools(model: Any) -> None:
    print("== 3. tools: one round trip, not an agent ================")
    print(f"tool schema: {describe_tool(get_order_status)}")
    bound = model.bind_tools([get_order_status])
    messages = [SystemMessage(content=SYSTEM), HumanMessage(content=QUESTION_3)]
    ai = bound.invoke(messages)
    call = ai.tool_calls[0]
    print(f"model requested: {call['name']}({call['args']})")

    result = get_order_status.invoke(call["args"])
    print(f"your code ran:   {result}")

    tool_message = ToolMessage(content=result, tool_call_id=call["id"])
    print(f"tool_call_id:    {call['id']} (matches the request)")

    thread = messages + [ai, tool_message]
    final = bound.invoke(thread)
    thread = thread + [final]
    print(f"final:           {final.content}")
    print(f"thread length:   {len(thread)} messages")
    print()


def stage_structured(model: Any) -> None:
    print("== 4. structured output: natural language in, pydantic ==")
    classifier = model.with_structured_output(SupportTicket, method="function_calling")
    ticket = classifier.invoke(
        [
            SystemMessage(content="Classify the support ticket. Extract the order id."),
            HumanMessage(content=TICKET_TEXT),
        ]
    )
    assert isinstance(ticket, SupportTicket)
    print(f"result: category={ticket.category!r} urgency={ticket.urgency} "
          f"order_id={ticket.order_id!r}")
    print(f"type:   {type(ticket).__name__} (validated instance)")
    print()


def run() -> int:
    try:
        model = build_model()
    except RuntimeError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    print(f"DeepSeek via LangChain -- live model ({MODEL})")
    print()
    stage_chat(model)
    stage_stream(model)
    stage_tools(model)
    stage_structured(model)
    print("done: 4 stages, live DeepSeek calls")
    return 0


def main() -> int:
    try:
        return run()
    except Exception as error:  # noqa: BLE001 - surface the provider error, keep exit codes
        print(f"error: {type(error).__name__}: {error}", file=sys.stderr)
        print(
            "check DEEPSEEK_API_KEY, account balance, and network access.",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
