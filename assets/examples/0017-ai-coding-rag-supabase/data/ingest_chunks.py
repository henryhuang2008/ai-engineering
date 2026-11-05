# /// script
# requires-python = ">=3.12"
# ///
from __future__ import annotations

import argparse
import hashlib
import json
import math
from bisect import bisect_left
from dataclasses import dataclass
from datetime import date
from pathlib import Path, PurePosixPath
from typing import Any
from uuid import UUID

from sqlalchemy import create_engine, delete, exists, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.engine import URL, make_url

DATA_DIR = Path(__file__).resolve().parent
DEFAULT_MANIFEST = DATA_DIR / "markdown" / "manifest.json"
DEFAULT_FISCAL_YEAR = 2025
EXPECTED_2025_FILINGS = 5
EMBEDDING_TOKEN_LIMIT = 8192
CHUNK_TOKEN_LIMIT = 7000
EMBEDDING_DIMENSIONS = 1536
EMBEDDING_MODEL = "text-embedding-v4"
TOKENIZER_MODEL = "Qwen/Qwen3-Embedding-0.6B"
MAX_EMBEDDING_BATCH_SIZE = 10
MAX_DOCUMENT_CHARS = 255
# Published synchronous prices vary by region; this is the higher of the
# documented Beijing and Singapore prices and is only an estimate.
ESTIMATED_PRICE_CNY_PER_1000_TOKENS = 0.000514


@dataclass(frozen=True)
class Filing:
    ticker: str
    accession_number: str
    fiscal_year: int
    filing_type: str
    filing_date: date
    source_url: str
    markdown_path: Path
    relative_markdown_path: str


@dataclass(frozen=True)
class Chunk:
    ticker: str
    accession_number: str
    chunk_index: int
    content: str
    embedding_text: str
    token_count: int
    section: str | None
    source_start: int | None
    source_end: int | None
    metadata: dict[str, Any]


@dataclass(frozen=True)
class ExistingChunk:
    content: str
    embedding_text_sha256: str | None
    has_citations: bool


@dataclass(frozen=True)
class SourceTextIndex:
    source: str
    normalized_text: str
    normalized_offsets: list[int]

    @classmethod
    def build(cls, source: str) -> SourceTextIndex:
        normalized_chars = []
        offsets = []
        for offset, char in enumerate(source):
            if char.isalnum():
                normalized_chars.append(char)
                offsets.append(offset)
        return cls(source, "".join(normalized_chars), offsets)

    def find_span(
        self, chunk_text: str, cursor: int
    ) -> tuple[tuple[int, int] | None, str]:
        exact_start = self.source.find(chunk_text, cursor)
        if exact_start >= 0:
            return (exact_start, exact_start + len(chunk_text)), "exact"

        normalized_chunk = "".join(char for char in chunk_text if char.isalnum())
        if not normalized_chunk:
            return None, "unavailable"
        normalized_cursor = bisect_left(self.normalized_offsets, cursor)
        match_start = self.normalized_text.find(normalized_chunk, normalized_cursor)
        if match_start < 0:
            return None, "unavailable"
        source_start = self.normalized_offsets[match_start]
        source_end = (
            self.normalized_offsets[match_start + len(normalized_chunk) - 1] + 1
        )
        return (source_start, source_end), "normalized"


def _relative_path(value: str) -> PurePosixPath:
    path = PurePosixPath(value.replace("\\", "/"))
    if path.is_absolute() or not path.parts or ".." in path.parts:
        raise ValueError(f"Manifest path must be relative to Markdown: {value!r}")
    return path


