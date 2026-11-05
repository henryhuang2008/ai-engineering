"""LanceDB: one table for rows, vectors and the BM25 index.

A row is a chunk. The vector column feeds the dense half of a hybrid query;
the FTS index on `text` feeds the BM25 half. Both live in the same table, so a
filter applies to both and chunk ids never have to be joined by hand.
"""

from __future__ import annotations

from typing import Any

import lancedb
from lancedb.index import FTS
from lancedb.pydantic import LanceModel, Vector
from lancedb.rerankers import RRFReranker

from common import DB_DIR, EMBED_DIM, TABLE_NAME


class Chunk(LanceModel):
    id: str
    text: str
    source: str
    headings: str
    pages: str
    doc_hash: str
    vector: Vector(EMBED_DIM)


def connect() -> lancedb.DBConnection:
    DB_DIR.mkdir(parents=True, exist_ok=True)
    return lancedb.connect(str(DB_DIR))


def table_names(db: lancedb.DBConnection) -> list[str]:
    return list(db.table_names())


def open_table(db: lancedb.DBConnection) -> lancedb.table.Table:
    return db.open_table(TABLE_NAME)


def create_table(db: lancedb.DBConnection, rows: list[Chunk]) -> lancedb.table.Table:
    table = db.create_table(TABLE_NAME, schema=Chunk, mode="overwrite")
    if rows:
        table.add(rows)
    return table


def delete_source(table: lancedb.table.Table, source: str) -> None:
    escaped = source.replace("'", "''")
    table.delete(f"source = '{escaped}'")


def build_fts(table: lancedb.table.Table) -> None:
    """BM25 index. These analyser settings are fixed here and assumed at query time."""
    table.create_index(
        "text",
        config=FTS(
            language="English",
            stem=True,
            remove_stop_words=True,
            ascii_folding=True,
        ),
        replace=True,
    )


def existing_hashes(table: lancedb.table.Table) -> dict[str, str]:
    """source -> doc_hash, read back from the table itself (no manifest file)."""
    columns = table.to_arrow().to_pydict()
    return dict(zip(columns["source"], columns["doc_hash"]))  # noqa: B905


def hybrid_search(
    table: lancedb.table.Table,
    text: str,
    vector: list[float],
    k: int = 8,
    rerank: bool = False,
) -> list[dict[str, Any]]:
    query = (
        table.search(query_type="hybrid")
        .vector(vector)
        .text(text)
    )
    if rerank:
        from lancedb.rerankers import CrossEncoderReranker

        query = query.rerank(CrossEncoderReranker())
    else:
        query = query.rerank(RRFReranker())
    return query.limit(k).to_list()
