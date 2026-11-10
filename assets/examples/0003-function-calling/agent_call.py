"""0003-function-calling - the same tools under a framework-owned loop.

The hand-written lab (function_calling_lab.py) owns the for-loop. This script
hands the loop to LangChain's `create_agent`, which compiles it into a LangGraph
graph. Same tools, same model, same wire protocol - a different owner.

Five stages:

  1. graph    create_agent(model, TOOLS) -> a compiled graph: model <-> tools
  2. one call ONE invoke() runs the whole refund task; count the turns it took
  3. stream   stream_mode="updates" shows the model/tools steps you wrote by hand
  4. approval HumanInTheLoopMiddleware pauses before issue_refund; approve/reject
  5. budget   recursion_limit raises GraphRecursionError instead of returning a
              stop reason

This script talks to the live DeepSeek API. Set DEEPSEEK_API_KEY first:

  PowerShell (this session):  $env:DEEPSEEK_API_KEY = "sk-..."
  PowerShell (persist):       setx DEEPSEEK_API_KEY "sk-..."   # reopen the terminal

Get a key at https://platform.deepseek.com/api_keys. No key -> exit 1 with these
instructions, never a guess.
"""

from __future__ import annotations

import sys
from typing import Any

from langchain.agents import create_agent
from langchain.agents.middleware import HumanInTheLoopMiddleware
from langchain_core.messages import BaseMessage, HumanMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.errors import GraphRecursionError
from langgraph.types import Command

from function_calling_lab import (
    MODEL,
    QUESTION_REFUND,
    QUESTION_STATUS,
    SYSTEM,
    TOOLS,
    build_model,
    describe,
)


# --- the framework wiring ---------------------------------------------------


def build_agent(model: Any, *, require_approval: bool = False):
    """Compile the model + tools into an agent graph.

    Approval needs a checkpointer: the graph saves its state at the interrupt,
    and resumes from that saved state when a human answers. Without a
    checkpointer there is nothing to resume.
    """
    middleware = []
    checkpointer = None
    if require_approval:
        middleware = [HumanInTheLoopMiddleware(interrupt_on={"issue_refund": True})]
        checkpointer = InMemorySaver()

    return create_agent(
        model,
        TOOLS,
        system_prompt=SYSTEM,
        middleware=middleware,
        checkpointer=checkpointer,
    )


def count_turns(messages: list[BaseMessage]) -> tuple[int, int]:
    """How many model turns and tool results one invoke() produced."""
    model_turns = sum(1 for message in messages if message.type == "ai")
    tool_results = sum(1 for message in messages if message.type == "tool")
    return model_turns, tool_results


def pending_actions(result: dict[str, Any]) -> list[dict[str, Any]]:
    """The tool calls the graph paused on, if any."""
    interrupts = result.get("__interrupt__") or []
    if not interrupts:
        return []
    return list(interrupts[0].value.get("action_requests", []))


# --- stages -----------------------------------------------------------------


def stage_graph(agent: Any) -> None:
    print("== 1. graph: create_agent compiles the loop you wrote ============")
    graph = agent.get_graph()
    print("nodes:  " + ", ".join(graph.nodes))
    for edge in graph.edges:
        if edge.source in {"__start__", "__end__"} or edge.target in {"__start__", "__end__"}:
            continue
        marker = " (conditional)" if edge.conditional else ""
        print(f"edge:   {edge.source} -> {edge.target}{marker}")
    print("  the framework did not remove the loop; it drew it as a graph")
    print()


def stage_one_call(agent: Any) -> None:
    print("== 2. one invoke(): the framework runs the whole loop ============")
    result = agent.invoke({"messages": [HumanMessage(QUESTION_REFUND)]})
    messages = result["messages"]
    for index, message in enumerate(messages, start=1):
        print(f"  {index} {describe(message)}")
    model_turns, tool_results = count_turns(messages)
    print(f"messages:        {len(messages)}")
    print(f"model turns:     {model_turns}; tool results: {tool_results}")
    print(f"answer:          {messages[-1].content}")
    print("  one call, three model turns - the same refund task as run_loop")
    print()


def stage_stream(agent: Any) -> None:
    print("== 3. stream: watch the loop the framework hides =================")
    step = 0
    for update in agent.stream(
        {"messages": [HumanMessage(QUESTION_STATUS)]},
        stream_mode="updates",
    ):
        for node, payload in update.items():
            if not isinstance(payload, dict):
                continue
            for message in payload.get("messages", []):
                step += 1
                print(f"  {step} {node:<6} {describe(message)}")
    print("  each chunk is one graph step: model -> tools -> model")
    print()


def stage_approval(model: Any) -> None:
    print("== 4. approval: the framework pauses before a side effect ========")
    agent = build_agent(model, require_approval=True)

    config = {"configurable": {"thread_id": "lesson-3-approve"}}
    paused = agent.invoke({"messages": [HumanMessage(QUESTION_REFUND)]}, config)
    actions = pending_actions(paused)
    action = actions[0]
    print(f"paused before:   {action['name']}({action['args']})")
    print(f"pending actions: {len(actions)}; the refund has not run")

    approved = agent.invoke(
        Command(resume={"decisions": [{"type": "approve"}]}),
        config,
    )
    print(f"approved ->      {approved['messages'][-1].content}")

    config = {"configurable": {"thread_id": "lesson-3-reject"}}
    agent.invoke({"messages": [HumanMessage(QUESTION_REFUND)]}, config)
    rejected = agent.invoke(
        Command(resume={"decisions": [{"type": "reject", "message": "No refunds today."}]}),
        config,
    )
    print(f"rejected ->      {rejected['messages'][-1].content}")
    print("  same tool, same model: the decision still belongs to your code")
    print()


def stage_budget(agent: Any) -> None:
    print("== 5. budget: recursion_limit raises instead of returning ========")
    try:
        agent.invoke(
            {"messages": [HumanMessage(QUESTION_REFUND)]},
            {"recursion_limit": 2},
        )
    except GraphRecursionError as error:
        print(f"GraphRecursionError: {str(error).splitlines()[0]}")
        print("  the hand-written loop returned stopped='budget'; the graph raises")
    else:
        print("  no error: the task fit inside 2 graph steps")
    print()


def print_comparison() -> None:
    print("same tools, same model, same wire protocol:")
    print("  run_loop      you own the for-loop, the error handling, the budget")
    print("  create_agent  LangGraph owns the loop; middleware adds approval and limits")
    print()


# --- entry point ------------------------------------------------------------


def run() -> int:
    try:
        model = build_model()
    except RuntimeError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    print(f"DeepSeek via LangChain -- live model ({MODEL}), framework-owned loop")
    print()
    agent = build_agent(model)
    stage_graph(agent)
    stage_one_call(agent)
    stage_stream(agent)
    stage_approval(model)
    stage_budget(agent)
    print_comparison()
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
