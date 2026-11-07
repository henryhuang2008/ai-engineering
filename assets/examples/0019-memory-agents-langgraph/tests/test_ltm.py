from __future__ import annotations

from langchain_core.messages import AIMessage
from langgraph.store.memory import InMemoryStore

from app.ltm import (
    build_store,
    extract_facts,
    fact_key,
    facts_namespace,
    forget_user,
    recall_facts,
    remember_facts,
)
from tests.support import StubModel, make_settings


class RawModel:
    def __init__(self, text: str) -> None:
        self.text = text

    def invoke(self, messages):
        return AIMessage(content=self.text)


def test_extracts_json_array() -> None:
    model = StubModel(facts=["Works as a data scientist", "Prefers Python"])

    facts = extract_facts(model, "I'm a data scientist who likes Python")

    assert facts == ["Works as a data scientist", "Prefers Python"]


def test_falls_back_to_lines_when_json_is_missing() -> None:
    model = RawModel("- Works in finance\n- Learning Rust")

    facts = extract_facts(model, "I work in finance and I'm learning Rust")

    assert facts == ["Works in finance", "Learning Rust"]


def test_caps_fact_count_and_length() -> None:
    model = RawModel("[" + ", ".join(f'"fact {i}"' for i in range(8)) + "]")

    assert len(extract_facts(model, "text")) == 3


def test_remember_is_idempotent() -> None:
    store = InMemoryStore()
    namespace = facts_namespace("user-a")

    first = remember_facts(store, "user-a", ["Works in finance"], thread_id="t1")
    second = remember_facts(store, "user-a", ["Works in finance"], thread_id="t2")

    assert first == 1
    assert second == 0
    assert len(store.search(namespace, limit=10)) == 1


def test_fact_key_normalizes_case_and_spacing() -> None:
    assert fact_key("Works  in Finance") == fact_key("works in finance")


def test_recall_and_forget() -> None:
    store = InMemoryStore()
    remember_facts(store, "user-a", ["Likes Python", "Works in finance"], thread_id="t1")
    remember_facts(store, "user-b", ["Likes Rust"], thread_id="t1")

    assert set(recall_facts(store, "user-a", limit=10)) == {"Likes Python", "Works in finance"}

    deleted = forget_user(store, "user-a")

    assert deleted == 2
    assert recall_facts(store, "user-a", limit=10) == []
    assert recall_facts(store, "user-b", limit=10) == ["Likes Rust"]


def test_search_without_an_index_is_not_semantic() -> None:
    store = InMemoryStore()
    remember_facts(store, "user-a", ["Works in finance"], thread_id="t1")

    items = store.search(facts_namespace("user-a"), query="what is their job", limit=5)

    # The query is accepted but ignored: no embeddings, no score, no ranking.
    assert items[0].score is None


def test_build_store_reports_its_mode() -> None:
    store, semantic = build_store(make_settings())

    assert semantic is False
    assert isinstance(store, InMemoryStore)
