from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from app import db


@pytest.fixture()
def database(tmp_path: Path) -> Path:
    path = tmp_path / "northstar.db"
    db.build_db(path, force=True)
    return path


def test_build_counts_the_seed_rows(database: Path) -> None:
    assert db.row_counts(database) == {
        "customers": 8,
        "products": 6,
        "orders": 12,
        "order_items": 19,
    }


def test_build_is_idempotent(tmp_path: Path) -> None:
    path = tmp_path / "northstar.db"
    first = db.build_db(path, force=True)
    second = db.build_db(path)
    assert first == second


def test_completed_orders_and_revenue(database: Path) -> None:
    orders = db.run_query(
        "SELECT COUNT(*) FROM orders WHERE status = 'completed'", database
    )
    revenue = db.run_query(
        "SELECT ROUND(SUM(oi.quantity * oi.unit_price), 2) "
        "FROM order_items oi JOIN orders o ON o.order_id = oi.order_id "
        "WHERE o.status = 'completed'",
        database,
    )
    assert orders.rows == [(10,)]
    assert revenue.rows == [(3111.0,)]


def test_schema_text_lists_every_table_with_counts(database: Path) -> None:
    text = db.schema_text(database)
    for table in db.TABLES:
        assert f"-- {table} (" in text
    assert "CREATE TABLE customers" in text


def test_read_only_connection_rejects_writes(database: Path) -> None:
    connection = db.connect(database)
    with pytest.raises(sqlite3.OperationalError):
        connection.execute("DELETE FROM orders")
    connection.close()


def test_missing_database_says_how_to_build(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="main.py build"):
        db.connect(tmp_path / "absent.db")
