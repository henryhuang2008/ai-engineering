from __future__ import annotations

import json
import sys
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from types import ModuleType, SimpleNamespace
from uuid import UUID

import pytest
from sqlalchemy.dialects import postgresql

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from data.ingest_chunks import (
    Chunk,
    ExistingChunk,
    Filing,
    chunk_filing,
    embed_texts,
    find_source_span,
    load_filings,
    match_document_ids,
    parse_args,
    pending_chunks,
    stale_chunk_indices,
    validate_embeddings,
    write_chunks,
)


def _write_manifest(directory: Path, count: int = 5) -> Path:
    filings = []
    for index in range(count):
        ticker = ("AAPL", "AMZN", "GOOGL", "MSFT", "NVDA")[index]
        filename = f"{ticker.lower()}.md"
        (directory / filename).write_text(f"# {ticker}\nFiling text.", encoding="utf-8")
        filings.append(
            {
                "ticker": ticker,
                "accession_number": f"accession-{ticker}",
                "form": "10-K",
                "filing_date": "2026-01-01",
                "report_date": "2025-12-31",
                "source_url": f"https://example.test/{ticker}",
                "local_path": filename,
            }
        )
    manifest_path = directory / "manifest.json"
    manifest_path.write_text(json.dumps({"filings": filings}), encoding="utf-8")
    return manifest_path


def _chunk(
    *,
    ticker: str = "AAPL",
    accession_number: str = "accession-AAPL",
    chunk_index: int = 0,
    content: str = "content",
) -> Chunk:
    return Chunk(
        ticker=ticker,
        accession_number=accession_number,
        chunk_index=chunk_index,
        content=content,
        embedding_text=f"section\n{content}",
        token_count=4,
        section="section",
        source_start=0,
        source_end=len(content),
        metadata={
            "embedding_text_sha256": f"hash-{content}",
            "source_offset_status": "exact",
        },
    )


def test_load_filings_selects_only_fiscal_year_2025(tmp_path: Path) -> None:
    manifest = _write_manifest(tmp_path)

    filings = load_filings(manifest, fiscal_year=2025)

    assert len(filings) == 5
    assert {filing.fiscal_year for filing in filings} == {2025}
    assert [filing.ticker for filing in filings] == ["AAPL", "AMZN", "GOOGL", "MSFT", "NVDA"]


def test_load_filings_rejects_unexpected_number_of_2025_documents(tmp_path: Path) -> None:
    manifest = _write_manifest(tmp_path, count=4)

    with pytest.raises(ValueError, match="Expected 5"):
        load_filings(manifest, fiscal_year=2025)


def test_all_mode_can_select_one_ticker(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        ["ingest_chunks.py", "--fiscal-year", "2025", "--all", "--ticker", "GOOGL"],
    )

    args = parse_args()

    assert args.all is True
    assert args.ticker == "GOOGL"
    assert args.fiscal_year == 2025


def test_find_source_span_advances_past_repeated_text() -> None:
    source = "repeat middle repeat"

    first = find_source_span(source, "repeat", 0)
    second = find_source_span(source, "repeat", first[1] if first else 0)

    assert first == (0, 6)
    assert second == (14, 20)
    assert find_source_span(source, "missing", 0) is None


def test_find_source_span_maps_normalized_docling_text_to_markdown() -> None:
    source = "| A | B |\n|---|---|\n\nHello, world!"

    span = find_source_span(source, "A = B\nHello world", 0)

    assert span is not None
    assert source[span[0] : span[1]] == "A | B |\n|---|---|\n\nHello, world"


def test_chunk_filing_uses_hierarchical_and_hybrid_chunkers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = "Heading\nHello world"
    markdown_path = tmp_path / "filing.md"
    markdown_path.write_text(source, encoding="utf-8")
    filing = Filing(
        ticker="AAPL",
        accession_number="accession-AAPL",
        fiscal_year=2025,
        filing_type="10-K",
        filing_date=date(2026, 1, 1),
        source_url="https://example.test/AAPL",
        markdown_path=markdown_path,
        relative_markdown_path="2025/aapl.md",
    )
    meta = SimpleNamespace(
        headings=["Heading"],
        model_dump=lambda **_: {"headings": ["Heading"]},
    )
    source_chunk = SimpleNamespace(text="Hello world", meta=meta)

    class FakeHierarchicalChunker:
        def chunk(self, *, dl_doc: object) -> list[object]:
            return [object(), object()]

    class FakeHybridChunker:
        def __init__(self, *, tokenizer: object) -> None:
            self.tokenizer = tokenizer

        def chunk(self, *, dl_doc: object) -> list[object]:
            return [source_chunk]

        def contextualize(self, *, chunk: object) -> str:
            return "Heading\nHello world"

    fake_module = ModuleType("docling.chunking")
    fake_module.HierarchicalChunker = FakeHierarchicalChunker
    fake_module.HybridChunker = FakeHybridChunker
    monkeypatch.setitem(sys.modules, "docling.chunking", fake_module)

    class FakeTokenizer:
        def count_tokens(self, text: str) -> int:
            return len(text.split())

    chunks_count, chunks = chunk_filing(
        filing,
        SimpleNamespace(
            convert=lambda **_: SimpleNamespace(
                document=SimpleNamespace(iterate_items=lambda: iter([]))
            )
        ),
        FakeTokenizer(),
    )

    assert chunks_count == 2
    assert len(chunks) == 1
    assert chunks[0].section == "Heading"
    assert chunks[0].token_count == 3
    assert (chunks[0].source_start, chunks[0].source_end) == (8, len(source))
    assert chunks[0].metadata["source_offset_status"] == "exact"
    assert chunks[0].metadata["ticker"] == "AAPL"
    assert chunks[0].metadata["fiscal_year"] == 2025
    assert chunks[0].metadata["filing_type"] == "10-K"
    assert chunks[0].metadata["page_references"] == []


