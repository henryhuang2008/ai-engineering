import re
from uuid import UUID

from app.assistant.outputs import (
    INSUFFICIENT_EVIDENCE_RESPONSE,
    MAX_CITATIONS_PER_ANSWER,
    GroundedAnswer,
    ValidatedAnswer,
    citation_source,
)
from app.retrieval.models import Passage


class GroundingError(ValueError):
    pass


def validate_grounded_answer(
    answer: GroundedAnswer,
    passages: dict[UUID, Passage],
) -> ValidatedAnswer:
    if answer.insufficient_evidence:
        return ValidatedAnswer(text=INSUFFICIENT_EVIDENCE_RESPONSE, citations=[])

    citation_ids = list(
        dict.fromkeys(chunk_id for claim in answer.claims for chunk_id in claim.citation_ids)
    )
    if len(citation_ids) > MAX_CITATIONS_PER_ANSWER:
        raise GroundingError("The answer cites too many distinct passages.")
    if not citation_ids:
        raise GroundingError("A grounded answer must cite retrieved passages.")

    missing_ids = [chunk_id for chunk_id in citation_ids if chunk_id not in passages]
    if missing_ids:
        raise GroundingError("The answer cited a passage that was not retrieved.")

    sources = {
        chunk_id: citation_source(passages[chunk_id], index)
        for index, chunk_id in enumerate(citation_ids, start=1)
    }
    numbered = {chunk_id: source.citation_index for chunk_id, source in sources.items()}
    text_parts = []
    for claim in answer.claims:
        if re.search(r"\[\d+\]", claim.text):
            raise GroundingError("Claim text cannot include unverified citation markers.")
        text_parts.append(
            f"{claim.text.strip()} "
            + " ".join(f"[{numbered[chunk_id]}]" for chunk_id in claim.citation_ids)
        )
    text = "\n\n".join(text_parts)
    if len(text) > 20_000:
        raise GroundingError("The grounded answer exceeds the supported length.")
    return ValidatedAnswer(text=text, citations=list(sources.values()))
