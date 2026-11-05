"""Live DeepSeek extraction with a Pydantic schema.

Run from this folder:

    uv sync
    $env:DEEPSEEK_API_KEY = "sk-..."
    uv run python structured.py

The model is asked for a `Ticket`; LangChain turns the Pydantic JSON Schema into
a tool schema, DeepSeek calls it, and Pydantic validates the arguments before
you ever touch the object.
"""

from __future__ import annotations

import json
import sys
from typing import Literal

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field, ValidationError

from common import build_model

TICKET_TEXT = (
    "Order A-1042 was charged twice this month. "
    "I want a refund today, please. My email is dana@example.com."
)


class Ticket(BaseModel):
    """What we want out of a support message."""

    order_id: str = Field(description="Order id, for example A-1042")
    category: Literal["billing", "technical", "other"] = Field(
        description="billing for money, technical for product failures"
    )
    urgency: int = Field(ge=1, le=5, description="1 low, 5 urgent")
    wants_refund: bool = Field(description="True only if a refund is requested")
    summary: str = Field(description="One sentence, using only facts in the message")


SYSTEM = "Extract the support ticket. Use only facts present in the message."


def main() -> int:
    try:
        model = build_model()
    except RuntimeError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    schema = Ticket.model_json_schema()
    print("ticket schema:")
    print(json.dumps(schema, indent=2))
    print(f"\nrequired fields: {schema['required']}\n")

    extractor = model.with_structured_output(Ticket, method="function_calling")
    try:
        ticket = extractor.invoke(
            [SystemMessage(content=SYSTEM), HumanMessage(content=TICKET_TEXT)]
        )
    except Exception as error:  # noqa: BLE001 - show the provider error, keep exit 1
        print(f"error: {type(error).__name__}: {error}", file=sys.stderr)
        print("check DEEPSEEK_API_KEY, balance, and network access.", file=sys.stderr)
        return 1

    print(f"type:    {type(ticket).__name__} (validated instance)")
    print(f"order:   {ticket.order_id}")
    print(f"route:   {ticket.category}")
    print(f"urgency: {ticket.urgency}")
    print(f"refund:  {ticket.wants_refund}")
    print(f"summary: {ticket.summary}")
    print("\nas JSON:")
    print(ticket.model_dump_json(indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
