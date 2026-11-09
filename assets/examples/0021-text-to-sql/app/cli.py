from __future__ import annotations

import argparse
import sys
from typing import Any
from uuid import uuid4

from langgraph.types import Command

from app import db
from app.config import Settings, get_settings
from app.graph import build_graph
from app.llm import build_llm

DEMO_QUESTIONS = [
    "How many orders were completed?",
    "What is total revenue from completed orders?",
    "Which customer placed the most orders, and how many did they place?",
    "What is the refund rate?",
]


def _text(message: Any) -> str:
    content = message.content
    if isinstance(content, str):
        return content
    parts = []
    for part in content:
        if isinstance(part, dict):
            parts.append(str(part.get("text", part)))
        else:
            parts.append(str(part))
    return "\n".join(parts)


def _decision(payload: dict) -> dict:
    print(f"\nproposed SQL (attempt {payload.get('attempt', 1)}):")
    print(payload.get("sql") or "(none)")
    try:
        choice = input("\n[a]pprove · [e]dit · [r]eject > ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return {"action": "reject"}

    if choice.startswith("e"):
        try:
            edited = input("new SQL > ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return {"action": "reject"}
        return {"action": "edit", "sql": edited}
    if choice.startswith("r"):
        return {"action": "reject"}
    return {"action": "approve"}


def ask(
    graph: Any,
    question: str,
    *,
    interactive: bool = True,
) -> dict:
    """Run one question, answering interrupt requests until the graph ends."""
    config = {"configurable": {"thread_id": f"ask-{uuid4().hex[:8]}"}}
    state = graph.invoke({"question": question, "attempts": 0}, config)

    while "__interrupt__" in state:
        payload = state["__interrupt__"][0].value
        decision = _decision(payload) if interactive else {"action": "approve"}
        state = graph.invoke(Command(resume=decision), config)
    return state


def _print_result(state: dict, *, show: bool) -> None:
    print(_text(state["messages"][-1]))
    if not show:
        return
    if state.get("sql"):
        print(f"\nSQL ({state.get('attempts', 0)} attempt(s)):")
        print(state["sql"])
    if state.get("result"):
        print("\nResult:")
        print(state["result"])
    if state.get("error"):
        print(f"\nLast error: {state['error']}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="0021-text-to-sql")
    sub = parser.add_subparsers(dest="command", required=True)

    build = sub.add_parser("build", help="create the SQLite file from the CSV seeds")
    build.add_argument("--force", action="store_true", help="rebuild from scratch")

    sub.add_parser("schema", help="print the schema the model is allowed to see")

    ask_parser = sub.add_parser("ask", help="answer one question")
    ask_parser.add_argument("question")
    ask_parser.add_argument("--show", action="store_true", help="print SQL and rows")
    ask_parser.add_argument(
        "--review",
        action="store_true",
        help="approve, edit or reject the SQL before it runs",
    )

    demo = sub.add_parser("demo", help="run four questions end to end")
    demo.add_argument("--show", action="store_true", help="print SQL and rows")
    demo.add_argument("--review", action="store_true", help="review every query")

    args = parser.parse_args(argv)
    settings = get_settings()

    if args.command == "build":
        counts = db.build_db(settings.db_path, force=args.force)
        print(f"built {settings.db_path}")
        for table, count in counts.items():
            print(f"  {table}: {count} rows")
        return 0

    if args.command == "schema":
        print(db.schema_text(settings.db_path))
        return 0

    try:
        model = build_llm(settings)
        graph = build_graph(model, settings, review=args.review)
        if args.command == "ask":
            state = ask(graph, args.question, interactive=args.review)
            _print_result(state, show=args.show)
            return 0

        for index, question in enumerate(DEMO_QUESTIONS, start=1):
            print(f"\n=== {index}. {question}")
            state = ask(graph, question, interactive=args.review)
            _print_result(state, show=args.show)
        return 0
    except ValueError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
