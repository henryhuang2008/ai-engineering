from __future__ import annotations

import asyncio
from datetime import date
from uuid import UUID

import pytest
from sqlalchemy.dialects import postgresql

from app.database.models import DocumentChunk, SourceDocument
from app.retrieval.models import SearchFilters
from app.retrieval.retriever import HybridRetriever, _async_postgres_url

CHUNK_A = UUID("00000000-0000-0000-0000-000000000001")
CHUNK_B = UUID("00000000-0000-0000-0000-000000000002")
DOCUMENT_ID = UUID("a61b2c08-8c8d-4c54-9dbb-f9828eb04818")


class FakeResult:
    def __init__(self, rows: list[object]) -> None:
        self._rows = rows

    def all(self) -> list[object]:
        return self._rows

    def mappings(self) -> FakeResult:
        return FakeResult(
            [_passage_record(*row) if isinstance(row, tuple) else row for row in self._rows]
        )

    def one_or_none(self) -> object | None:
        if not self._rows:
            return None
        assert len(self._rows) == 1
        return self._rows[0]


class FakeSession:
    def __init__(self, results: list[list[object]]) -> None:
        self.results = results
        self.statements: list[object] = []

    async def __aenter__(self) -> FakeSession:
        return self

    async def __aexit__(self, *_: object) -> None:
        return None

    async def execute(self, statement: object) -> FakeResult:
        self.statements.append(statement)
        return FakeResult(self.results.pop(0))


class FakeSessionFactory:
    def __init__(self, session: FakeSession) -> None:
        self.session = session

    def __call__(self) -> FakeSession:
        return self.session


class FakeEmbedder:
    def __init__(self) -> None:
        self.queries: list[str] = []

    async def embed_query(self, query: str) -> list[float]:
        self.queries.append(query)
        return [0.1] * 1536

    async def aclose(self) -> None:
        return None


def _passage_rows() -> tuple[tuple[DocumentChunk, SourceDocument], ...]:
    document = SourceDocument(
        id=DOCUMENT_ID,
        ticker="GOOGL",
        company_name="Alphabet Inc.",
        filing_type="10-K",
        filing_date=date(2026, 2, 5),
        fiscal_year=2025,
        accession_number="0001652044-26-000012",
        source_url="https://example.test/filing",
        content="# filing",
        document_metadata={"source": "SEC"},
    )
    chunks = [
        DocumentChunk(
            id=chunk_id,
            document_id=DOCUMENT_ID,
            chunk_index=index,
            content=f"Passage {index}",
            section="Revenue",
            token_count=4,
            source_start=None,
            source_end=None,
            embedding=[0.1] * 1536,
            chunk_metadata={"page_references": [index + 1]},
        )
        for index, chunk_id in ((0, CHUNK_A), (1, CHUNK_B))
    ]
    return ((chunks[0], document), (chunks[1], document))


def _passage_record(chunk: DocumentChunk, document: SourceDocument) -> dict[str, object]:
    return {
        "chunk_id": chunk.id,
        "document_id": document.id,
        "chunk_index": chunk.chunk_index,
        "content": chunk.content,
        "section": chunk.section,
        "source_start": chunk.source_start,
        "source_end": chunk.source_end,
        "page_references": chunk.chunk_metadata.get("page_references", []),
        "ticker": document.ticker,
        "company_name": document.company_name,
        "filing_type": document.filing_type,
        "filing_date": document.filing_date,
        "fiscal_year": document.fiscal_year,
        "accession_number": document.accession_number,
        "source_url": document.source_url,
    }


