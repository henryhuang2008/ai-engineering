from __future__ import annotations

from pathlib import Path

import pytest

from app import db


def test_accepts_select_and_with() -> None:
    assert db.check_sql("SELECT 1") == "SELECT 1"
    assert db.check_sql("WITH x AS (SELECT 1) SELECT * FROM x").startswith("WITH")


def test_strips_code_fence_and_trailing_semicolon() -> None:
    assert db.check_sql("```sql\nSELECT 1;\n```") == "SELECT 1"


@pytest.mark.parametrize(
    "sql",
    [
        "INSERT INTO orders VALUES (1)",
        "UPDATE orders SET status = 'x'",
        "DELETE FROM orders",
        "DROP TABLE orders",
        "PRAGMA table_info(orders)",
        "ATTACH DATABASE 'x.db' AS x",
    ],
)
def test_rejects_writes_and_pragmas(sql: str) -> None:
    with pytest.raises(db.SqlRejected):
        db.check_sql(sql)


def test_rejects_multiple_statements() -> None:
    with pytest.raises(db.SqlRejected, match="one statement"):
        db.check_sql("SELECT 1; SELECT 2")


def test_rejects_empty_and_non_select() -> None:
    with pytest.raises(db.SqlRejected):
        db.check_sql("   ")
    with pytest.raises(db.SqlRejected):
        db.check_sql("EXPLAIN SELECT 1")


def test_run_query_returns_errors_as_data(tmp_path: Path) -> None:
    path = tmp_path / "t.db"
    db.build_db(path, force=True)
    result = db.run_query("SELECT missing FROM orders", path)
    assert not result.ok
    assert "no such column" in (result.error or "")


def test_result_is_capped_at_fifty_rows(tmp_path: Path) -> None:
    path = tmp_path / "t.db"
    db.build_db(path, force=True)
    result = db.run_query("SELECT * FROM orders a, orders b", path)
    assert result.ok
    assert len(result.rows) == db.MAX_ROWS
    assert result.truncated
    assert f"truncated at {db.MAX_ROWS}" in db.format_result(result)


def test_slow_query_is_stopped_by_the_progress_handler(tmp_path: Path) -> None:
    path = tmp_path / "t.db"
    db.build_db(path, force=True)
    # A recursive CTE over 10^9 rows: without the progress handler this never returns.
    result = db.run_query(
        "WITH RECURSIVE n(x) AS (SELECT 1 UNION ALL SELECT x + 1 FROM n) "
        "SELECT count(*) FROM n",
        path,
        seconds=0.1,
    )
    assert not result.ok
    assert "interrupted" in (result.error or "").lower()
