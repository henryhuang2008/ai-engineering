"""0003-function-calling - the agent loop, by hand, with LangChain + DeepSeek.

Five stages on one model handle:

  1. catalog   two @tool functions -> the JSON schema the model actually reads
  2. one call  bind_tools -> AIMessage.tool_calls -> your code runs the tool ->
               ToolMessage -> one more call. ONE round trip, not an agent.
  3. the loop  a refund needs two rounds (look up, then refund). The loop keeps
               calling until the model stops asking for tools: the agent loop.
  4. the guard a non-refundable ticket returns an error; the model must read it
               and recover instead of claiming success.
  5. the cap   max_iterations on a task that needs two rounds: the production
               guard fires instead of spinning forever.

This lab talks to the live DeepSeek API. Set DEEPSEEK_API_KEY first:

  PowerShell (this session):  $env:DEEPSEEK_API_KEY = "sk-..."
  PowerShell (persist):       setx DEEPSEEK_API_KEY "sk-..."   # reopen the terminal

Get a key at https://platform.deepseek.com/api_keys. No key -> exit 1 with these
instructions, never a guess.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from typing import Any

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.tools import BaseTool, tool

MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-flash")
BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
MAX_ITERATIONS = int(os.getenv("MAX_ITERATIONS", "10"))

SYSTEM = "You are a support agent. Use tools when you need facts. Answer in one or two sentences."
QUESTION_STATUS = "What's the status of ticket T-1001?"
QUESTION_REFUND = "Ticket T-1001 says I was overcharged 20 dollars. Check it and issue the refund."
QUESTION_REFUSED = "Ticket T-1002 was charged 20 dollars. Refund it now."

# --- the world the tools can touch (fixture) --------------------------------

TICKETS = {
    "T-1001": {"status": "open", "plan": "pro", "refundable": True},
    "T-1002": {"status": "closed", "plan": "free", "refundable": False},
}


@tool
def get_ticket_status(ticket_id: str) -> dict:
    """Look up the status and plan of a support ticket by its id, for example T-1001."""
    return TICKETS.get(ticket_id, {"error": "unknown ticket"})


@tool
def issue_refund(ticket_id: str, amount_usd: float) -> dict:
    """Issue a refund for a refundable ticket. Check the status first and only refund amounts the customer was actually charged."""
    ticket = TICKETS.get(ticket_id)
    if ticket is None:
        return {"error": "unknown ticket"}
    if not ticket["refundable"]:
        return {"error": "ticket not refundable"}
    return {"refunded_usd": amount_usd, "ticket": ticket_id}


TOOLS = [get_ticket_status, issue_refund]
REGISTRY: dict[str, BaseTool] = {item.name: item for item in TOOLS}


# --- model wiring -----------------------------------------------------------


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
        # DeepSeek's thinking mode requires every earlier reasoning block to be
        # echoed back on tool turns; this lab is about the loop, so keep it off.
        extra_body={"thinking": {"type": "disabled"}},
    )


# --- the mechanics the lesson is about --------------------------------------


def catalog() -> list[dict[str, Any]]:
    """What the model is allowed to know about each tool. Nothing else is sent."""
    rows: list[dict[str, Any]] = []
    for item in TOOLS:
        schema = item.args_schema.model_json_schema()
        rows.append(
            {
                "name": item.name,
                "description": item.description,
                "required": schema.get("required", []),
                "properties": sorted(schema.get("properties", {})),
            }
        )
    return rows


def execute(call: dict[str, Any]) -> ToolMessage:
    """Run one requested tool call and wrap the result for the model.

    Unknown tools and invalid arguments come back as data, not exceptions: the
    model reads them and corrects itself on the next round.
    """
    name = call["name"]
    arguments = call["args"]
    tool_obj = REGISTRY.get(name)
    if tool_obj is None:
        payload: Any = {"error": f"unknown tool {name}"}
    else:
        try:
            payload = tool_obj.invoke(arguments)
        except Exception as exc:  # noqa: BLE001 - validation errors are data here
            payload = {"error": f"invalid arguments for {name}: {type(exc).__name__}"}
    return ToolMessage(content=json.dumps(payload), tool_call_id=call["id"])


@dataclass
class LoopResult:
    answer: str
    messages: list[BaseMessage]
    iterations: int
    stopped: str  # "answer" or "budget"


def run_loop(model: Any, question: str, *, max_iterations: int = MAX_ITERATIONS) -> LoopResult:
    """The agent loop: call, act, observe, repeat until plain text or the cap."""
    bound = model.bind_tools(TOOLS)
    messages: list[BaseMessage] = [
        SystemMessage(content=SYSTEM),
        HumanMessage(content=question),
    ]
    for step in range(1, max_iterations + 1):
        reply = bound.invoke(messages)
        messages.append(reply)
        if not reply.tool_calls:
            return LoopResult(str(reply.content), messages, step, "answer")
        # Keep the raw AIMessage above: rebuilding it by hand loses fields the
        # provider expects on the next request (ids, reasoning, provider extras).
        for call in reply.tool_calls:
            messages.append(execute(call))
    return LoopResult("", messages, max_iterations, "budget")


# --- output helpers ---------------------------------------------------------


def describe(message: BaseMessage) -> str:
    if message.type == "ai" and message.tool_calls:
        calls = ", ".join(f"{c['name']}({c['args']})" for c in message.tool_calls)
        return f"{message.type:<6} wants {calls}"
    text = message.content if isinstance(message.content, str) else str(message.content)
    return f"{message.type:<6} {text}"


def print_trace(messages: list[BaseMessage], start: int = 1) -> None:
    for index, message in enumerate(messages, start=start):
        print(f"  {index} {describe(message)}")


# --- stages -----------------------------------------------------------------


def stage_catalog() -> None:
    print("== 1. catalog: the only thing the model knows about your code ==")
    for row in catalog():
        print(f"{row['name']}{row['required']}")
        print(f'  description: "{row["description"]}"')
    print("  the model never sees the function bodies - only this catalog")
    print()


def stage_one_call(model: Any) -> None:
    print("== 2. one round trip: the model asks, your code acts =============")
    bound = model.bind_tools(TOOLS)
    messages = [SystemMessage(content=SYSTEM), HumanMessage(content=QUESTION_STATUS)]
    reply = bound.invoke(messages)
    call = reply.tool_calls[0]
    print(f"model requested: {call['name']}({call['args']})")
    print(f"tool_call_id:    {call['id']}")

    result = execute(call)
    print(f"your code ran:   {result.content}")

    thread = messages + [reply, result]
    final = bound.invoke(thread)
    print(f"final answer:    {final.content}")
    print(f"thread length:   {len(thread) + 1} messages (system, human, ai, tool, ai)")
    print()


def stage_loop(model: Any) -> None:
    print("== 3. the loop: two rounds, one answer ===========================")
    result = run_loop(model, QUESTION_REFUND)
    print_trace(result.messages)
    print(f"iterations:      {result.iterations} (stopped: {result.stopped})")
    print(f"answer:          {result.answer}")
    print()


def stage_guard(model: Any) -> None:
    print("== 4. the guard: a refused action is data, not a crash ===========")
    result = run_loop(model, QUESTION_REFUSED)
    print_trace(result.messages)
    print(f"iterations:      {result.iterations} (stopped: {result.stopped})")
    print(f"answer:          {result.answer}")
    print("  the tool said no; the model had to read that and stop pretending")
    print()


def stage_cap(model: Any) -> None:
    print("== 5. the cap: max_iterations stops a spinning loop ==============")
    result = run_loop(model, QUESTION_REFUND, max_iterations=1)
    print(f"iterations:      {result.iterations} (stopped: {result.stopped})")
    print(f"messages kept:   {len(result.messages)} ({result.messages[-1].type} last)")
    print("  in production this is your budget guard, not an error tax")
    print()


def run() -> int:
    try:
        model = build_model()
    except RuntimeError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    print(f"DeepSeek via LangChain -- live model ({MODEL})")
    print()
    stage_catalog()
    stage_one_call(model)
    stage_loop(model)
    stage_guard(model)
    stage_cap(model)
    print("done: 5 stages, live DeepSeek calls")
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