def load_filings(
    manifest_path: Path,
    fiscal_year: int,
    ticker: str | None = None,
) -> list[Filing]:
    manifest_path = manifest_path.resolve()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    records = manifest.get("filings")
    if not isinstance(records, list):
        raise ValueError(f"Expected a 'filings' list in {manifest_path}")

    markdown_root = manifest_path.parent.resolve()
    filings = []
    seen_keys: set[tuple[str, str]] = set()
    for record in records:
        if not isinstance(record, dict):
            raise ValueError(f"Invalid filing entry in {manifest_path}: {record!r}")
        report_date = record.get("report_date")
        filing_date = date.fromisoformat(record["filing_date"])
        record_year = (
            date.fromisoformat(report_date).year if report_date else filing_date.year
        )
        if record_year != fiscal_year or (ticker and record.get("ticker") != ticker):
            continue

        record_ticker = record.get("ticker")
        accession_number = record.get("accession_number")
        if not isinstance(record_ticker, str) or not isinstance(accession_number, str):
            raise ValueError(f"Filing is missing ticker/accession number: {record!r}")
        key = (record_ticker, accession_number)
        if key in seen_keys:
            raise ValueError(f"Duplicate filing in manifest: {key}")
        seen_keys.add(key)

        local_path = record.get("local_path")
        if not isinstance(local_path, str):
            raise ValueError(f"Filing is missing its local_path: {record!r}")
        relative_path = _relative_path(local_path)
        markdown_path = markdown_root.joinpath(*relative_path.parts).resolve()
        if not markdown_path.is_relative_to(markdown_root):
            raise ValueError(f"Manifest path escapes Markdown directory: {local_path}")
        if markdown_path.suffix.casefold() != ".md" or not markdown_path.is_file():
            raise FileNotFoundError(f"Markdown filing not found: {markdown_path}")

        filings.append(
            Filing(
                ticker=record_ticker,
                accession_number=accession_number,
                fiscal_year=record_year,
                filing_type=record["form"],
                filing_date=filing_date,
                source_url=record["source_url"],
                markdown_path=markdown_path,
                relative_markdown_path=relative_path.as_posix(),
            )
        )

    filings.sort(key=lambda filing: (filing.ticker, filing.accession_number))
    if not filings:
        raise ValueError(f"No filings found for fiscal year {fiscal_year}.")
    if (
        fiscal_year == DEFAULT_FISCAL_YEAR
        and ticker is None
        and len(filings) != EXPECTED_2025_FILINGS
    ):
        raise ValueError(
            f"Expected {EXPECTED_2025_FILINGS} fiscal-year-2025 filings; found {len(filings)}."
        )
    return filings


def find_source_span(
    source: str, chunk_text: str, cursor: int
) -> tuple[int, int] | None:
    span, _ = SourceTextIndex.build(source).find_span(chunk_text, cursor)
    return span


