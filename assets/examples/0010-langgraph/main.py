"""One branch: classify the message, then run the matching specialist.

The classifier is a structured-output call, so the route is a validated
Literal -- not a string match on prose. The conditional edge reads that field
and returns a node name. Everything else is the same four nouns as simple.py.

Run from this folder:

    uv sync
    uv run python main.py "I was charged twice for the Team plan"
    uv run python main.py "Outlook sync fails with E-311" --trace
    uv run python main.py                  # interactive
    uv run python main.py --mermaid        # print the diagram source
"""

from __future__ import annotations

import sys
from typing import Annotated, Literal, TypedDict

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field

from common import build_model

CLASSIFY_PROMPT = """You classify NimbusDesk customer messages.

- billing: charges, invoices, refunds, plans, seats, cancellation
- technical: errors, logins, integrations, outages, how-to steps

Pick the single best route. If the message mentions both, pick the one that
blocks the customer right now."""

BILLING_PROMPT = """You are NimbusDesk's billing specialist.
Facts you may use:
- A full refund is available within 14 days of the initial charge.
- After day 14, annual plans are refunded pro rata minus the months used.
- The Team plan includes 25 seats; extra seats are billed monthly.
Answer in at most three sentences. If a fact is not in this list, say so."""

TECHNICAL_PROMPT = """You are NimbusDesk's technical specialist.
Facts you may use:
- E-311 means the mailbox storage quota was exceeded.
- Fix: archive conversations or raise the seat storage limit.
- SSO uses SAML 2.0; the metadata URL is under Settings > Security.
Answer in at most three sentences. If a fact is not in this list, say so."""


class Route(BaseModel):
    """The classifier's output schema: one of two node names."""

    route: Literal["billing", "technical"] = Field(
        description="billing for money questions, technical for product failures"
    )


class State(TypedDict):
    messages: Annotated[list, add_messages]
    route: str | None


def build_graph(model):
    classifier = model.with_structured_output(Route, method="function_calling")

    def classify(state: State) -> dict:
        decision = classifier.invoke(
            [
                SystemMessage(content=CLASSIFY_PROMPT),
                state["messages"][-1],
            ]
        )
        return {"route": decision.route}

    def pick_specialist(state: State) -> str:
        # This is the conditional edge: a pure function -> a node name.
        return state["route"] or "technical"

    def billing(state: State) -> dict:
        reply = model.invoke([SystemMessage(content=BILLING_PROMPT), *state["messages"]])
        return {"messages": [reply]}

    def technical(state: State) -> dict:
        reply = model.invoke(
            [SystemMessage(content=TECHNICAL_PROMPT), *state["messages"]]
        )
        return {"messages": [reply]}

    graph = StateGraph(State)
    graph.add_node("classify", classify)
    graph.add_node("billing", billing)
    graph.add_node("technical", technical)

    graph.add_edge(START, "classify")
    graph.add_conditional_edges(
        "classify",
        pick_specialist,
        {"billing": "billing", "technical": "technical"},
    )
    graph.add_edge("billing", END)
    graph.add_edge("technical", END)
    return graph.compile()


def ask_once(app, question: str) -> None:
    """Stream one turn so each node's delta is visible."""
    inputs = {"messages": [HumanMessage(content=question)], "route": None}
    answer = ""

    print(f"question: {question}")
    for step, update in enumerate(app.stream(inputs, stream_mode="updates"), start=1):
        for node, delta in update.items():
            if node == "classify":
                print(f"step {step}  classify   route={delta['route']}")
            else:
                answer = delta["messages"][-1].content
                print(f"step {step}  {node:<10} replied ({len(answer)} chars)")
    print()
    print(f"answer: {answer}")


def chat_loop(app) -> None:
    """Keep the state between turns, like a small chat session."""
    state = {"messages": [], "route": None}
    print("type a message, or 'exit'.")
    while True:
        try:
            text = input("\nyou: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if text.lower() in {"exit", "quit"}:
            return

        state = app.invoke(
            {**state, "messages": state["messages"] + [HumanMessage(content=text)]}
        )
        print(f"route: {state['route']}")
        print(f"bot:   {state['messages'][-1].content}")


def main() -> int:
    try:
        model = build_model()
    except RuntimeError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    app = build_graph(model)
    args = sys.argv[1:]

    if "--mermaid" in args:
        print(app.get_graph().draw_mermaid())
        return 0

    trace = "--trace" in args
    args = [arg for arg in args if arg != "--trace"]

    if not args:
        chat_loop(app)
    elif trace:
        ask_once(app, " ".join(args))
    else:
        state = app.invoke(
            {"messages": [HumanMessage(content=" ".join(args))], "route": None}
        )
        print(f"route:  {state['route']}")
        print(f"answer: {state['messages'][-1].content}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:  # noqa: BLE001 - show the provider error, keep exit 1
        print(f"error: {type(error).__name__}: {error}", file=sys.stderr)
        print("check DEEPSEEK_API_KEY, account balance, and network access.", file=sys.stderr)
        raise SystemExit(1) from error