def test_search_fuses_both_branches_and_restores_fused_order() -> None:
    rows = _passage_rows()
    session = FakeSession(
        [
            [(CHUNK_A, 0.1), (CHUNK_B, 0.2)],
            [(CHUNK_A, 0.9)],
            [rows[1], rows[0]],
        ]
    )
    embedder = FakeEmbedder()
    retriever = HybridRetriever(FakeSessionFactory(session), embedder)
    filters = SearchFilters(ticker="GOOGL", fiscal_year=2025, filing_type="10-K")

    passages = asyncio.run(retriever.search_filings("  revenue  ", filters))

    assert [passage.chunk_id for passage in passages] == [CHUNK_A, CHUNK_B]
    assert [passage.content for passage in passages] == ["Passage 0", "Passage 1"]
    assert embedder.queries == ["revenue"]
    assert passages[0].retrieval is not None
    assert passages[0].retrieval.semantic_rank == 1
    assert passages[0].retrieval.lexical_rank == 1
    assert passages[1].retrieval is not None
    assert passages[1].retrieval.semantic_rank == 2
    assert passages[1].retrieval.lexical_rank is None
    assert passages[0].source_start is None
    assert passages[0].chunk_metadata["page_references"] == [1]

    compiled = [
        statement.compile(dialect=postgresql.dialect()) for statement in session.statements[:2]
    ]
    for statement in compiled:
        assert "source_documents.ticker =" in str(statement)
        assert "source_documents.fiscal_year =" in str(statement)
        assert "source_documents.filing_type =" in str(statement)
        assert "GOOGL" in statement.params.values()
        assert 2025 in statement.params.values()
        assert "10-K" in statement.params.values()


def test_search_returns_empty_when_both_retrievers_find_nothing() -> None:
    session = FakeSession([[], []])
    retriever = HybridRetriever(FakeSessionFactory(session), FakeEmbedder())

    assert asyncio.run(retriever.search_filings("revenue")) == []
    assert len(session.statements) == 2


def test_read_chunk_returns_passage_metadata() -> None:
    chunk, document = _passage_rows()[0]
    session = FakeSession([[(chunk, document)]])
    retriever = HybridRetriever(FakeSessionFactory(session), FakeEmbedder())

    passage = asyncio.run(retriever.read_chunk(CHUNK_A))

    assert passage is not None
    assert passage.chunk_id == CHUNK_A
    assert passage.ticker == "GOOGL"
    assert passage.source_start is None


def test_read_chunk_returns_none_for_unknown_chunk() -> None:
    session = FakeSession([[]])
    retriever = HybridRetriever(FakeSessionFactory(session), FakeEmbedder())

    assert asyncio.run(retriever.read_chunk(CHUNK_A)) is None


@pytest.mark.parametrize("limit", [0, 11, True])
def test_search_rejects_invalid_result_limit(limit: int) -> None:
    session = FakeSession([])
    retriever = HybridRetriever(FakeSessionFactory(session), FakeEmbedder())

    with pytest.raises(ValueError, match="Search result limit"):
        asyncio.run(retriever.search_filings("revenue", limit=limit))
    assert session.statements == []


def test_read_surrounding_chunks_is_bounded_and_stays_within_document() -> None:
    rows = _passage_rows()
    target_chunk, document = rows[1]
    target_chunk.chunk_index = 1
    previous_chunk = DocumentChunk(
        id=CHUNK_A,
        document_id=DOCUMENT_ID,
        chunk_index=0,
        content="Previous",
        section="Revenue",
        token_count=3,
        embedding=[0.1] * 1536,
        chunk_metadata={},
    )
    session = FakeSession(
        [
            [(target_chunk, document)],
            [(previous_chunk, document), (target_chunk, document)],
        ]
    )
    retriever = HybridRetriever(FakeSessionFactory(session), FakeEmbedder())

    result = asyncio.run(retriever.read_surrounding_chunks(CHUNK_B))

    assert result is not None
    assert result.target.chunk_id == CHUNK_B
    assert [passage.chunk_id for passage in result.before] == [CHUNK_A]
    assert result.after == []
    neighbor_sql = str(session.statements[1].compile(dialect=postgresql.dialect()))
    assert "document_chunks.document_id =" in neighbor_sql
    assert "document_chunks.chunk_index BETWEEN" in neighbor_sql


def test_neighbor_window_rejects_values_outside_the_bound() -> None:
    session = FakeSession([])
    retriever = HybridRetriever(FakeSessionFactory(session), FakeEmbedder())

    with pytest.raises(ValueError, match="Neighbor window"):
        asyncio.run(retriever.read_surrounding_chunks(CHUNK_A, window=2))
    assert session.statements == []


def test_database_url_uses_async_psycopg_driver() -> None:
    url = _async_postgres_url("postgresql://user:password@db.example.test:5432/postgres")

    assert url.drivername == "postgresql+psycopg"