def chunk_filing(
    filing: Filing,
    converter: Any,
    tokenizer: Any,
) -> tuple[int, list[Chunk]]:
    from docling.chunking import HierarchicalChunker, HybridChunker

    markdown = filing.markdown_path.read_text(encoding="utf-8")
    document = converter.convert(source=filing.markdown_path).document
    source_index = SourceTextIndex.build(markdown)
    hierarchical_count = sum(1 for _ in HierarchicalChunker().chunk(dl_doc=document))
    hybrid_chunker = HybridChunker(tokenizer=tokenizer)
    chunks = []
    cursor = 0
    for chunk_index, docling_chunk in enumerate(hybrid_chunker.chunk(dl_doc=document)):
        content = docling_chunk.text.strip()
        embedding_text = hybrid_chunker.contextualize(chunk=docling_chunk).strip()
        if not content or not embedding_text:
            raise ValueError(
                f"Docling produced an empty chunk for "
                f"{filing.ticker}/{filing.accession_number} at index {chunk_index}."
            )

        token_count = tokenizer.count_tokens(embedding_text)
        if token_count > CHUNK_TOKEN_LIMIT or token_count > EMBEDDING_TOKEN_LIMIT:
            raise ValueError(
                f"Chunk {filing.ticker}/{filing.accession_number}/{chunk_index} has "
                f"{token_count} tokens; limits are {CHUNK_TOKEN_LIMIT} and "
                f"{EMBEDDING_TOKEN_LIMIT}."
            )

        meta = docling_chunk.meta.model_dump(mode="json", exclude_none=True)
        headings = docling_chunk.meta.headings or []
        section = " > ".join(headings)[:MAX_DOCUMENT_CHARS] or None
        span, source_offset_status = source_index.find_span(content, cursor)
        if span is not None:
            cursor = span[1]
        page_references = sorted(
            {
                provenance["page_no"]
                for item in meta.get("doc_items", [])
                for provenance in item.get("prov", [])
                if isinstance(provenance, dict) and "page_no" in provenance
            }
        )

        chunks.append(
            Chunk(
                ticker=filing.ticker,
                accession_number=filing.accession_number,
                chunk_index=chunk_index,
                content=content,
                embedding_text=embedding_text,
                token_count=token_count,
                section=section,
                source_start=span[0] if span else None,
                source_end=span[1] if span else None,
                metadata={
                    "markdown_local_path": filing.relative_markdown_path,
                    "ticker": filing.ticker,
                    "fiscal_year": filing.fiscal_year,
                    "filing_type": filing.filing_type,
                    "filing_date": filing.filing_date.isoformat(),
                    "accession_number": filing.accession_number,
                    "source_url": filing.source_url,
                    "page_references": page_references,
                    "docling_metadata": meta,
                    "embedding_model": EMBEDDING_MODEL,
                    "embedding_dimensions": EMBEDDING_DIMENSIONS,
                    "source_offset_status": source_offset_status,
                    "embedding_text_sha256": hashlib.sha256(
                        embedding_text.encode("utf-8")
                    ).hexdigest(),
                },
            )
        )
    if not chunks:
        raise ValueError(f"Docling produced no chunks for {filing.markdown_path}")
    return hierarchical_count, chunks


def build_tokenizer() -> Any:
    from docling_core.transforms.chunker.tokenizer.huggingface import (
        HuggingFaceTokenizer,
    )
    from transformers import AutoTokenizer

    return HuggingFaceTokenizer(
        tokenizer=AutoTokenizer.from_pretrained(
            TOKENIZER_MODEL, trust_remote_code=False
        ),
        max_tokens=CHUNK_TOKEN_LIMIT,
    )


def _database_url() -> URL:
    from app.config import settings

    if not settings.database_url:
        raise RuntimeError("DATABASE_URL is required for database access.")
    url = make_url(settings.database_url)
    if url.drivername in {"postgres", "postgresql", "postgresql+psycopg2"}:
        return url.set(drivername="postgresql+psycopg")
    if url.drivername != "postgresql+psycopg":
        raise ValueError("DATABASE_URL must use a PostgreSQL connection.")
    return url


def load_database_documents(
    engine: Any, fiscal_year: int
) -> dict[tuple[str, str], UUID]:
    from app.database.models.source_document import SourceDocument

    table = SourceDocument.__table__
    statement = select(table.c.id, table.c.ticker, table.c.accession_number).where(
        table.c.fiscal_year == fiscal_year
    )
    with engine.connect() as connection:
        rows = connection.execute(statement).mappings().all()
    return {(row["ticker"], row["accession_number"]): row["id"] for row in rows}


def match_document_ids(
    filings: list[Filing],
    database_documents: dict[tuple[str, str], UUID],
) -> dict[tuple[str, str], UUID]:
    ids = {}
    for filing in filings:
        key = (filing.ticker, filing.accession_number)
        document_id = database_documents.get(key)
        if document_id is None:
            raise ValueError(
                f"No source_documents row for fiscal-year-{filing.fiscal_year} "
                f"filing {filing.ticker}/{filing.accession_number}."
            )
        ids[key] = document_id
    if len(database_documents) != len(filings):
        raise ValueError(
            f"Expected {len(filings)} source_documents rows for fiscal year "
            f"{filings[0].fiscal_year}; found {len(database_documents)}."
        )
    return ids


