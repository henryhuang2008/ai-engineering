"""Postgres-backed STM and LTM: PostgresSaver + PostgresStore.

Not exercised by the test suite: it needs a running pgvector database. The
``--postgres`` CLI flag is the gate. Both objects share one connection pool,
which is the part the article gets right.
"""

from __future__ import annotations

from typing import Any

from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.store.postgres import PostgresStore
from psycopg_pool import ConnectionPool

from app.config import Settings
from app.embeddings import OpenAICompatibleEmbeddings
from app.ltm import FACT_FIELDS


def build_postgres(settings: Settings) -> tuple[ConnectionPool, Any, Any, bool]:
    if not settings.database_url:
        raise ValueError("DATABASE_URL is required for --postgres")

    pool = ConnectionPool(
        conninfo=settings.database_url,
        kwargs={"autocommit": True},
        open=True,
    )

    checkpointer = PostgresSaver(conn=pool)
    checkpointer.setup()

    semantic = settings.semantic_memory
    index = None
    if semantic:
        embeddings = OpenAICompatibleEmbeddings(settings)
        index = {
            "dims": settings.embed_dims,
            "embed": embeddings,
            "fields": FACT_FIELDS,
        }

    store = PostgresStore(conn=pool, index=index)
    store.setup()
    return pool, checkpointer, store, semantic
