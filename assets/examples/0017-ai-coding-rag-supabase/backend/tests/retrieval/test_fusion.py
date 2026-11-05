from uuid import UUID

import pytest

from app.retrieval.fusion import SearchHit, reciprocal_rank_fusion

CHUNK_A = UUID("00000000-0000-0000-0000-000000000001")
CHUNK_B = UUID("00000000-0000-0000-0000-000000000002")
CHUNK_C = UUID("00000000-0000-0000-0000-000000000003")


def test_rrf_combines_ranks_and_preserves_branch_evidence() -> None:
    fused = reciprocal_rank_fusion(
        [SearchHit(CHUNK_A, 0.1), SearchHit(CHUNK_B, 0.2)],
        [SearchHit(CHUNK_B, 0.8), SearchHit(CHUNK_A, 0.9)],
        limit=3,
    )

    assert [hit.chunk_id for hit in fused] == [CHUNK_A, CHUNK_B]
    assert fused[0].fused_score == pytest.approx(1 / 61 + 1 / 62)
    assert (fused[0].semantic_rank, fused[0].lexical_rank) == (1, 2)
    assert (fused[0].semantic_score, fused[0].lexical_score) == (0.1, 0.9)


def test_rrf_handles_non_overlapping_and_empty_rankings() -> None:
    fused = reciprocal_rank_fusion(
        [SearchHit(CHUNK_C, 0.3)],
        [SearchHit(CHUNK_A, 0.4)],
        limit=5,
    )

    assert [hit.chunk_id for hit in fused] == [CHUNK_A, CHUNK_C]
    assert reciprocal_rank_fusion([], [], limit=1) == []


def test_rrf_ties_are_stable_and_limits_are_validated() -> None:
    fused = reciprocal_rank_fusion(
        [SearchHit(CHUNK_B, 0.1)],
        [SearchHit(CHUNK_A, 0.1)],
        limit=2,
    )

    assert [hit.chunk_id for hit in fused] == [CHUNK_A, CHUNK_B]
    with pytest.raises(ValueError, match="at least one"):
        reciprocal_rank_fusion([], [], limit=0)
