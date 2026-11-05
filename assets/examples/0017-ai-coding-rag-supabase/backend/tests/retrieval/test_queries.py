from uuid import UUID

from sqlalchemy.dialects import postgresql

from app.retrieval.models import MAX_PASSAGE_EXCERPT_LENGTH, SearchFilters
from app.retrieval.queries import (
    CANDIDATE_LIMIT,
    lexical_candidates_query,
    neighboring_chunks_query,
    passage_hydration_query,
    semantic_candidates_query,
)


def _compile(statement: object) -> tuple[str, dict[str, object]]:
    compiled = statement.compile(dialect=postgresql.dialect())
    return str(compiled), compiled.params


def test_semantic_and_lexical_queries_apply_identical_filing_filters() -> None:
    filters = SearchFilters(ticker="googl", fiscal_year=2025, filing_type="10-k")
    semantic_sql, semantic_params = _compile(semantic_candidates_query([0.1] * 1536, filters))
    lexical_sql, lexical_params = _compile(lexical_candidates_query("annual revenue", filters))

    for sql in (semantic_sql, lexical_sql):
        assert "source_documents.ticker =" in sql
        assert "source_documents.fiscal_year =" in sql
        assert "source_documents.filing_type =" in sql
        assert "LIMIT" in sql
    for params in (semantic_params, lexical_params):
        assert "GOOGL" in params.values()
        assert 2025 in params.values()
        assert "10-K" in params.values()
        assert CANDIDATE_LIMIT in params.values()
    assert "websearch_to_tsquery" in lexical_sql
    assert "annual revenue" in lexical_params.values()
    assert "annual revenue" not in lexical_sql


def test_semantic_query_uses_cosine_distance_and_stable_tie_breaking() -> None:
    sql, params = _compile(semantic_candidates_query([0.25] * 1536))

    assert "<=>" in sql
    assert "document_chunks.id ASC" in sql
    assert any(value == [0.25] * 1536 for value in params.values())


def test_neighbor_query_is_scoped_to_one_document_and_adjacent_indices() -> None:
    document_id = UUID("a61b2c08-8c8d-4c54-9dbb-f9828eb04818")
    sql, params = _compile(neighboring_chunks_query(document_id, 2, 4))

    assert "document_chunks.document_id =" in sql
    assert "document_chunks.chunk_index BETWEEN" in sql
    assert params["document_id_1"] == document_id
    assert 2 in params.values()
    assert 4 in params.values()


def test_passage_hydration_does_not_load_embeddings_or_full_filing_text() -> None:
    chunk_id = UUID("00000000-0000-0000-0000-000000000001")
    sql, params = _compile(passage_hydration_query([chunk_id]))

    assert "document_chunks.content" in sql
    assert "left(document_chunks.content" in sql
    assert MAX_PASSAGE_EXCERPT_LENGTH in params.values()
    assert "AS page_references" in sql
    assert "source_documents.source_url" in sql
    assert "document_chunks.embedding" not in sql
    assert "source_documents.content" not in sql
    assert "document_chunks.metadata AS chunk_metadata" not in sql