def select_existing_chunks(
    engine: Any, document_ids: set[UUID]
) -> dict[tuple[UUID, int], ExistingChunk]:
    from app.database.models.document_chunk import DocumentChunk
    from app.database.models.message_citation import MessageCitation

    table = DocumentChunk.__table__
    citations = MessageCitation.__table__
    has_citations = exists(
        select(1).select_from(citations).where(citations.c.chunk_id == table.c.id)
    )
    statement = select(
        table.c.document_id,
        table.c.chunk_index,
        table.c.content,
        table.c["metadata"],
        has_citations.label("has_citations"),
    ).where(table.c.document_id.in_(document_ids))
    with engine.connect() as connection:
        rows = connection.execute(statement).mappings().all()
    return {
        (row["document_id"], row["chunk_index"]): ExistingChunk(
            content=row["content"],
            embedding_text_sha256=(row["metadata"] or {}).get("embedding_text_sha256"),
            has_citations=row["has_citations"],
        )
        for row in rows
    }


def pending_chunks(
    chunks: list[Chunk],
    document_ids: dict[tuple[str, str], UUID],
    existing: dict[tuple[UUID, int], ExistingChunk],
) -> list[tuple[Chunk, UUID]]:
    pending = []
    for chunk in chunks:
        document_id = document_ids[(chunk.ticker, chunk.accession_number)]
        key = (document_id, chunk.chunk_index)
        previous = existing.get(key)
        if (
            previous is not None
            and previous.has_citations
            and (
                previous.content != chunk.content
                or previous.embedding_text_sha256
                != chunk.metadata["embedding_text_sha256"]
            )
        ):
            raise ValueError(
                f"Stored chunk changed for "
                f"{chunk.ticker}/{chunk.accession_number}/{chunk.chunk_index}; "
                "it has citations, so refusing to replace the cited passage."
            )
        if previous is None or (
            previous.content != chunk.content
            or previous.embedding_text_sha256 != chunk.metadata["embedding_text_sha256"]
        ):
            pending.append((chunk, document_id))
    return pending


def stale_chunk_indices(
    chunks: list[Chunk],
    document_id: UUID,
    existing: dict[tuple[UUID, int], ExistingChunk],
) -> list[int]:
    expected_indices = {chunk.chunk_index for chunk in chunks}
    stale = [
        chunk_index
        for (stored_document_id, chunk_index), stored in existing.items()
        if stored_document_id == document_id
        and chunk_index not in expected_indices
        and stored.has_citations
    ]
    if stale:
        raise ValueError(
            f"Stale chunks {sorted(stale)} for document {document_id} have citations; "
            "refusing to remove cited chunks."
        )
    return [
        chunk_index
        for stored_document_id, chunk_index in existing
        if stored_document_id == document_id and chunk_index not in expected_indices
    ]


def validate_embeddings(vectors: list[list[float]], expected_count: int) -> None:
    if len(vectors) != expected_count:
        raise ValueError(
            f"Embedding service returned {len(vectors)} vectors; expected {expected_count}."
        )
    for index, vector in enumerate(vectors):
        if len(vector) != EMBEDDING_DIMENSIONS:
            raise ValueError(
                f"Embedding {index} has {len(vector)} dimensions; expected {EMBEDDING_DIMENSIONS}."
            )
        if not all(math.isfinite(value) for value in vector):
            raise ValueError(f"Embedding {index} contains a non-finite value.")


def embed_texts(client: Any, texts: list[str], model: str) -> list[list[float]]:
    if not texts:
        return []
    if len(texts) > MAX_EMBEDDING_BATCH_SIZE:
        raise ValueError(
            f"Embedding request has {len(texts)} items; maximum is {MAX_EMBEDDING_BATCH_SIZE}."
        )
    response = client.embeddings.create(
        model=model,
        input=texts,
        dimensions=EMBEDDING_DIMENSIONS,
        encoding_format="float",
    )
    indexed = sorted(response.data, key=lambda item: item.index)
    if [item.index for item in indexed] != list(range(len(texts))):
        raise ValueError("Embedding response indices are missing or duplicated.")
    vectors = [list(item.embedding) for item in indexed]
    validate_embeddings(vectors, len(texts))
    return vectors


