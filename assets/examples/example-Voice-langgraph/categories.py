"""The expense categories, shared by the MCP server and the agent prompt.

Kept in its own module so `assistant_graph.py` can import the enum without
opening a database connection.
"""

from __future__ import annotations

from enum import StrEnum


class ExpenseCategory(StrEnum):
    MEALS = "meals"
    TRAVEL = "travel"
    LODGING = "lodging"
    ENTERTAINMENT = "entertainment"
    TRAINING = "training"
    GIFTS = "gifts"
    EDUCATION = "education"
    OFFICE_SUPPLIES = "office_supplies"
    OTHER = "other"


CATEGORY_NAMES = ", ".join(c.value for c in ExpenseCategory)
