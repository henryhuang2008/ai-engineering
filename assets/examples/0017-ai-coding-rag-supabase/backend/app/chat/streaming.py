from __future__ import annotations

import json
from collections.abc import Iterator
from uuid import UUID

from app.assistant.outputs import ValidatedAnswer

TEXT_DELTA_SIZE = 64


def stream_progress(message: str) -> bytes:
    return _sse(
        {
            "type": "data-progress",
            "id": "turn-progress",
            "data": {"message": message},
            "transient": True,
        }
    )


def stream_error(message: str) -> bytes:
    return _sse({"type": "error", "errorText": message})


def stream_validated_answer(
    answer: ValidatedAnswer,
    assistant_message_id: UUID,
) -> Iterator[bytes]:
    message_id = str(assistant_message_id)
    yield _sse({"type": "start", "messageId": message_id})
    yield _sse({"type": "text-start", "id": message_id})
    for start in range(0, len(answer.text), TEXT_DELTA_SIZE):
        yield _sse(
            {
                "type": "text-delta",
                "id": message_id,
                "delta": answer.text[start : start + TEXT_DELTA_SIZE],
            }
        )
    for citation in answer.citations:
        yield _sse(
            {
                "type": "data-citation",
                "id": str(citation.chunk_id),
                "data": citation.model_dump(mode="json"),
            }
        )
    yield _sse({"type": "text-end", "id": message_id})
    yield _sse({"type": "finish", "finishReason": "stop"})
    yield b"data: [DONE]\n\n"


def _sse(event: dict[str, object]) -> bytes:
    return f"data: {json.dumps(event, separators=(',', ':'))}\n\n".encode()