def write_chunks(
    engine: Any, pending: list[tuple[Chunk, UUID]], vectors: list[list[float]]
) -> None:
    from app.database.models.document_chunk import DocumentChunk
    from app.database.models.message_citation import MessageCitation

    if len(pending) != len(vectors):
        raise ValueError("Chunk and embedding counts do not match.")
    table = DocumentChunk.__table__
    citations = MessageCitation.__table__
    cited_chunk = exists(
        select(1).select_from(citations).where(citations.c.chunk_id == table.c.id)
    )
    insert_statement = insert(table)
    for start in range(0, len(pending), MAX_EMBEDDING_BATCH_SIZE):
        chunk_batch = pending[start : start + MAX_EMBEDDING_BATCH_SIZE]
        vector_batch = vectors[start : start + MAX_EMBEDDING_BATCH_SIZE]
        rows = [
            {
                "document_id": document_id,
                "chunk_index": chunk.chunk_index,
                "content": chunk.content,
                "section": chunk.section,
                "token_count": chunk.token_count,
                "source_start": chunk.source_start,
                "source_end": chunk.source_end,
                "embedding": vector,
                "metadata": chunk.metadata,
            }
            for (chunk, document_id), vector in zip(
                chunk_batch, vector_batch, strict=True
            )
        ]
        statement = insert_statement.on_conflict_do_update(
            index_elements=[table.c.document_id, table.c.chunk_index],
            set_={
                "content": insert_statement.excluded.content,
                "section": insert_statement.excluded.section,
                "token_count": insert_statement.excluded.token_count,
                "source_start": insert_statement.excluded.source_start,
                "source_end": insert_statement.excluded.source_end,
                "embedding": insert_statement.excluded.embedding,
                "metadata": insert_statement.excluded["metadata"],
                "updated_at": func.now(),
            },
            where=~cited_chunk,
        ).returning(table.c.document_id, table.c.chunk_index)
        with engine.begin() as connection:
            written = connection.execute(statement, rows).all()
            if len(written) != len(rows):
                raise ValueError(
                    "A chunk gained a citation during ingestion; refusing to replace "
                    "the cited chunk."
                )


def delete_stale_chunks(
    engine: Any,
    document_id: UUID,
    stale_indices: list[int],
) -> None:
    if not stale_indices:
        return
    from app.database.models.document_chunk import DocumentChunk
    from app.database.models.message_citation import MessageCitation

    table = DocumentChunk.__table__
    citations = MessageCitation.__table__
    has_citations = exists(
        select(1).select_from(citations).where(citations.c.chunk_id == table.c.id)
    )
    statement = delete(table).where(
        table.c.document_id == document_id,
        table.c.chunk_index.in_(stale_indices),
        ~has_citations,
    )
    with engine.begin() as connection:
        deleted = connection.execute(statement).rowcount
        if deleted != len(stale_indices):
            raise ValueError(
                "A stale chunk gained a citation during ingestion; refusing to remove it."
            )


def _estimate_cost_cny(tokens: int) -> float:
    return tokens / 1000 * ESTIMATED_PRICE_CNY_PER_1000_TOKENS


def _print_summary(
    filings: list[Filing],
    document_chunks: list[tuple[Filing, int, list[Chunk]]],
) -> None:
    total_tokens = 0
    all_chunks = [chunk for _, _, chunks in document_chunks for chunk in chunks]
    print(f"Fiscal year: {filings[0].fiscal_year}; filings: {len(filings)}")
    for filing, hierarchical_count, chunks in document_chunks:
        tokens = sum(chunk.token_count for chunk in chunks)
        total_tokens += tokens
        print(
            f"{filing.ticker} {filing.accession_number}: "
            f"{hierarchical_count} hierarchical / {len(chunks)} hybrid chunks, "
            f"{tokens:,} embedding tokens"
        )
    print(
        f"Total hybrid chunks: {sum(len(chunks) for _, _, chunks in document_chunks):,}"
    )
    print(f"Estimated input tokens: {total_tokens:,}")
    token_counts = [chunk.token_count for chunk in all_chunks]
    exact_offsets = sum(
        chunk.metadata["source_offset_status"] == "exact" for chunk in all_chunks
    )
    normalized_offsets = sum(
        chunk.metadata["source_offset_status"] == "normalized" for chunk in all_chunks
    )
    unmapped_offsets = sum(
        chunk.metadata["source_offset_status"] == "unavailable" for chunk in all_chunks
    )
    print(f"Contextualized chunk tokens: {min(token_counts)}-{max(token_counts)}")
    print(
        f"Source offsets: {exact_offsets} exact, {normalized_offsets} normalized, "
        f"{unmapped_offsets} unavailable"
    )
    print(
        f"Estimated API cost: CNY {_estimate_cost_cny(total_tokens):.4f} "
        f"(using a conservative published Beijing/Singapore rate)"
    )


