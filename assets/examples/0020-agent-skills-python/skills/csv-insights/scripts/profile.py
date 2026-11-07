"""Profile a CSV file and print one JSON object.

Deliberately stdlib-only: a skill script is executed in a subprocess by the
runtime, so its dependencies must already exist in that interpreter. Fewer
imports means fewer ways the skill fails on a user's machine.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from pathlib import Path


def parse_number(value: str) -> int | float | None:
    try:
        return int(value)
    except ValueError:
        pass
    try:
        number = float(value)
    except ValueError:
        return None
    return number if math.isfinite(number) else None


def infer_type(values: list[str]) -> str:
    parsed = [parse_number(value) for value in values]
    if not parsed:
        return "empty"
    if all(isinstance(number, int) for number in parsed):
        return "int"
    if all(number is not None for number in parsed):
        return "float"
    return "text"


def profile_column(name: str, raw: list[str]) -> dict[str, object]:
    values = [value.strip() for value in raw]
    present = [value for value in values if value]
    kind = infer_type(present)

    column: dict[str, object] = {
        "name": name,
        "inferred_type": kind,
        "missing": len(values) - len(present),
        "distinct": len(set(present)),
    }

    if kind in {"int", "float"}:
        numbers = [parse_number(value) for value in present]
        numeric = [number for number in numbers if number is not None]
        if numeric:
            column["min"] = min(numeric)
            column["max"] = max(numeric)
            column["mean"] = sum(numeric) / len(numeric)
    return column


def profile_csv(path: Path) -> dict[str, object]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError("CSV has no header row")
        names = [name for name in reader.fieldnames if name is not None]
        columns: dict[str, list[str]] = {name: [] for name in names}
        rows = 0
        for row in reader:
            if not any((value or "").strip() for value in row.values()):
                continue
            rows += 1
            for name in names:
                columns[name].append(row.get(name) or "")

    return {
        "path": str(path),
        "rows": rows,
        "columns": [profile_column(name, columns[name]) for name in names],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Profile a CSV file as JSON.")
    parser.add_argument("--csv", required=True, type=Path)
    parser.add_argument("--json", action="store_true", help="emit JSON (the default)")
    args = parser.parse_args(argv)

    try:
        report = profile_csv(args.csv)
    except (OSError, ValueError, csv.Error) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
