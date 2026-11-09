# 0021 — Text to SQL: a guarded LangGraph agent

A question in English becomes a SQLite query, a result, and an answer. The
graph is the shape of LangChain's
[custom SQL agent](https://docs.langchain.com/oss/python/langgraph/sql-agent)
tutorial, with three additions the tutorial leaves as an exercise: a read-only
guard, a retry limit, and a human approval interrupt.

```text
question
   │
   ├─ load_schema   schema + row counts, once
   ├─ generate      model calls the run_query tool with SQL
   ├─ review        optional interrupt: approve / edit / reject
   ├─ execute       guard → SQLite → rows or an error
   ├─ answer        model turns the rows into one or two sentences
   └─ fail          after three bad queries, stop with the last error
```

## Why a local database

The tutorial downloads Chinook from a public bucket. This example builds
`data/northstar.db` from four CSV files instead, so it runs offline and every
expected number is reproducible: **8 customers, 6 products, 12 orders, 19 line
items**. The questions below have fixed answers, which makes a wrong query
visible.

Nothing about the agent changes if you point it at Chinook or PostgreSQL; the
guard and the graph are the same. Only `app/db.py` is SQLite-specific.

## The two model calls

| call | input | output |
| ---- | ----- | ------ |
| `generate` | system prompt with the schema, the question, any earlier errors | a `run_query` tool call, or `INSUFFICIENT_SCHEMA: …` |
| `answer` | question, SQL, formatted rows | one or two sentences |

The SQL prompt is a contract: one statement, `SELECT`/`WITH` only, no `LIMIT`,
ISO dates, `completed`/`cancelled`/`pending` statuses, and the sentinel for
questions the schema cannot answer. Revenue is defined once, in the prompt, as
`SUM(quantity * unit_price)` over completed orders.

The model may also reply with a ` ```sql ` fence instead of a tool call; the
graph accepts either and the guard treats both the same way.

## The guard is the point

The tutorial's own warning says its tools are "not intended to be secure". This
example makes the missing layers explicit:

| layer | what it stops |
| ----- | ------------- |
| `file:…?mode=ro` URI | any write, even if the SQL gets past the text checks |
| `PRAGMA query_only = ON` | the same, at the connection level |
| one statement, `SELECT`/`WITH` only | stacked statements, DDL, `ATTACH` |
| forbidden-keyword scan | `INSERT`, `UPDATE`, `DELETE`, `DROP`, `PRAGMA`, … |
| outer `SELECT * FROM (…) LIMIT 50` | unbounded result sets and `SELECT *` |
| `set_progress_handler` + 2 s deadline | runaway recursive CTEs and cartesian joins |

The outer `LIMIT` is applied by the runner, not requested in the prompt, so a
model that ignores the instruction is still capped. The 50-row cap is not a
correctness guarantee — an aggregate query has one row and can still be wrong —
it is a memory and latency bound.

## Workflow

| step | command | what it shows |
| ---- | ------- | ------------- |
| 1 | `uv run python main.py build` | creates the database and prints row counts |
| 2 | `uv run python main.py schema` | exactly what the model is allowed to see |
| 3 | `uv run python main.py ask "…"` | one answer |
| 4 | `uv run python main.py ask "…" --show` | the answer plus the SQL and rows |
| 5 | `uv run python main.py ask "…" --review` | approve, edit or reject the SQL first |
| 6 | `uv run python main.py demo --show` | four questions end to end |
| 7 | `uv run pytest -q` | 29 offline tests |

Measured output from `demo --show` with DeepSeek `deepseek-chat` (abridged: the
full run prints each SQL statement and row set between the answers):

```text
=== 1. How many orders were completed?
10 orders were completed.

SQL (1 attempt(s)):
SELECT COUNT(*) AS completed_orders FROM orders WHERE status = 'completed'

Result:
completed_orders
1. 10

=== 2. What is total revenue from completed orders?
The total revenue from completed orders is 3111.0.

SQL (1 attempt(s)):
SELECT SUM(oi.quantity * oi.unit_price) AS total_revenue
FROM order_items oi JOIN orders o ON o.order_id = oi.order_id
WHERE o.status = 'completed'

=== 3. Which customer placed the most orders, and how many did they place?
Ava Chen placed the most orders, with 3 orders.

=== 4. What is the refund rate?
INSUFFICIENT_SCHEMA: refunds table (no refund/refunded column or table exists)
```

The fourth question is the important one. There is no refunds table and no
`refunded` status, so the correct behavior is to refuse. A model that invents
`WHERE status = 'refunded'` returns zero rows and sounds confident; the
sentinel is why this example can tell the difference.

## Commands

```bash
uv sync
cp .env.example .env        # Windows: Copy-Item .env.example .env

uv run python main.py build
uv run python main.py schema
uv run python main.py ask "Which products sold best?"
uv run python main.py ask "Which products sold best?" --show
uv run python main.py ask "Which products sold best?" --review
uv run python main.py demo --show
uv run pytest -q
```

`--review` prints the proposed SQL and reads one key: `a` approves, `e` edits
the statement, `r` rejects it. The graph pauses on `interrupt` and resumes with
`Command(resume=…)`, which is the tutorial's human-in-the-loop section. The
checkpointer is required for the pause; `build_graph` always supplies one.

## One turn, node by node

| node | reads | writes |
| ---- | ----- | ------ |
| `load_schema` | the database file | `schema`, the system prompt, the question |
| `generate` | messages | the assistant reply, `sql`, `tool_call_id`, `attempts` |
| `review` | `sql`, `attempts` | `approved`, possibly an edited `sql` |
| `execute` | `sql` | `result` or `error`, a tool/user message |
| `answer` | question, `sql`, `result` | the final assistant message |
| `fail` | `error`, `attempts` | a plain-language failure message |

`execute` is a node rather than a `ToolNode` because it owns three things a
tool call should not: the read-only guard, the attempt counter, and the
approval result. The `run_query` tool is still bound to the model — it is the
contract that makes the model produce `{"query": "…"}` instead of prose — but
SQL only runs inside `execute`.

## Files

| file | role |
| ---- | ---- |
| `app/db.py` | build from CSVs, schema text, guard, capped and timed execution |
| `app/graph.py` | state, nodes, routing, the review interrupt |
| `app/prompts.py` | SQL contract and answer prompt |
| `app/cli.py` | `build`, `schema`, `ask`, `demo`, the interrupt loop |
| `app/config.py` | env settings and paths |
| `app/llm.py` | `ChatOpenAI` pointed at DeepSeek |
| `data/*.csv` | the seed rows |
| `tests/` | guard, database, graph, retry, interrupt — no network |

## What was verified

- **Live, DeepSeek `deepseek-chat`:** five questions; four answered with one
  attempt each, the refund question refused with `INSUFFICIENT_SCHEMA`.
- **Numbers cross-checked with SQL:** 10 completed orders, revenue 3111.0,
  AOV 311.1, top product 27-inch Monitor at 987.0, top category Accessories at
  1110.0, three West customers.
- **Human review, live:** a piped `a` approved the proposed
  `SELECT COUNT(*) … WHERE region = 'West'` and the graph resumed to an answer.
- **Offline:** 29 tests pass with no network, no key and no database server.

## What is not verified

- No evaluation set. "Did the model write the right SQL?" is checked by reading
  five answers, not by a scored benchmark.
- No semantic review of the query. The tutorial's `check_query` node asks a
  second model to proofread the SQL; this example skips it and relies on the
  guard plus the retry loop. The reference's approach is in
  [`docs/agent-notes.md`](docs/agent-notes.md).
- The 2-second budget and 50-row cap are policy choices, not measured limits.
- The SQLite guard is not a sandbox. A read-only connection still allows a
  expensive query until the progress handler fires; a production system also
  needs per-user row-level permissions and a query cost limit.
- Only SQLite is exercised. The tutorial's Chinook file and a PostgreSQL
  variant are described, not run here.
