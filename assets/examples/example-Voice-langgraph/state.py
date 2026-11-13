"""The graph state: the running conversation plus which customer it belongs to."""

from __future__ import annotations

from typing import Annotated, List

from langgraph.graph import add_messages
from pydantic import BaseModel


class AgentState(BaseModel):
    messages: Annotated[List, add_messages] = []
    customer_id: str = ""
