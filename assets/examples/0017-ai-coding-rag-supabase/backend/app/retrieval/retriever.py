from __future__ import annotations

from collections.abc import Callable, Mapping
from uuid import UUID

from sqlalchemy.engine import URL, make_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import Settings, settings
from app.retrieval.embeddings import QueryEmbedder, QwenQueryEmbedder
from app.retrieval.fusion import FusedHit, SearchHit, reciprocal_rank_fusion
from app.retrieval.models import (
    MAX_NEIGHBOR_WINDOW,
    MAX_RESULTS,
    Passage,
    PassageWindow,
    RetrievalEvidence,
    SearchFilters,
    validate_query,
)
from app.retrieval.queries import (
    CANDIDATE_LIMIT,
    VECTOR_DIMENSIONS,
    chunk_lookup_query,
    lexical_candidates_query,
    neighboring_chunks_query,
    passage_hydration_query,
    semantic_candidates_query,
)

DATABASE_STATEMENT_TIMEOUT_MS = 15_000


class HybridRetriever:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        embedder: QueryEmbedder,
        *,
        engine: AsyncEngine | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._embedder = embedder
        self._engine = engine

    async def search_filings(
        self,
        query: str,
        filters: SearchFilters | None = None,
        *,
        limit: int = MAX_RESULTS,
        report_progress: Callable[[str], None] | None = None,
    ) -> list[Passage]:
        normalized_query = validate_query(query)
        if isinstance(limit, bool) or not 1 <= limit <= MAX_RESULTS:
            raise ValueError(f"Search result limit must be between 1 and {MAX_RESULTS}.")

        if report_progress is not None:
            report_progress("Embedding your question with Qwen...")
        embedding = await self._embedder.embed_query(normalized_query)
        if len(embedding) != VECTOR_DIMENSIONS:
            raise ValueError(f"Query embedding must contain {VECTOR_DIMENSIONS} values.")

        if report_progress is not None:
            report_progress("Searching filing chunks in PostgreSQL...")
        async with self._session_factory() as session:
            semantic_rows = (
                await session.execute(
                    semantic_candidates_query(embedding, filters, CANDIDATE_LIMIT)
                )
            ).all()
            lexical_rows = (
                await session.execute(
                    lexical_candidates_query(normalized_query, filters, CANDIDATE_LIMIT)
                )
            ).all()
            fused = reciprocal_rank_fusion(
                _search_hits(semantic_rows),
                _search_hits(lexical_rows),
                limit=limit,
            )
            if not fused:
                return []

            if report_progress is not None:
                report_progress("Fetching passage text and filing metadata...")
            rows = (
                (await session.execute(passage_hydration_query([hit.chunk_id for hit in fused])))
                .mappings()
                .all()
            )

        passages = {passage.chunk_id: passage for row in rows if (passage := _to_passage(row))}
        return [
            passages[hit.chunk_id].model_copy(update={"retrieval": _retrieval_evidence(hit)})
            for hit in fused
            if hit.chunk_id in passages
        ]

    async def read_chunk(self, chunk_id: UUID) -> Passage | None:
        async with self._session_factory() as session:
            row = (await session.execute(chunk_lookup_query(chunk_id))).mappings().one_or_none()
        if row is None:
            return None
        return _to_passage(row)

    async def read_surrounding_chunks(
        self,
        chunk_id: UUID,
        *,
        window: int = MAX_NEIGHBOR_WINDOW,
    ) -> PassageWindow | None:
        if isinstance(window, bool) or not 0 <= window <= MAX_NEIGHBOR_WINDOW:
            raise ValueError(f"Neighbor window must be between 0 and {MAX_NEIGHBOR_WINDOW}.")

        async with self._session_factory() as session:
            target_row = (
                (await session.execute(chunk_lookup_query(chunk_id))).mappings().one_or_none()
            )
            if target_row is None:
                return None
            rows = (
                (
                    await session.execute(
                        neighboring_chunks_query(
                            target_row["document_id"],
                            max(0, target_row["chunk_index"] - window),
                            target_row["chunk_index"] + window,
                        )
                    )
                )
                .mappings()
                .all()
            )

        passages = {passage.chunk_index: passage for row in rows if (passage := _to_passage(row))}
        target = passages.get(target_row["chunk_index"])
        if target is None:
            return None
        return PassageWindow(
            target=target,
            before=[
                passages[index]
                for index in sorted(passages)
                if target.chunk_index - window <= index < target.chunk_index
            ],
            after=[
                passages[index]
                for index in sorted(passages)
                if target.chunk_index < index <= target.chunk_index + window
            ],
        )

    async def aclose(self) -> None:
        try:
            await self._embedder.aclose()
        finally:
            if self._engine is not None:
                await self._engine.dispose()


def create_retriever(config: Settings = settings) -> HybridRetriever:
    if not config.database_url:
        raise RuntimeError("DATABASE_URL is required for retrieval.")
    if config.qwen_embedding_dimensions != VECTOR_DIMENSIONS:
        raise ValueError(
            f"QWEN_EMBEDDING_DIMENSIONS must be {VECTOR_DIMENSIONS} to match document_chunks."
        )

    database_url = _async_postgres_url(config.database_url)
    embedder = QwenQueryEmbedder(config)
    engine = create_async_engine(
        database_url,
        pool_pre_ping=True,
        connect_args={"options": f"-c statement_timeout={DATABASE_STATEMENT_TIMEOUT_MS}"},
    )
    return HybridRetriever(
        async_sessionmaker(engine, expire_on_commit=False),
        embedder,
        engine=engine,
    )


def _async_postgres_url(database_url: str) -> URL:
    url = make_url(database_url)
    if url.drivername in {"postgres", "postgresql", "postgresql+psycopg2"}:
        return url.set(drivername="postgresql+psycopg")
    if url.drivername != "postgresql+psycopg":
        raise ValueError("DATABASE_URL must use a PostgreSQL connection.")
    return url


def _search_hits(rows: list[tuple[UUID, float]]) -> list[SearchHit]:
    return [SearchHit(chunk_id=chunk_id, score=float(score)) for chunk_id, score in rows]


def _retrieval_evidence(hit: FusedHit) -> RetrievalEvidence:
    return RetrievalEvidence(
        fused_score=hit.fused_score,
        semantic_rank=hit.semantic_rank,
        semantic_score=hit.semantic_score,
        lexical_rank=hit.lexical_rank,
        lexical_score=hit.lexical_score,
    )


def _to_passage(row: Mapping[str, object]) -> Passage:
    page_references = row.get("page_references")
    return Passage.model_validate(
        {
            **row,
            "chunk_metadata": {"page_references": page_references}
            if isinstance(page_references, list)
            else {},
            "document_metadata": {},
        }
    )
