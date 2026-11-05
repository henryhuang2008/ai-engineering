from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import Select, func, select

from app.database.models import DocumentChunk, SourceDocument
from app.retrieval.models import MAX_PASSAGE_EXCERPT_LENGTH, SearchFilters

VECTOR_DIMENSIONS = 1536
CANDIDATE_LIMIT = 50


def _passage_columns() -> tuple[Any, ...]:
    return (
        DocumentChunk.id.label("chunk_id"),
        DocumentChunk.document_id,
        DocumentChunk.chunk_index,
        func.left(DocumentChunk.content, MAX_PASSAGE_EXCERPT_LENGTH).label("content"),
        DocumentChunk.section,
        DocumentChunk.source_start,
        DocumentChunk.source_end,
        DocumentChunk.chunk_metadata["page_references"].label("page_references"),
        SourceDocument.ticker,
        SourceDocument.company_name,
        SourceDocument.filing_type,
        SourceDocument.filing_date,
        SourceDocument.fiscal_year,
        SourceDocument.accession_number,
        SourceDocument.source_url,
    )


def semantic_candidates_query(
    embedding: list[float],
    filters: SearchFilters | None = None,
    limit: int = CANDIDATE_LIMIT,
) -> Select[Any]:
    distance = DocumentChunk.embedding.cosine_distance(embedding)
    statement = (
        select(DocumentChunk.id, distance.label("score"))
        .join(SourceDocument, DocumentChunk.document_id == SourceDocument.id)
        .order_by(distance.asc(), DocumentChunk.id.asc())
        .limit(limit)
    )
    return _apply_filters(statement, filters)


def lexical_candidates_query(
    query: str,
    filters: SearchFilters | None = None,
    limit: int = CANDIDATE_LIMIT,
) -> Select[Any]:
    tsquery = func.websearch_to_tsquery("english", query)
    score = func.ts_rank_cd(DocumentChunk.search_vector, tsquery)
    statement = (
        select(DocumentChunk.id, score.label("score"))
        .join(SourceDocument, DocumentChunk.document_id == SourceDocument.id)
        .where(DocumentChunk.search_vector.op("@@")(tsquery))
        .order_by(score.desc(), DocumentChunk.id.asc())
        .limit(limit)
    )
    return _apply_filters(statement, filters)


def passage_hydration_query(chunk_ids: list[UUID]) -> Select[Any]:
    return (
        select(*_passage_columns())
        .join(SourceDocument, DocumentChunk.document_id == SourceDocument.id)
        .where(DocumentChunk.id.in_(chunk_ids))
    )


def chunk_lookup_query(chunk_id: UUID) -> Select[Any]:
    return (
        select(*_passage_columns())
        .join(SourceDocument, DocumentChunk.document_id == SourceDocument.id)
        .where(DocumentChunk.id == chunk_id)
    )


def neighboring_chunks_query(
    document_id: UUID,
    first_chunk_index: int,
    last_chunk_index: int,
) -> Select[Any]:
    return (
        select(*_passage_columns())
        .join(SourceDocument, DocumentChunk.document_id == SourceDocument.id)
        .where(
            DocumentChunk.document_id == document_id,
            DocumentChunk.chunk_index.between(first_chunk_index, last_chunk_index),
        )
        .order_by(DocumentChunk.chunk_index.asc())
    )


def _apply_filters(
    statement: Select[Any],
    filters: SearchFilters | None,
) -> Select[Any]:
    if filters is None:
        return statement

    if filters.ticker is not None:
        statement = statement.where(SourceDocument.ticker == filters.ticker)
    if filters.fiscal_year is not None:
        statement = statement.where(SourceDocument.fiscal_year == filters.fiscal_year)
    if filters.filing_type is not None:
        statement = statement.where(SourceDocument.filing_type == filters.filing_type)
    return statement
