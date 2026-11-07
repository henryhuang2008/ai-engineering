# Metric definitions

Read this before reporting numbers. Every definition here matches what
`scripts/profile.py` computes, so the words in an answer can be traced to a
field in its JSON.

## Counts

- **rows** - data rows, excluding the header. Blank trailing lines are ignored.
- **missing** - empty cells in a column. Whitespace-only cells count as empty.
- **distinct** - unique non-empty values, case-sensitive.

## Inferred type

`int` if every non-empty value parses as an integer, `float` if every non-empty
value parses as a float, otherwise `text`. A single bad value demotes the whole
column to `text`; that is deliberate, because a mostly-numeric column with one
label is a category, not a measurement.

## Numeric statistics

- **min / max** - computed on parsed numbers only.
- **mean** - arithmetic mean of parsed numbers.

## The skew warning

A mean is only a fair summary when the values are roughly symmetric. On a
long-tailed column (revenue, session length, file size) the mean sits above the
typical value and reads as wrong to anyone who knows the data. When the spread
is large, report the count and the range and say the distribution is skewed
rather than quoting a mean as "typical".

## What this skill does not compute

No median, no percentiles, no standard deviation. If a question needs them, say
they are not available from this profile instead of estimating them.
