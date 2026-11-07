from __future__ import annotations

from app.stm import build_stm_graph, history, send
from tests.support import StubModel


def test_threads_do_not_share_state() -> None:
    model = StubModel()
    graph = build_stm_graph(model)

    send(graph, "thread-1", "Hi! My name is Alice")
    send(graph, "thread-2", "Hi! My name is Bob")

    assert len(history(graph, "thread-1")) == 2
    assert len(history(graph, "thread-2")) == 2


def test_same_thread_reloads_its_history() -> None:
    model = StubModel()
    graph = build_stm_graph(model)

    send(graph, "thread-1", "first")
    send(graph, "thread-1", "second")
    send(graph, "thread-1", "third")

    # Before the third call, the model sees four messages (two exchanges).
    assert model.message_counts == [1, 3, 5]
    assert len(history(graph, "thread-1")) == 6


def test_new_thread_starts_empty() -> None:
    model = StubModel()
    graph = build_stm_graph(model)

    send(graph, "thread-1", "first")
    send(graph, "thread-2", "second")

    assert model.message_counts == [1, 1]
    assert history(graph, "thread-1")[0].content == "first"
    assert history(graph, "thread-2")[0].content == "second"
