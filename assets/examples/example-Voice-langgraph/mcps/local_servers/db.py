"""The MCP server: expense tools on top of PostgreSQL.

This is a local stdio server. `main.py` launches it with the current
interpreter; it reads SUPABASE_URI from the environment (see `.env.example`).

Schema source of truth: `generate_tables.sql` (the same SQL you run in Supabase).
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Optional
from uuid import UUID

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, ConfigDict
from sqlalchemy import ForeignKey, String, create_engine, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from categories import ExpenseCategory  # noqa: E402  (needs the path above)

load_dotenv(PROJECT_ROOT / ".env")


# ------------------------------------------------------------------ models ----

class Base(DeclarativeBase):
    pass


class DBCustomer(Base):
    __tablename__ = "customers"

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=text("gen_random_uuid()"))
    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=text("now()"), onupdate=datetime.now
    )
    first_name: Mapped[str] = mapped_column(String, nullable=False)
    last_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    email: Mapped[str] = mapped_column(String, nullable=False)

    expenses: Mapped[List["DBExpense"]] = relationship(
        back_populates="customer", cascade="all, delete-orphan"
    )


class DBExpense(Base):
    __tablename__ = "expenses"

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=text("gen_random_uuid()"))
    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=text("now()"), onupdate=datetime.now
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    category: Mapped[str] = mapped_column(String, nullable=False, server_default=text("'other'"))
    amount: Mapped[float] = mapped_column(nullable=False)
    customer_id: Mapped[UUID] = mapped_column(
        ForeignKey("customers.id", ondelete="CASCADE"), nullable=False
    )

    customer: Mapped["DBCustomer"] = relationship(
        back_populates="expenses", foreign_keys=[customer_id]
    )


class Expense(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime
    updated_at: datetime
    name: str
    description: Optional[str] = None
    category: ExpenseCategory
    amount: float
    customer_id: UUID


# ----------------------------------------------------------------- session ----

def database_uri() -> str:
    uri = os.environ.get("SUPABASE_URI", "").strip() or os.environ.get("DATABASE_URL", "").strip()
    if not uri:
        raise RuntimeError(
            "SUPABASE_URI is not set. Put it in .env, for example:\n"
            "SUPABASE_URI=postgresql://postgres:PASSWORD@db.PROJECT.supabase.co:5432/postgres"
        )
    return uri


engine = create_engine(database_uri(), pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def _json(expense: DBExpense) -> str:
    return Expense.model_validate(expense).model_dump_json(indent=2)


# --------------------------------------------------------------- MCP server ----

mcp = FastMCP("db", log_level="ERROR")


@mcp.tool()
async def create_expense(
    customer_id: UUID,
    name: str,
    amount: float,
    category: ExpenseCategory,
    description: Optional[str] = None,
) -> str:
    """Create a new expense for a customer.

    Args:
        customer_id: The customer the expense belongs to.
        name: Short name of the expense, e.g. "Team lunch".
        amount: Amount spent, in account currency.
        category: One of meals, travel, lodging, entertainment, training, gifts,
            education, office_supplies, other.
        description: Optional extra detail.

    Returns:
        The created expense as JSON.
    """
    with SessionLocal() as session:
        expense = DBExpense(
            name=name,
            amount=amount,
            category=category.value,
            description=description,
            customer_id=customer_id,
        )
        session.add(expense)
        session.commit()
        session.refresh(expense)
        return _json(expense)


@mcp.tool()
async def list_expenses(customer_id: UUID, limit: int = 20) -> str:
    """List a customer's expenses, most recent first.

    Args:
        customer_id: The customer to query.
        limit: Maximum number of rows to return (default 20).

    Returns:
        A JSON array of expenses.
    """
    with SessionLocal() as session:
        rows = (
            session.query(DBExpense)
            .filter(DBExpense.customer_id == customer_id)
            .order_by(DBExpense.created_at.desc())
            .limit(limit)
            .all()
        )
        return json.dumps([Expense.model_validate(row).model_dump() for row in rows], default=str, indent=2)


@mcp.tool()
async def update_expense(
    id: UUID,
    customer_id: UUID,
    name: Optional[str] = None,
    amount: Optional[float] = None,
    category: Optional[ExpenseCategory] = None,
    description: Optional[str] = None,
) -> str:
    """Update one expense. Only the fields you pass are changed.

    Args:
        id: The expense id.
        customer_id: The customer the expense must belong to.
        name: New name, if changing.
        amount: New amount, if changing.
        category: New category, if changing.
        description: New description, if changing.

    Returns:
        The updated expense as JSON, or "Expense not found".
    """
    with SessionLocal() as session:
        expense = (
            session.query(DBExpense)
            .filter(DBExpense.id == id, DBExpense.customer_id == customer_id)
            .first()
        )
        if expense is None:
            return "Expense not found"

        if name is not None:
            expense.name = name
        if amount is not None:
            expense.amount = amount
        if category is not None:
            expense.category = category.value
        if description is not None:
            expense.description = description

        session.commit()
        session.refresh(expense)
        return _json(expense)


@mcp.tool()
async def delete_expense(id: UUID, customer_id: UUID) -> str:
    """Delete one expense.

    Args:
        id: The expense id.
        customer_id: The customer the expense must belong to.

    Returns:
        The deleted expense as JSON, or "Expense not found".
    """
    with SessionLocal() as session:
        expense = (
            session.query(DBExpense)
            .filter(DBExpense.id == id, DBExpense.customer_id == customer_id)
            .first()
        )
        if expense is None:
            return "Expense not found"
        payload = _json(expense)
        session.delete(expense)
        session.commit()
        return payload


@mcp.tool()
async def query_db(query: str, customer_id: UUID) -> str:
    """Run a read-only SQL query against the expenses table.

    Args:
        query: A PostgreSQL SELECT statement.
        customer_id: The active customer, exposed to the database as app.customer_id
            so row-level security policies can use it.

    Returns:
        The rows as JSON.

    Note:
        The SQL is only as safe as the model that wrote it. This is a demo: give
        the database user read-only rights before exposing this to anyone.
    """
    with SessionLocal() as session:
        session.execute(text("SELECT set_config('app.customer_id', :cid, true)"), {"cid": str(customer_id)})
        result = session.execute(text(query))
        rows = [dict(row._mapping) for row in result]
    return json.dumps(rows, default=str, indent=2)


if __name__ == "__main__":
    mcp.run(transport="stdio")
