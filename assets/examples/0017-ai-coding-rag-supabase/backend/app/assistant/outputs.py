from __future__ import annotations

from datetime import date
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from app.retrieval.models import Passage

MAX_CLAIMS = 20
MAX_CITATIONS_PER_CLAIM = 5
MAX_CITATIONS_PER_ANSWER = 20
MAX_ANSWER_LENGTH = 20_000
INSUFFICIENT_EVIDENCE_RESPONSE = (
    "The available filing evidence is not sufficient to answer this question reliably."
)


class GroundedClaim(BaseModel):
    text: str = Field(min_length=1, max_length=2_000)
    citation_ids: list[UUID] = Field(min_length=1, max_length=MAX_CITATIONS_PER_CLAIM)

    @model_validator(mode="after")
    def validate_text_and_citations(self) -> GroundedClaim:
        if not self.text.strip():
            raise ValueError("A grounded claim must contain text.")
        if len(set(self.citation_ids)) != len(self.citation_ids):
            raise ValueError("A claim cannot repeat the same citation.")
        return self


class GroundedAnswer(BaseModel):
    insufficient_evidence: bool
    claims: list[GroundedClaim] = Field(max_length=MAX_CLAIMS)

    @model_validator(mode="after")
    def validate_answer_shape(self) -> GroundedAnswer:
        if self.insufficient_evidence and self.claims:
            raise ValueError("An evidence-limited answer cannot contain factual claims.")
        if not self.insufficient_evidence and not self.claims:
            raise ValueError("An answer with sufficient evidence must contain claims.")
        return self


class CitationSource(BaseModel):
    citation_index: int = Field(ge=1)
    chunk_id: UUID
    quote: str | None = None
    ticker: str
    company_name: str
    filing_type: str
    filing_date: date
    fiscal_year: int
    accession_number: str
    source_url: str
    section: str | None
    page_references: list[int]
    passage: str


class ValidatedAnswer(BaseModel):
    text: str = Field(max_length=MAX_ANSWER_LENGTH)
    citations: list[CitationSource] = Field(max_length=MAX_CITATIONS_PER_ANSWER)


def citation_source(passage: Passage, citation_index: int) -> CitationSource:
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
    return CitationSource(
        citation_index=citation_index,
        chunk_id=passage.chunk_id,
        ticker=passage.ticker,
        company_name=passage.company_name,
        filing_type=passage.filing_type,
        filing_date=passage.filing_date,
        fiscal_year=passage.fiscal_year,
        accession_number=passage.accession_number,
        source_url=passage.source_url,
        section=passage.section,
        page_references=pages,
        passage=passage.content,
    )
