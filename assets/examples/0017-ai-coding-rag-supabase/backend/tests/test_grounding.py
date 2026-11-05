from datetime import date
from uuid import UUID

import pytest

from app.assistant.outputs import GroundedAnswer, GroundedClaim
from app.grounding.validator import GroundingError, validate_grounded_answer
from app.retrieval.models import Passage

CHUNK_ID = UUID("a61b2c08-8c8d-4c54-9dbb-f9828eb04820")
DOCUMENT_ID = UUID("a61b2c08-8c8d-4c54-9dbb-f9828eb04818")


@pytest.fixture
def passage() -> Passage:
    return Passage(
        chunk_id=CHUNK_ID,
        document_id=DOCUMENT_ID,
        chunk_index=3,
        content="Google reported revenue of $100 billion.",
        section="Revenue",
        source_start=None,
        source_end=None,
        chunk_metadata={"page_references": [12, 12, 0, True, "13"]},
        document_metadata={},
        ticker="GOOGL",
        company_name="Alphabet Inc.",
        fiscal_year=2025,
        filing_type="10-K",
        filing_date=date(2026, 2, 5),
        accession_number="0001652044-26-000012",
        source_url="https://example.test/filing",
    )


def test_grounding_adds_stable_citations_and_uses_source_metadata(
    passage: Passage,
) -> None:
    answer = GroundedAnswer(
        insufficient_evidence=False,
        claims=[
            GroundedClaim(
                text="Google reported revenue of $100 billion.",
                citation_ids=[CHUNK_ID],
            )
        ],
    )

    validated = validate_grounded_answer(answer, {CHUNK_ID: passage})

    assert validated.text.endswith("[1]")
    assert len(validated.citations) == 1
    assert validated.citations[0].page_references == [12]
    assert validated.citations[0].source_url == passage.source_url
    assert validated.citations[0].passage == passage.content


def test_grounding_rejects_unknown_passages_and_unverified_inline_markers(
    passage: Passage,
) -> None:
    unknown = UUID("a61b2c08-8c8d-4c54-9dbb-f9828eb04821")
    answer = GroundedAnswer(
        insufficient_evidence=False,
        claims=[GroundedClaim(text="A claim.", citation_ids=[unknown])],
    )
    with pytest.raises(GroundingError, match="not retrieved"):
        validate_grounded_answer(answer, {CHUNK_ID: passage})

    marker = GroundedAnswer(
        insufficient_evidence=False,
        claims=[GroundedClaim(text="A claim [1].", citation_ids=[CHUNK_ID])],
    )
    with pytest.raises(GroundingError, match="unverified citation markers"):
        validate_grounded_answer(marker, {CHUNK_ID: passage})


def test_insufficient_evidence_is_rendered_as_fixed_citation_free_refusal() -> None:
    answer = GroundedAnswer(insufficient_evidence=True, claims=[])

    validated = validate_grounded_answer(answer, {})

    assert validated.text == (
        "The available filing evidence is not sufficient to answer this question reliably."
    )
    assert validated.citations == []


def test_grounded_answer_requires_claims_or_explicit_refusal() -> None:
    with pytest.raises(ValueError, match="must contain claims"):
        GroundedAnswer(insufficient_evidence=False, claims=[])
    with pytest.raises(ValueError, match="cannot contain factual claims"):
        GroundedAnswer(
            insufficient_evidence=True,
            claims=[GroundedClaim(text="Unsupported.", citation_ids=[CHUNK_ID])],
        )
