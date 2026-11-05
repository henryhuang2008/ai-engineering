# /// script
# requires-python = ">=3.12"
# ///
from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path, PurePosixPath
from typing import Any

from sqlalchemy import create_engine, func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.engine import URL, make_url

DATA_DIR = Path(__file__).resolve().parent
DEFAULT_MANIFEST = DATA_DIR / "markdown" / "manifest.json"
COMPANY_NAMES = {
    "AAPL": "Apple Inc.",
    "AMZN": "Amazon.com, Inc.",
    "GOOGL": "Alphabet Inc.",
    "MSFT": "Microsoft Corporation",
    "NVDA": "NVIDIA Corporation",
}


def _relative_path(value: str) -> PurePosixPath:
    path = PurePosixPath(value.replace("\\", "/"))
    if path.is_absolute() or not path.parts or ".." in path.parts:
        raise ValueError(f"Manifest path must be relative to the Markdown directory: {value!r}")
    return path


def load_documents(manifest_path: Path) -> list[dict[str, Any]]:
    manifest_path = manifest_path.resolve()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    filings = manifest.get("filings")
    if not isinstance(filings, list):
        raise ValueError(f"Expected a 'filings' list in {manifest_path}")

    markdown_dir = manifest_path.parent.resolve()
    documents = []
    seen_keys: set[tuple[str, str]] = set()
    for filing in filings:
        if not isinstance(filing, dict):
            raise ValueError(f"Invalid filing entry in {manifest_path}: {filing!r}")
        ticker = filing.get("ticker")
        accession_number = filing.get("accession_number")
        if ticker not in COMPANY_NAMES or not isinstance(accession_number, str):
            raise ValueError(
                f"Filing is missing a supported ticker or accession number: {filing!r}"
            )

        key = (ticker, accession_number)
        if key in seen_keys:
            raise ValueError(f"Duplicate ticker/accession number in manifest: {key}")
        seen_keys.add(key)

        local_path = filing.get("local_path")
        if not isinstance(local_path, str):
            raise ValueError(f"Filing is missing its Markdown local_path: {filing!r}")
        relative_path = _relative_path(local_path)
        source = markdown_dir.joinpath(*relative_path.parts).resolve()
        if not source.is_relative_to(markdown_dir):
            raise ValueError(f"Manifest path escapes the Markdown directory: {local_path}")
        if not source.is_file():
            raise FileNotFoundError(f"Markdown filing not found: {source}")
        content = source.read_text(encoding="utf-8")
        if not content.strip():
            raise ValueError(f"Markdown filing is empty: {source}")

        filing_date = date.fromisoformat(filing["filing_date"])
        report_date = filing.get("report_date")
        fiscal_year = date.fromisoformat(report_date).year if report_date else filing_date.year
        documents.append(
            {
                "ticker": ticker,
                "company_name": COMPANY_NAMES[ticker],
                "filing_type": filing["form"],
                "filing_date": filing_date,
                "fiscal_year": fiscal_year,
                "accession_number": accession_number,
                "source_url": filing["source_url"],
                "content": content,
                "metadata": {
                    "cik": filing["cik"],
                    "report_date": report_date,
                    "primary_document": filing["primary_document"],
                    "markdown_local_path": relative_path.as_posix(),
                    "source_local_path": filing.get("source_local_path"),
                },
            }
        )

    if not documents:
        raise ValueError(f"No filings found in {manifest_path}")
    return documents


def _database_url() -> URL:
    from app.config import settings

    if not settings.database_url:
        raise RuntimeError("DATABASE_URL is required to ingest source documents.")
    url = make_url(settings.database_url)
    if url.drivername in {"postgres", "postgresql", "postgresql+psycopg2"}:
        return url.set(drivername="postgresql+psycopg")
    if url.drivername != "postgresql+psycopg":
        raise ValueError("DATABASE_URL must use a PostgreSQL connection.")
    return url


def ingest_documents(documents: list[dict[str, Any]]) -> None:
    from app.database.models.source_document import SourceDocument

    table = SourceDocument.__table__
    statement = insert(table)
    update_values = {
        column: getattr(statement.excluded, column)
        for column in (
            "company_name",
            "filing_type",
            "filing_date",
            "fiscal_year",
            "source_url",
            "content",
            "metadata",
        )
    }
    update_values["updated_at"] = func.now()
    statement = statement.on_conflict_do_update(
        index_elements=[table.c.ticker, table.c.accession_number],
        set_=update_values,
    )

    engine = create_engine(_database_url(), pool_pre_ping=True)
    try:
        with engine.begin() as connection:
            if (
                connection.exec_driver_sql(
                    "SELECT to_regclass('public.source_documents')"
                ).scalar_one()
                is None
            ):
                raise RuntimeError(
                    "public.source_documents does not exist. Apply the Alembic migration first."
                )
            for document in documents:
                connection.execute(statement.values(**document))
    finally:
        engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Upsert converted SEC filings into public.source_documents."
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=DEFAULT_MANIFEST,
        help=f"Markdown conversion manifest (default: {DEFAULT_MANIFEST})",
    )
    args = parser.parse_args()

    documents = load_documents(args.manifest)
    ingest_documents(documents)
    print(f"Upserted {len(documents)} source document(s) into public.source_documents.")


if __name__ == "__main__":
    main()
