from __future__ import annotations

from datetime import date
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

MAX_QUERY_LENGTH = 2_000
MAX_RESULTS = 10
MAX_NEIGHBOR_WINDOW = 1
MAX_PASSAGE_EXCERPT_LENGTH = 3_000


class SearchFilters(BaseModel):
    model_config = ConfigDict(frozen=True)

    ticker: str | None = Field(default=None, min_length=1, max_length=10)
    fiscal_year: int | None = Field(default=None, ge=1900, le=2200)
    filing_type: str | None = Field(default=None, min_length=1, max_length=20)

    @field_validator("ticker", "filing_type")
    @classmethod
    def normalize_text_filter(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().upper()
        if not normalized:
            raise ValueError("Text filters must not be empty.")
        return normalized


class RetrievalEvidence(BaseModel):
    fused_score: float
    semantic_rank: int | None = Field(default=None, ge=1)
    semantic_score: float | None = None
    lexical_rank: int | None = Field(default=None, ge=1)
    lexical_score: float | None = None


class Passage(BaseModel):
    chunk_id: UUID
    document_id: UUID
    chunk_index: int
    content: str
    section: str | None
    source_start: int | None
    source_end: int | None
    chunk_metadata: dict[str, Any]
    document_metadata: dict[str, Any]
    ticker: str
    company_name: str
    fiscal_year: int
    filing_type: str
    filing_date: date
    accession_number: str
    source_url: str
    retrieval: RetrievalEvidence | None = None


class PassageWindow(BaseModel):
    target: Passage
    before: list[Passage]
    after: list[Passage]


def validate_query(query: str) -> str:
    normalized = query.strip()
    if not normalized:
        raise ValueError("Search query must not be empty.")
    if len(normalized) > MAX_QUERY_LENGTH:
        raise ValueError(f"Search query must not exceed {MAX_QUERY_LENGTH} characters.")
    return normalized
