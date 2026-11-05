from __future__ import annotations

from datetime import date
from uuid import UUID

from pydantic import BaseModel

from app.retrieval.models import MAX_PASSAGE_EXCERPT_LENGTH, Passage, PassageWindow

MAX_EVIDENCE_PASSAGE_LENGTH = MAX_PASSAGE_EXCERPT_LENGTH
MAX_EVIDENCE_CONTEXT_LENGTH = 24_000


class EvidencePassage(BaseModel):
    chunk_id: UUID
    chunk_index: int
    ticker: str
    company_name: str
    filing_type: str
    filing_date: date
    fiscal_year: int
    accession_number: str
    section: str | None
    page_references: list[int]
    content: str


class EvidencePassageWindow(BaseModel):
    target: EvidencePassage
    before: list[EvidencePassage]
    after: list[EvidencePassage]


def to_evidence_passage(passage: Passage) -> EvidencePassage:
    page_references = passage.chunk_metadata.get("page_references", [])
    pages = (
        sorted(
            {
                page
                for page in page_references
                if isinstance(page, int) and not isinstance(page, bool) and page > 0
            }
        )
        if isinstance(page_references, list)
        else []
    )
    return EvidencePassage(
        chunk_id=passage.chunk_id,
        chunk_index=passage.chunk_index,
        ticker=passage.ticker,
        company_name=passage.company_name,
        filing_type=passage.filing_type,
        filing_date=passage.filing_date,
        fiscal_year=passage.fiscal_year,
        accession_number=passage.accession_number,
        section=passage.section,
        page_references=pages,
        content=passage.content[:MAX_EVIDENCE_PASSAGE_LENGTH],
    )


def to_evidence_passages(passages: list[Passage]) -> list[EvidencePassage]:
    evidence = []
    remaining = MAX_EVIDENCE_CONTEXT_LENGTH
    for passage in passages:
        content_length = min(MAX_EVIDENCE_PASSAGE_LENGTH, remaining)
        if content_length <= 0:
            break
        evidence.append(
            to_evidence_passage(passage).model_copy(
                update={"content": passage.content[:content_length]}
            )
        )
        remaining -= content_length
    return evidence


def to_evidence_window(window: PassageWindow) -> EvidencePassageWindow:
    return EvidencePassageWindow(
        target=to_evidence_passage(window.target),
        before=[to_evidence_passage(passage) for passage in window.before],
        after=[to_evidence_passage(passage) for passage in window.after],
    )
