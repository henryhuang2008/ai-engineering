"""Group a CSV by one column and summarize another. Stdlib only, JSON out."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

AGGREGATIONS = ("count", "sum", "mean", "min", "max")


def summarize(value: str, aggregation: str, values: list[float]) -> float | int | None:
    if aggregation == "count":
        return len(values)
    if not values:
        return None
    if aggregation == "sum":
        return sum(values)
    if aggregation == "mean":
        return sum(values) / len(values)
    if aggregation == "min":
        return min(values)
    return max(values)


def aggregate(path: Path, group: str, value: str | None, aggregation: str) -> dict:
    grouped: dict[str, list[float]] = defaultdict(list)
    seen: dict[str, int] = defaultdict(int)

    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError("CSV has no header row")
        for field in [group, value] if value else [group]:
            if field not in reader.fieldnames:
                raise ValueError(f"column {field!r} not found; have {reader.fieldnames}")

        for row in reader:
            key = (row.get(group) or "").strip() or "(empty)"
            seen[key] += 1
            if value:
                raw = (row.get(value) or "").strip()
                try:
                    grouped[key].append(float(raw))
                except ValueError:
                    continue
            else:
                grouped[key].append(0.0)

    results = []
    for key in sorted(seen):
        numbers = grouped.get(key, [])
        results.append(
            {
                "group": key,
                "rows": seen[key],
                "n": len(numbers),
                "value": summarize(value or "", aggregation, numbers),
            }
        )

    return {
        "path": str(path),
        "group_by": group,
        "value": value,
        "aggregation": aggregation,
        "results": results,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Group a CSV and summarize a numeric column.")
    parser.add_argument("--csv", required=True, type=Path)
    parser.add_argument("--group", required=True)
    parser.add_argument("--value")
    parser.add_argument("--agg", default="mean", choices=AGGREGATIONS)
    args = parser.parse_args(argv)

    if args.agg != "count" and not args.value:
        print("error: --value is required unless --agg count", file=sys.stderr)
        return 2

    try:
        report = aggregate(args.csv, args.group, args.value, args.agg)
    except (OSError, ValueError, csv.Error) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
