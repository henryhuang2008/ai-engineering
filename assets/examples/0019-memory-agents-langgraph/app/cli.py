from __future__ import annotations

import argparse
import sys

from langgraph.checkpoint.memory import InMemorySaver

from app.config import Settings, get_settings
from app.graph import create_memory_graph, run_turn
from app.llm import build_llm
from app.ltm import build_store, forget_user, recall_facts
from app.stm import build_stm_graph, history, send

DEMO_TURNS = [
    "Hi! My name is Alice",
    "What's my name?",
    "Remind me my name",
]
BOB_INTRO = "Hi! My name is Bob"
FACT_TURNS = [
    "I'm a data scientist working in Python and machine learning.",
    "What should I focus on learning next?",
]


def _stores(settings: Settings, use_postgres: bool):
    if use_postgres:
        from app.postgres import build_postgres

        pool, checkpointer, store, semantic = build_postgres(settings)
        return pool, checkpointer, store, semantic
    store, semantic = build_store(settings)
    return None, InMemorySaver(), store, semantic


def _stm_demo(model) -> int:
    graph = build_stm_graph(model, InMemorySaver())
    print("=== thread-1 (Alice) ===")
    for text in DEMO_TURNS:
        print(f"you> {text}")
        print(f"bot> {send(graph, 'thread-1', text)}")
        print()
    print("=== thread-2 (Bob) ===")
    print(f"you> {BOB_INTRO}")
    print(f"bot> {send(graph, 'thread-2', BOB_INTRO)}")
    print(f"you> {DEMO_TURNS[1]}")
    print(f"bot> {send(graph, 'thread-2', DEMO_TURNS[1])}")
    print()
    print(f"thread-1 messages stored: {len(history(graph, 'thread-1'))}")
    print(f"thread-2 messages stored: {len(history(graph, 'thread-2'))}")
    return 0


def _facts_demo(settings: Settings, model, use_postgres: bool) -> int:
    pool, checkpointer, store, semantic = _stores(settings, use_postgres)
    graph = create_memory_graph(
        model,
        store,
        settings=settings,
        checkpointer=checkpointer,
        semantic=semantic,
    )
    user_id = "user-alice"
    print("=== thread A: introduce yourself ===")
    print(f"bot> {run_turn(graph, user_id, 'alice-1', FACT_TURNS[0])}")
    print(f"stored facts: {recall_facts(store, user_id, limit=10)}")
    print()
    print("=== thread B: a new conversation, same user ===")
    print(f"bot> {run_turn(graph, user_id, 'alice-2', FACT_TURNS[1])}")
    print(f"facts after turn: {recall_facts(store, user_id, limit=10)}")
    if pool is not None:
        pool.close()
    return 0


def _chat(settings: Settings, model, use_postgres: bool) -> int:
    pool, checkpointer, store, semantic = _stores(settings, use_postgres)
    graph = create_memory_graph(
        model,
        store,
        settings=settings,
        checkpointer=checkpointer,
        semantic=semantic,
    )
    user_id = input("user id [user-alice]: ").strip() or "user-alice"
    thread_id = input("thread id [chat-1]: ").strip() or "chat-1"
    print(f"user={user_id} thread={thread_id}; type 'exit' to stop.")
    while True:
        try:
            text = input("\nyou> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not text:
            continue
        if text.lower() in {"exit", "quit"}:
            break
        print(f"bot> {run_turn(graph, user_id, thread_id, text)}")
    print(f"\nfacts: {recall_facts(store, user_id, limit=20)}")
    if pool is not None:
        pool.close()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="0019-memory-agents-langgraph")
    parser.add_argument("--postgres", action="store_true", help="use PostgreSQL")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo", help="short-term memory across two threads")
    sub.add_parser("facts", help="long-term memory across two threads")
    sub.add_parser("chat", help="interactive agent with both memories")
    forget = sub.add_parser("forget", help="delete all facts for a user")
    forget.add_argument("user_id")

    args = parser.parse_args(argv)
    settings = get_settings()

    try:
        if args.command == "forget":
            if not args.postgres:
                print(
                    "error: forget needs --postgres; in-memory facts die with the process",
                    file=sys.stderr,
                )
                return 1
            pool, _, store, _ = _stores(settings, args.postgres)
            print(f"deleted {forget_user(store, args.user_id)} facts for {args.user_id}")
            if pool is not None:
                pool.close()
            return 0
        model = build_llm(settings)
        if args.command == "demo":
            return _stm_demo(model)
        if args.command == "facts":
            return _facts_demo(settings, model, args.postgres)
        return _chat(settings, model, args.postgres)
    except ValueError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
