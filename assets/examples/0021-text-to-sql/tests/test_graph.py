from __future__ import annotations

from pathlib import Path

import pytest
from langchain_core.messages import AIMessage
from langgraph.types import Command

from app import db
from app.graph import build_graph, extract_sql
from tests.support import ScriptedModel, make_settings, tool_call

CONFIG = {"configurable": {"thread_id": "test-thread"}}
COUNT_SQL = "SELECT COUNT(*) AS n FROM orders WHERE status = 'completed'"


@pytest.fixture()
def settings(tmp_path: Path):
    value = make_settings(tmp_path / "northstar.db")
    db.build_db(value.db_path, force=True)
    return value


def test_extract_sql_prefers_the_tool_call() -> None:
    message = AIMessage(
        content="```sql\nSELECT 2\n```",
        tool_calls=[{"name": "run_query", "args": {"query": "SELECT 1"}, "id": "c1"}],
    )
    assert extract_sql(message) == ("SELECT 1", "c1")


def test_extract_sql_falls_back_to_a_fence() -> None:
    assert extract_sql(AIMessage(content="```sql\nSELECT 1\n```")) == ("SELECT 1", None)
    assert extract_sql(AIMessage(content="no query here")) == (None, None)


def test_one_good_query_produces_an_answer(settings) -> None:
    model = ScriptedModel(
        responses=[tool_call(COUNT_SQL), AIMessage(content="There were 10 completed orders.")]
    )
    graph = build_graph(model, settings)

    state = graph.invoke({"question": "How many orders were completed?", "attempts": 0}, CONFIG)

    assert state["attempts"] == 1
    assert state["error"] is None
    assert state["result"].splitlines()[0] == "n"
    assert state["messages"][-1].content == "There were 10 completed orders."
    assert len(model.seen) == 2  # generate, then answer


def test_a_bad_query_is_retried_once(settings) -> None:
    model = ScriptedModel(
        responses=[
            tool_call("SELECT nope FROM orders", "c1"),
            tool_call(COUNT_SQL, "c2"),
            AIMessage(content="10"),
        ]
    )
    graph = build_graph(model, settings)

    state = graph.invoke({"question": "How many?", "attempts": 0}, CONFIG)

    assert state["attempts"] == 2
    assert state["error"] is None
    assert state["messages"][-1].content == "10"
    # The retry prompt carries the SQLite error, so the next turn can fix it.
    assert any(
        "no such column" in str(message.content) for message in model.seen[1]
    )


def test_it_gives_up_after_max_attempts(settings) -> None:
    model = ScriptedModel(
        responses=[tool_call("SELECT nope FROM orders", f"c{i}") for i in range(3)]
    )
    graph = build_graph(model, settings)

    state = graph.invoke({"question": "How many?", "attempts": 0}, CONFIG)

    assert state["attempts"] == 3
    assert state["error"] is not None
    assert state["messages"][-1].content.startswith("I could not produce")


def test_insufficient_schema_ends_without_running_sql(settings) -> None:
    model = ScriptedModel(
        responses=[
            AIMessage(
                content="INSUFFICIENT_SCHEMA: there is no refunds table or refunded status."
            )
        ]
    )
    graph = build_graph(model, settings)

    state = graph.invoke({"question": "What is the refund rate?", "attempts": 0}, CONFIG)

    assert state["sql"] is None
    assert state.get("result") is None
    assert state["messages"][-1].content.startswith("INSUFFICIENT_SCHEMA")
    assert len(model.seen) == 1  # no answer call, no execute


def _start_with_review(settings):
    model = ScriptedModel(
        responses=[tool_call("SELECT 1 AS n"), AIMessage(content="one")]
    )
    graph = build_graph(model, settings, review=True)
    state = graph.invoke({"question": "How many?", "attempts": 0}, CONFIG)
    return model, graph, state


def test_review_pauses_before_executing(settings) -> None:
    _, _, state = _start_with_review(settings)
    assert "__interrupt__" in state
    payload = state["__interrupt__"][0].value
    assert payload["sql"] == "SELECT 1 AS n"
    assert payload["attempt"] == 1


def test_review_approve_runs_the_query(settings) -> None:
    _, graph, state = _start_with_review(settings)
    state = graph.invoke(Command(resume={"action": "approve"}), CONFIG)
    assert state["result"] == "n\n1. 1"
    assert state["messages"][-1].content == "one"


def test_review_edit_runs_the_edited_query(settings) -> None:
    _, graph, _ = _start_with_review(settings)
    state = graph.invoke(
        Command(resume={"action": "edit", "sql": "SELECT 42 AS n"}), CONFIG
    )
    assert state["sql"] == "SELECT 42 AS n"
    assert state["result"] == "n\n1. 42"


def test_review_reject_stops_the_graph(settings) -> None:
    model, graph, _ = _start_with_review(settings)
    state = graph.invoke(Command(resume={"action": "reject"}), CONFIG)
    assert state.get("result") is None
    assert state["messages"][-1].content.startswith("I could not produce")
    assert len(model.seen) == 1  # the answer node never ran
