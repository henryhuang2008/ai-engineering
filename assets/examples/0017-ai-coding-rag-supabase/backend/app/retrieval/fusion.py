from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class SearchHit:
    chunk_id: UUID
    score: float


@dataclass(frozen=True)
class FusedHit:
    chunk_id: UUID
    fused_score: float
    semantic_rank: int | None
    semantic_score: float | None
    lexical_rank: int | None
    lexical_score: float | None


def reciprocal_rank_fusion(
    semantic: list[SearchHit],
    lexical: list[SearchHit],
    *,
    limit: int,
    k: int = 60,
) -> list[FusedHit]:
    if limit < 1:
        raise ValueError("Fusion result limit must be at least one.")
    if k < 1:
        raise ValueError("RRF k must be at least one.")

    hits: dict[UUID, FusedHit] = {}
    for retriever, ranking in (("semantic", semantic), ("lexical", lexical)):
        for rank, hit in enumerate(ranking, start=1):
            previous = hits.get(hit.chunk_id)
            fused_score = (previous.fused_score if previous else 0.0) + 1 / (k + rank)
            if retriever == "semantic":
                hits[hit.chunk_id] = FusedHit(
                    chunk_id=hit.chunk_id,
                    fused_score=fused_score,
                    semantic_rank=rank,
                    semantic_score=hit.score,
                    lexical_rank=previous.lexical_rank if previous else None,
                    lexical_score=previous.lexical_score if previous else None,
                )
            else:
                hits[hit.chunk_id] = FusedHit(
                    chunk_id=hit.chunk_id,
                    fused_score=fused_score,
                    semantic_rank=previous.semantic_rank if previous else None,
                    semantic_score=previous.semantic_score if previous else None,
                    lexical_rank=rank,
                    lexical_score=hit.score,
                )

    return sorted(hits.values(), key=lambda hit: (-hit.fused_score, str(hit.chunk_id)))[:limit]