def run(args: argparse.Namespace) -> None:
    from app.config import settings
    from docling.document_converter import DocumentConverter

    if settings.qwen_embedding_dimensions != EMBEDDING_DIMENSIONS:
        raise ValueError(
            f"QWEN_EMBEDDING_DIMENSIONS must be {EMBEDDING_DIMENSIONS} "
            "to match document_chunks.embedding."
        )
    if settings.qwen_embedding_model != EMBEDDING_MODEL:
        raise ValueError(
            f"This pipeline requires QWEN_EMBEDDING_MODEL={EMBEDDING_MODEL}."
        )

    all_filings = load_filings(args.manifest, args.fiscal_year)
    filings = (
        [filing for filing in all_filings if filing.ticker == args.ticker]
        if args.ticker
        else all_filings
    )
    tokenizer = build_tokenizer()
    converter = DocumentConverter()
    document_chunks = []
    for filing in filings:
        hierarchical_count, chunks = chunk_filing(filing, converter, tokenizer)
        document_chunks.append((filing, hierarchical_count, chunks))

    _print_summary(filings, document_chunks)
    if not args.pilot and not args.all:
        print("Dry run only. No embedding requests or database writes were made.")
        return

    if args.pilot:
        if not args.ticker:
            raise ValueError("--pilot requires --ticker to identify one filing.")
        selected = [
            (filing, hierarchical_count, chunks)
            for filing, hierarchical_count, chunks in document_chunks
            if filing.ticker == args.ticker
        ]
        if len(selected) != 1:
            raise ValueError(f"Expected one fiscal-year filing for {args.ticker}.")
        filing, _, chunks = selected[0]
        selected_chunks = chunks[:1]
    else:
        selected_chunks = [
            chunk for _, _, chunks in document_chunks for chunk in chunks
        ]

    if not selected_chunks:
        raise ValueError("No chunks selected for embedding.")

    engine = create_engine(_database_url(), pool_pre_ping=True)
    try:
        source_ids = load_database_documents(engine, args.fiscal_year)
        document_ids = match_document_ids(all_filings, source_ids)
        selected_document_ids = {
            document_ids[(filing.ticker, filing.accession_number)]
            for filing, _, _ in document_chunks
        }
        existing = select_existing_chunks(engine, selected_document_ids)
        resolved_pending = pending_chunks(selected_chunks, document_ids, existing)
        stale_by_document = {}
        if args.all:
            for filing, _, chunks in document_chunks:
                document_id = document_ids[(filing.ticker, filing.accession_number)]
                stale_by_document[document_id] = stale_chunk_indices(
                    chunks, document_id, existing
                )
        if not resolved_pending:
            print(
                "Selected chunks already exist unchanged; no embedding call was made."
            )
            if args.all:
                for document_id, stale_indices in stale_by_document.items():
                    delete_stale_chunks(engine, document_id, stale_indices)
                    if stale_indices:
                        print(
                            f"Removed {len(stale_indices)} stale chunks for {document_id}."
                        )
            return
        if args.pilot and len(resolved_pending) != 1:
            raise ValueError(
                f"Pilot mode must embed exactly one pending chunk, got {len(resolved_pending)}."
            )

        selected_tokens = sum(chunk.token_count for chunk, _ in resolved_pending)
        estimated_cost = _estimate_cost_cny(selected_tokens)
        print(
            f"Chunks to embed or re-embed: {len(resolved_pending)}; "
            f"input tokens: {selected_tokens:,}; estimated cost: CNY {estimated_cost:.4f}"
        )
        if args.max_cost_cny is None:
            raise ValueError(
                "Live embedding requires --max-cost-cny to acknowledge and cap the estimated cost."
            )
        if estimated_cost > args.max_cost_cny:
            raise ValueError(
                f"Estimated cost CNY {estimated_cost:.4f} exceeds "
                f"--max-cost-cny {args.max_cost_cny:.4f}; no API request was made."
            )
        if not settings.dashscope_api_key or not settings.qwen_base_url:
            raise RuntimeError(
                "DASHSCOPE_API_KEY and QWEN_BASE_URL must be configured before live ingestion."
            )

        from app.database.models.document_chunk import DocumentChunk
        from openai import OpenAI

        client = OpenAI(
            api_key=settings.dashscope_api_key.get_secret_value(),
            base_url=settings.qwen_base_url,
            timeout=60.0,
            max_retries=2,
        )
        for start in range(0, len(resolved_pending), MAX_EMBEDDING_BATCH_SIZE):
            pending_batch = resolved_pending[start : start + MAX_EMBEDDING_BATCH_SIZE]
            vectors = embed_texts(
                client,
                [chunk.embedding_text for chunk, _ in pending_batch],
                settings.qwen_embedding_model,
            )
            write_chunks(engine, pending_batch, vectors)
        if args.all:
            for document_id, stale_indices in stale_by_document.items():
                delete_stale_chunks(engine, document_id, stale_indices)
                if stale_indices:
                    print(
                        f"Removed {len(stale_indices)} stale chunks for {document_id}."
                    )
        if args.pilot:
            chunk, document_id = resolved_pending[0]
            chunk_table = DocumentChunk.__table__
            with engine.connect() as connection:
                row = (
                    connection.execute(
                        select(
                            chunk_table.c.content,
                            chunk_table.c.token_count,
                            chunk_table.c.embedding,
                            chunk_table.c.search_vector,
                        ).where(
                            chunk_table.c.document_id == document_id,
                            chunk_table.c.chunk_index == chunk.chunk_index,
                        )
                    )
                    .mappings()
                    .one()
                )
            if (
                row["content"] != chunk.content
                or row["token_count"] != chunk.token_count
            ):
                raise RuntimeError(
                    "Pilot chunk read-back did not match the inserted record."
                )
            if (
                row["search_vector"] is None
                or len(row["embedding"]) != EMBEDDING_DIMENSIONS
            ):
                raise RuntimeError(
                    "Pilot chunk is missing its generated search vector or embedding."
                )
            print(
                f"Pilot verified: {chunk.ticker}/{chunk.accession_number}/"
                f"{chunk.chunk_index}, document_id={document_id}"
            )
    finally:
        engine.dispose()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Chunk fiscal-year filings and optionally embed/store them."
    )
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--fiscal-year", type=int, default=DEFAULT_FISCAL_YEAR)
    parser.add_argument("--ticker", choices=("AAPL", "AMZN", "GOOGL", "MSFT", "NVDA"))
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--pilot", action="store_true", help="Embed and insert exactly one chunk."
    )
    mode.add_argument(
        "--all",
        action="store_true",
        help="Embed, upsert, and reconcile all chunks for the selected filings.",
    )
    parser.add_argument(
        "--max-cost-cny",
        type=float,
        help="Required for paid modes; abort before API calls if the estimate exceeds this cap.",
    )
    args = parser.parse_args()
    if args.pilot and not args.ticker:
        parser.error("--pilot requires --ticker")
    if args.max_cost_cny is not None and args.max_cost_cny < 0:
        parser.error("--max-cost-cny must be non-negative")
    return args


if __name__ == "__main__":
    run(parse_args())