def test_match_document_ids_requires_all_selected_filings() -> None:
    filings = [
        Filing(
            ticker="AAPL",
            accession_number="accession-AAPL",
            fiscal_year=2025,
            filing_type="10-K",
            filing_date=date(2026, 1, 1),
            source_url="https://example.test/AAPL",
            markdown_path=Path("aapl.md"),
            relative_markdown_path="aapl.md",
        )
    ]

    ids = match_document_ids(
        filings,
        {("AAPL", "accession-AAPL"): UUID("6dc1c1fa-1429-4c8c-92b0-1cd9bf1f95b7")},
    )

    assert ids[("AAPL", "accession-AAPL")] == UUID("6dc1c1fa-1429-4c8c-92b0-1cd9bf1f95b7")


def test_pending_chunks_skips_identical_and_rejects_changed_content() -> None:
    document_id = UUID("6dc1c1fa-1429-4c8c-92b0-1cd9bf1f95b7")
    doc_ids = {("AAPL", "accession-AAPL"): document_id}

    stored = ExistingChunk("content", "hash-content", has_citations=False)
    assert pending_chunks([_chunk()], doc_ids, {(document_id, 0): stored}) == []
    assert pending_chunks(
        [_chunk(content="changed")],
        doc_ids,
        {(document_id, 0): ExistingChunk("old", "hash-old", has_citations=False)},
    ) == [(_chunk(content="changed"), document_id)]
    with pytest.raises(ValueError, match="has citations"):
        pending_chunks(
            [_chunk(content="changed")],
            doc_ids,
            {(document_id, 0): ExistingChunk("old", "hash-old", has_citations=True)},
        )


def test_pending_chunks_reembeds_when_embedding_context_changes() -> None:
    document_id = UUID("6dc1c1fa-1429-4c8c-92b0-1cd9bf1f95b7")
    chunk = _chunk()
    existing = ExistingChunk("content", "old-hash", has_citations=False)

    assert pending_chunks(
        [chunk],
        {("AAPL", "accession-AAPL"): document_id},
        {(document_id, 0): existing},
    ) == [(chunk, document_id)]


def test_stale_chunk_indices_only_remove_uncited_rows() -> None:
    document_id = UUID("6dc1c1fa-1429-4c8c-92b0-1cd9bf1f95b7")
    chunks = [_chunk(chunk_index=0)]
    existing = {
        (document_id, 0): ExistingChunk("content", "hash-content", False),
        (document_id, 1): ExistingChunk("old", "old-hash", False),
    }

    assert stale_chunk_indices(chunks, document_id, existing) == [1]
    existing[(document_id, 1)] = ExistingChunk("old", "old-hash", True)
    with pytest.raises(ValueError, match="have citations"):
        stale_chunk_indices(chunks, document_id, existing)


def test_validate_embeddings_checks_count_dimensions_and_finite_values() -> None:
    vector = [0.1] * 1536
    validate_embeddings([vector], expected_count=1)

    with pytest.raises(ValueError, match="expected 1"):
        validate_embeddings([], expected_count=1)
    with pytest.raises(ValueError, match="expected 1536"):
        validate_embeddings([[0.1]], expected_count=1)
    with pytest.raises(ValueError, match="non-finite"):
        validate_embeddings([[float("nan")] * 1536], expected_count=1)


def test_embed_texts_sends_dimensions_and_validates_ordered_response() -> None:
    response = SimpleNamespace(
        data=[
            SimpleNamespace(index=1, embedding=[0.2] * 1536),
            SimpleNamespace(index=0, embedding=[0.1] * 1536),
        ]
    )

    class FakeEmbeddings:
        def create(self, **kwargs: object) -> SimpleNamespace:
            assert kwargs["model"] == "text-embedding-v4"
            assert kwargs["input"] == ["first", "second"]
            assert kwargs["dimensions"] == 1536
            assert kwargs["encoding_format"] == "float"
            return response

    client = SimpleNamespace(embeddings=FakeEmbeddings())

    vectors = embed_texts(client, ["first", "second"], "text-embedding-v4")

    assert vectors == [[0.1] * 1536, [0.2] * 1536]


def test_embed_texts_rejects_batches_larger_than_provider_limit() -> None:
    client = SimpleNamespace(
        embeddings=SimpleNamespace(create=lambda **_: pytest.fail("API called"))
    )

    with pytest.raises(ValueError, match="maximum is 10"):
        embed_texts(client, ["text"] * 11, "text-embedding-v4")


def test_write_chunks_uses_citation_safe_upsert_and_generated_search_vector() -> None:
    chunk = _chunk()
    document_id = UUID("6dc1c1fa-1429-4c8c-92b0-1cd9bf1f95b7")
    statements = []

    class FakeConnection:
        def execute(self, statement: object, rows: list[dict[str, object]]) -> SimpleNamespace:
            statements.append(statement)
            return SimpleNamespace(
                all=lambda: [(row["document_id"], row["chunk_index"]) for row in rows]
            )

    class FakeEngine:
        @contextmanager
        def begin(self):
            yield FakeConnection()

    write_chunks(FakeEngine(), [(chunk, document_id)], [[0.1] * 1536])

    compiled = str(statements[0].compile(dialect=postgresql.dialect()))
    assert "ON CONFLICT (document_id, chunk_index) DO UPDATE" in compiled
    assert "message_citations" in compiled
    assert "search_vector =" not in compiled
