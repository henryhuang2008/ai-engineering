"""SQLite access for the text-to-SQL agent: build, describe, guard, execute.

The model never touches this connection. It proposes SQL; this module decides
whether the statement is allowed and runs it on a read-only connection with a
row cap and a wall-clock budget.
"""

from __future__ import annotations

import csv
import re
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
DEFAULT_DB = DATA_DIR / "northstar.db"

MAX_ROWS = 50
MAX_SECONDS = 2.0

SCHEMA = """
CREATE TABLE customers (
    customer_id INTEGER PRIMARY KEY,
    name        TEXT NOT NULL,
    region      TEXT NOT NULL,
    signup_date TEXT NOT NULL
);

CREATE TABLE products (
    product_id INTEGER PRIMARY KEY,
    name       TEXT NOT NULL,
    category   TEXT NOT NULL,
    unit_price REAL NOT NULL
);

CREATE TABLE orders (
    order_id    INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL REFERENCES customers(customer_id),
    ordered_at  TEXT NOT NULL,
    status      TEXT NOT NULL CHECK (status IN ('completed', 'cancelled', 'pending'))
);

CREATE TABLE order_items (
    order_id   INTEGER NOT NULL REFERENCES orders(order_id),
    product_id INTEGER NOT NULL REFERENCES products(product_id),
    quantity   INTEGER NOT NULL,
    unit_price REAL NOT NULL,
    PRIMARY KEY (order_id, product_id)
);
"""

TABLES = {
    "customers": (
        "customer_id,name,region,signup_date",
        (int, str, str, str),
    ),
    "products": (
        "product_id,name,category,unit_price",
        (int, str, str, float),
    ),
    "orders": (
        "order_id,customer_id,ordered_at,status",
        (int, int, str, str),
    ),
    "order_items": (
        "order_id,product_id,quantity,unit_price",
        (int, int, int, float),
    ),
}


class SqlRejected(ValueError):
    """Raised when a proposed statement fails the guard."""


FORBIDDEN = re.compile(
    r"\b(insert|update|delete|drop|alter|create|replace|attach|detach|"
    r"pragma|vacuum|reindex|trigger|grant|revoke)\b",
    re.IGNORECASE,
)


def build_db(
    path: Path = DEFAULT_DB,
    data_dir: Path = DATA_DIR,
    *,
    force: bool = False,
) -> dict[str, int]:
    """Create the SQLite file from the CSV seeds. Safe to call twice."""
    if path.exists() and not force:
        return row_counts(path)

    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()

    connection = sqlite3.connect(path)
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.executescript(SCHEMA)
        for table, (columns, types) in TABLES.items():
            with (data_dir / f"{table}.csv").open(encoding="utf-8", newline="") as handle:
                reader = csv.DictReader(handle)
                rows = [
                    tuple(cast(row[column]) for column, cast in zip(columns.split(","), types))
                    for row in reader
                ]
            placeholders = ", ".join("?" for _ in columns.split(","))
            connection.executemany(
                f"INSERT INTO {table} ({columns}) VALUES ({placeholders})",
                rows,
            )
        connection.commit()
    finally:
        connection.close()
    return row_counts(path)


def row_counts(path: Path = DEFAULT_DB) -> dict[str, int]:
    connection = connect(path)
    try:
        return {
            table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in TABLES
        }
    finally:
        connection.close()


def connect(path: Path = DEFAULT_DB, *, readonly: bool = True) -> sqlite3.Connection:
    if not path.exists():
        raise FileNotFoundError(
            f"database not found: {path}\nrun: uv run python main.py build"
        )
    if readonly:
        uri = f"file:{path.as_posix()}?mode=ro"
        connection = sqlite3.connect(uri, uri=True)
        connection.execute("PRAGMA query_only = ON")
    else:
        connection = sqlite3.connect(path)
        connection.execute("PRAGMA foreign_keys = ON")
    return connection


def schema_text(path: Path = DEFAULT_DB) -> str:
    """DDL plus row counts, the whole schema the model is allowed to see."""
    connection = connect(path)
    try:
        rows = connection.execute(
            "SELECT name, sql FROM sqlite_master "
            "WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall()
        blocks = []
        for name, ddl in rows:
            count = connection.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
            blocks.append(f"-- {name} ({count} rows)\n{ddl.strip()};")
        return "\n\n".join(blocks)
    finally:
        connection.close()


def check_sql(sql: str) -> str:
    """Return the statement if it is one read-only SELECT, else raise."""
    text = (sql or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    text = text.strip()
    if text.endswith(";"):
        text = text[:-1].rstrip()

    if not text:
        raise SqlRejected("empty query")
    if ";" in text:
        raise SqlRejected("only one statement is allowed")
    if not re.match(r"(?is)^\s*(select|with)\b", text):
        raise SqlRejected("only SELECT queries are allowed")

    match = FORBIDDEN.search(text)
    if match:
        raise SqlRejected(f"forbidden keyword: {match.group(1).upper()}")
    return text


def wrap_limit(sql: str, max_rows: int = MAX_ROWS) -> str:
    """Cap any statement, even one that already has its own LIMIT."""
    return f"SELECT * FROM (\n{sql}\n) LIMIT {max_rows}"


@dataclass
class QueryResult:
    columns: list[str] = field(default_factory=list)
    rows: list[tuple] = field(default_factory=list)
    error: str | None = None
    truncated: bool = False
    elapsed_ms: float = 0.0

    @property
    def ok(self) -> bool:
        return self.error is None


def run_query(
    sql: str,
    path: Path = DEFAULT_DB,
    *,
    max_rows: int = MAX_ROWS,
    seconds: float = MAX_SECONDS,
) -> QueryResult:
    """Guard and execute one statement. Errors come back as data, not raises."""
    started = time.monotonic()
    try:
        statement = check_sql(sql)
    except SqlRejected as error:
        return QueryResult(error=f"Rejected: {error}")

    try:
        connection = connect(path)
    except FileNotFoundError as error:
        return QueryResult(error=str(error))

    deadline = started + seconds

    def stop_when_late() -> int:
        return 1 if time.monotonic() > deadline else 0

    try:
        connection.set_progress_handler(stop_when_late, 1_000)
        cursor = connection.execute(wrap_limit(statement, max_rows + 1))
        columns = [description[0] for description in cursor.description or []]
        rows = cursor.fetchmany(max_rows + 1)
        truncated = len(rows) > max_rows
        return QueryResult(
            columns=columns,
            rows=rows[:max_rows],
            truncated=truncated,
            elapsed_ms=(time.monotonic() - started) * 1000,
        )
    except sqlite3.Error as error:
        return QueryResult(error=f"{type(error).__name__}: {error}")
    finally:
        connection.close()


def format_result(result: QueryResult) -> str:
    """Compact text form for the model and the terminal."""
    if not result.ok:
        return f"Error: {result.error}"
    if not result.rows:
        return "0 rows"
    lines = [" | ".join(result.columns)]
    for index, row in enumerate(result.rows, start=1):
        cells = [str(value) for value in row]
        lines.append(f"{index}. " + " | ".join(cells))
    if result.truncated:
        lines.append(f"... truncated at {MAX_ROWS} rows")
    return "\n".join(lines)
