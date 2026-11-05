"""The smallest useful LangGraph: one node, two edges, one reducer.

A graph is four declarations:

  State   -- the data the nodes share (here: a message list)
  Node    -- a function that reads state and returns a delta
  Edge    -- who runs next (START -> chatbot -> END)
  compile -- turn the declarations into an app you can invoke

Run from this folder:

    uv sync
    uv run python simple.py
    uv run python simple.py --mermaid     # print the diagram source
"""

from __future__ import annotations

import sys
from typing import Annotated, TypedDict

from langchain_core.messages import HumanMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages

from common import build_model

QUESTION = "In one sentence, what does a router do in a LangGraph?"


class State(TypedDict):
    # add_messages is the reducer: a node appends, it never replaces the list.
    messages: Annotated[list, add_messages]


def build_graph(model):
    def chatbot(state: State) -> dict:
        # Return a delta, not the new state. The reducer merges it.
        return {"messages": [model.invoke(state["messages"])]}

    graph = StateGraph(State)
    graph.add_node("chatbot", chatbot)
    graph.add_edge(START, "chatbot")
    graph.add_edge("chatbot", END)
    return graph.compile()


def main() -> int:
    try:
        model = build_model()
    except RuntimeError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    app = build_graph(model)

    if "--mermaid" in sys.argv[1:]:
        print(app.get_graph().draw_mermaid())
        return 0

    result = app.invoke({"messages": [HumanMessage(content=QUESTION)]})
    reply = result["messages"][-1].content

    print(f"question: {QUESTION}")
    print(f"reply:    {reply}")
    print()
    print(
        "state: "
        f"{len(result['messages'])} messages "
        f"({', '.join(message.type for message in result['messages'])})"
    )
    print("edges:")
    for edge in app.get_graph().edges:
        print(f"  {edge.source} -> {edge.target}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:  # noqa: BLE001 - show the provider error, keep exit 1
        print(f"error: {type(error).__name__}: {error}", file=sys.stderr)
        print("check DEEPSEEK_API_KEY, account balance, and network access.", file=sys.stderr)
        raise SystemExit(1) from error
