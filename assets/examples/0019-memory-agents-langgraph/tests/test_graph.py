from __future__ import annotations

from langgraph.store.memory import InMemoryStore

from app.graph import create_memory_graph, run_turn
from app.ltm import recall_facts, remember_facts
from tests.support import StubModel, make_settings


def config(thread_id: str) -> dict:
    return {"configurable": {"thread_id": thread_id}}


def test_facts_are_written_and_recalled_across_threads() -> None:
    store = InMemoryStore()
    model = StubModel(facts=["Works as a data scientist"])
    settings = make_settings()
    graph = create_memory_graph(model, store, settings=settings)

    run_turn(graph, "user-a", "thread-1", "I'm a data scientist")

    assert recall_facts(store, "user-a", limit=10) == ["Works as a data scientist"]
    assert "(nothing yet)" in model.system_prompts[0]

    run_turn(graph, "user-a", "thread-2", "What should I learn next?")

    assert "Works as a data scientist" in model.system_prompts[-1]


def test_facts_do_not_leak_between_users() -> None:
    store = InMemoryStore()
    remember_facts(store, "user-a", ["Works as a data scientist"], thread_id="seed")
    model = StubModel(facts=[])
    graph = create_memory_graph(model, store, settings=make_settings())

    run_turn(graph, "user-b", "thread-2", "Hello")

    assert "(nothing yet)" in model.system_prompts[-1]
    assert recall_facts(store, "user-b", limit=10) == []


def test_memory_context_is_declared_state_not_a_dropped_key() -> None:
    store = InMemoryStore()
    model = StubModel(facts=["Works as a data scientist"])
    graph = create_memory_graph(model, store, settings=make_settings())

    run_turn(graph, "user-a", "thread-1", "I'm a data scientist")
    run_turn(graph, "user-a", "thread-1", "And what next?")

    state = graph.get_state(config("thread-1")).values

    assert state["memory_context"] == "- Works as a data scientist"


def test_thread_history_keeps_more_than_the_model_sees() -> None:
    store = InMemoryStore()
    model = StubModel(facts=[])
    settings = make_settings(max_context_tokens=2000)
    graph = create_memory_graph(model, store, settings=settings)

    for index in range(4):
        run_turn(graph, "user-a", "thread-1", f"message {index}")

    state = graph.get_state(config("thread-1")).values

    # Eight messages stored; the chat call on the last turn saw seven plus the
    # system prompt. The extraction call is a single-message prompt.
    assert len(state["messages"]) == 8
    assert max(model.message_counts) == 8
    assert state["summary"] == ""
