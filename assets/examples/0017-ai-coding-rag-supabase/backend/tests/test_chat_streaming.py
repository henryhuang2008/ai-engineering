import json
from datetime import date
from uuid import UUID

from app.assistant.outputs import CitationSource, ValidatedAnswer
from app.chat.streaming import (
    TEXT_DELTA_SIZE,
    stream_error,
    stream_progress,
    stream_validated_answer,
)

MESSAGE_ID = UUID("a61b2c08-8c8d-4c54-9dbb-f9828eb04819")
CHUNK_ID = UUID("a61b2c08-8c8d-4c54-9dbb-f9828eb04820")


def test_stream_emits_validated_answer_and_citation_in_protocol_order() -> None:
    answer = ValidatedAnswer(
        text="x" * (TEXT_DELTA_SIZE + 1),
        citations=[
            CitationSource(
                citation_index=1,
                chunk_id=CHUNK_ID,
                ticker="GOOGL",
                company_name="Alphabet Inc.",
                filing_type="10-K",
                filing_date=date(2026, 2, 5),
                fiscal_year=2025,
                accession_number="0001652044-26-000012",
                source_url="https://example.test/filing",
                section="Revenue",
                page_references=[12],
                passage="Passage text.",
            )
        ],
    )

    events = list(stream_validated_answer(answer, MESSAGE_ID))
    payloads = [json.loads(event.decode().removeprefix("data: ").strip()) for event in events[:-1]]

    assert [event["type"] for event in payloads] == [
        "start",
        "text-start",
        "text-delta",
        "text-delta",
        "data-citation",
        "text-end",
        "finish",
    ]
    assert payloads[4]["id"] == str(CHUNK_ID)
    assert payloads[4]["data"]["page_references"] == [12]
    assert sum(len(event.get("delta", "")) for event in payloads) == len(answer.text)
    assert events[-1] == b"data: [DONE]\n\n"


def test_progress_and_errors_use_ai_sdk_data_parts() -> None:
    progress = json.loads(stream_progress("Searching filings.").decode().removeprefix("data: "))
    error = json.loads(stream_error("The request timed out.").decode().removeprefix("data: "))

    assert progress == {
        "type": "data-progress",
        "id": "turn-progress",
        "data": {"message": "Searching filings."},
        "transient": True,
    }
    assert error == {"type": "error", "errorText": "The request timed out."}
