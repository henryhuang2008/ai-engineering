from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field
from uuid import UUID

from app.retrieval.models import Passage, PassageWindow, SearchFilters
from app.retrieval.retriever import HybridRetriever

ProgressReporter = Callable[[str], None]


@dataclass
class DocumentAgentDeps:
    user_id: UUID
    thread_id: UUID
    retriever: HybridRetriever
    conversation_context: str
    report_progress: ProgressReporter | None = None
    passages: dict[UUID, Passage] = field(default_factory=dict)
    _search_cache: dict[tuple[str, SearchFilters | None], list[Passage]] = field(
        default_factory=dict
    )
    _search_locks: dict[tuple[str, SearchFilters | None], asyncio.Lock] = field(
        default_factory=dict
    )

    async def search_filings(
        self,
        query: str,
        filters: SearchFilters | None = None,
        *,
        limit: int,
    ) -> list[Passage]:
        key = (query.strip(), filters)
        cached = self._search_cache.get(key)
        if cached is not None:
            return cached

        lock = self._search_locks.setdefault(key, asyncio.Lock())
        async with lock:
            cached = self._search_cache.get(key)
            if cached is not None:
                return cached
            passages = await self.retriever.search_filings(
                query,
                filters,
                limit=limit,
                report_progress=self.report_progress,
            )
            self._search_cache[key] = passages
            return passages

    def remember(self, passage: Passage) -> None:
        self.passages[passage.chunk_id] = passage

    def remember_window(self, window: PassageWindow) -> None:
        self.remember(window.target)
        for passage in (*window.before, *window.after):
            self.remember(passage)
