---
name: csv-insights
description: Profile a CSV file and answer questions about its columns, types, missing values and numeric spread. Use when the user points at a .csv file and asks what is in it, whether a column is trustworthy, or for a quick summary before deeper analysis.
---

# CSV insights

## When to use this skill

Use it when a question can be answered from a CSV's shape and column-level
statistics: row counts, inferred types, missing values, distinct counts, min,
max and mean. Do not use it for joins across files or for charting.

## Workflow

1. Profile the file:

   ```bash
   python ${SKILL_DIR}/scripts/profile.py --csv data/sales.csv --json
   ```

2. Read `references/metrics.md` before choosing which numbers to report. It
   defines what each statistic means and which ones are misleading on skewed
   data.

3. For a grouped summary, run the aggregate script:

   ```bash
   python ${SKILL_DIR}/scripts/aggregate.py --csv data/sales.csv --group region --value amount --agg mean
   ```

## Rules

- Report the row count before any percentage, so the reader can judge the base.
- Say "inferred" when naming a column type: the script guesses from the first
  non-empty values, not from a schema.
- Never report a mean without the count and the missing-value count for that
  column.
- If a column is all-empty, say so; do not invent a type.
- Quote numbers exactly as the script prints them. Do not round silently.

## Files

- `scripts/profile.py` - JSON profile of a CSV.
- `scripts/aggregate.py` - group-by summary with one metric.
- `references/metrics.md` - definitions and the skew warning.
