"""Long-term memory: a store keyed by user, independent of any thread.

The article's Part 6-9 shape: a namespace per user, ``put/get/search/delete``,
facts extracted from the conversation and written back. Two corrections:

* ``search(query=...)`` is only semantic when the store was built with an
  embedding index. Without one, LangGraph ignores the query and returns items
  with ``score=None`` -- so this module passes the query only when the index
  exists, and says which mode it is in.
* Facts are keyed by a hash of their text, so extracting the same fact twice
  overwrites instead of duplicating it.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime

from langchain_core.language_models.chat_models import BaseChatModel
from langgraph.store.memory import InMemoryStore

from app.config import Settings
from app.embeddings import OpenAICompatibleEmbeddings

MAX_FACTS_PER_TURN = 3
MAX_FACT_CHARACTERS = 240
FACT_FIELDS = ["fact"]

EXTRACTION_PROMPT = """Extract up to {limit} durable facts about the user from the message.
A durable fact is something useful in a future conversation: role, skills,
goals, preferences, constraints, ongoing projects. Ignore small talk, questions,
and anything temporary.

Return a JSON array of strings. Return [] if nothing is worth remembering.
Example: ["Works as a data scientist", "Prefers Python for analysis"]

Message:
{message}
"""


def facts_namespace(user_id: str) -> tuple[str, str]:
    return (user_id, "facts")


def fact_key(text: str) -> str:
    normalized = " ".join(text.lower().split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


def build_store(settings: Settings) -> tuple[InMemoryStore, bool]:
    """Return (store, semantic). Semantic needs an embedding provider."""
    if not settings.semantic_memory:
        return InMemoryStore(), False

    embeddings = OpenAICompatibleEmbeddings(settings)
    store = InMemoryStore(
        index={
            "dims": settings.embed_dims,
            "embed": embeddings,
            "fields": FACT_FIELDS,
        }
    )
    return store, True


def extract_facts(model: BaseChatModel, message: str) -> list[str]:
    """Ask the model for durable facts; parse defensively."""
    response = model.invoke(
        [
            {
                "role": "user",
                "content": EXTRACTION_PROMPT.format(
                    limit=MAX_FACTS_PER_TURN, message=message
                ),
            }
        ]
    )
    raw = str(response.content).strip()
    facts: list[str] = []
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            facts = [str(item) for item in parsed]
    except json.JSONDecodeError:
        facts = [line.lstrip("-* ").strip() for line in raw.splitlines()]

    cleaned = []
    for fact in facts:
        fact = " ".join(fact.split())
        if fact and len(fact) <= MAX_FACT_CHARACTERS:
            cleaned.append(fact)
    return cleaned[:MAX_FACTS_PER_TURN]


def remember_facts(
    store: InMemoryStore,
    user_id: str,
    facts: list[str],
    *,
    thread_id: str,
) -> int:
    """Write facts under the user's namespace. Returns how many were new."""
    namespace = facts_namespace(user_id)
    written = 0
    for fact in facts:
        key = fact_key(fact)
        if store.get(namespace, key) is not None:
            continue
        store.put(
            namespace,
            key,
            {
                "fact": fact,
                "thread_id": thread_id,
                "created_at": datetime.now(UTC).isoformat(),
            },
        )
        written += 1
    return written


def recall_facts(
    store: InMemoryStore,
    user_id: str,
    *,
    query: str | None = None,
    semantic: bool = False,
    limit: int = 5,
) -> list[str]:
    """Read facts back. Ranked by similarity only when an index exists."""
    namespace = facts_namespace(user_id)
    if semantic and query:
        items = store.search(namespace, query=query, limit=limit)
    else:
        items = store.search(namespace, limit=limit)
    return [
        str(item.value.get("fact", item.value))
        if isinstance(item.value, dict)
        else str(item.value)
        for item in items
    ]


def forget_user(store: InMemoryStore, user_id: str) -> int:
    """Delete every fact for a user. Long-term memory needs a delete path."""
    namespace = facts_namespace(user_id)
    items = store.search(namespace, limit=10_000)
    for item in items:
        store.delete(namespace, item.key)
    return len(items)
