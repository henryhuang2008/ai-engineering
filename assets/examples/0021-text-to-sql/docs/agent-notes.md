# Notes on the reference: Build a custom SQL agent

Source:
<https://docs.langchain.com/oss/python/langgraph/sql-agent> (fetched 2026-11-08).
This file records what the tutorial does, what this example keeps, and where it
deliberately differs. The differences are design choices, not claims that the
tutorial is wrong.

## What the tutorial builds

1. A local `Chinook.db`, downloaded from a public GCS bucket.
2. Three tools over `sqlite3`: `sql_db_list_tables`, `sql_db_schema` (DDL plus
   three sample rows per table), and `sql_db_query` (executes whatever it is
   given and returns `str(cursor.fetchall())`).
3. Five nodes: `list_tables` (a hard-coded tool call), `call_get_schema`
   (forces `tool_choice="any"`), `get_schema` (a `ToolNode`), `generate_query`
   (model bound to `sql_db_query`), and `check_query` (a second model that
   proofreads the SQL).
4. The graph:

   ```text
   START → list_tables → call_get_schema → get_schema → generate_query
              ↑                                              │
              └────────────── run_query ←── check_query ←────┘
   ```

   `should_continue` ends the run when the model answers without a tool call.

5. Human-in-the-loop: wrap the query tool in another `@tool`, call
   `interrupt([request])` inside it, and put the wrapper in a `ToolNode`. The
   graph is recompiled with `InMemorySaver()`, because a pause needs a
   checkpointer.

## The tutorial's own warning

> These database tools are minimal wrappers for demonstration purposes only.
> They are not intended to be secure or used in production.

`sql_db_query` opens a read/write `sqlite3.connect`, executes any string, has no
row cap and no timeout. The graph can also loop between `run_query` and
`generate_query` without a limit. A model that emits `DELETE FROM Invoice` or a
cartesian join is not stopped by the code.

That is the gap this example fills. It is the reason the lesson spends a section
on the guard rather than treating SQL execution as a detail.

## Where this example differs

| topic | tutorial | this example | why |
| --- | --- | --- | --- |
| data | downloads Chinook | builds SQLite from four CSVs | offline, deterministic numbers |
| schema | list tables, then fetch schema with sample rows | one `load_schema` node with DDL and counts | four small tables; no need for two tool round-trips |
| execution | `sql_db_query` tool inside `ToolNode` | `execute` node calls `db.run_query` | the node owns the guard, the attempt counter and the approval result |
| tool | executes directly | bound as the model-facing contract; SQL runs in `execute` | the model still emits `{"query": …}`; only one code path executes SQL |
| guard | none | read-only URI, `query_only`, statement whitelist, keyword scan, outer `LIMIT`, 2 s deadline | the tutorial explicitly leaves this out |
| retry | unbounded loop | three attempts, then `fail` | a wrong model should not spin forever |
| review | always on in the second graph | `--review` flag, same graph | one graph to read, and the default run does not block |
| review payload | `{"type": "accept"`, `"edit"`, `"response"}` | `{"action": "approve"`, `"edit"`, `"reject"}` | the payload is ours to define; `interrupt` returns whatever was resumed |
| final answer | `generate_query` answers in a later turn | a separate `answer` node with a fresh prompt | keeps the SQL turn and the prose turn separate |
| streaming | `stream_events(..., version="v3")` | `invoke` plus `__interrupt__` | see the version note below |

### The `check_query` detail worth copying

The tutorial's checker is clever: it takes the tool call from the last assistant
message, asks a second model to reproduce or fix the SQL, then assigns the
original message id to the checker's reply:

```python
response.id = state["messages"][-1].id
```

Because `add_messages` replaces a message with the same id, the corrected tool
call takes the place of the original instead of appending a second one. Without
that assignment the graph would carry two tool calls for one query.

This example omits the checker to keep one model call per attempt. The guard
catches structural problems (writes, multiple statements, runaway queries); it
does not catch a query that runs but answers the wrong question. That is what
the checker and a human reviewer are for. If you add the checker, reuse the id.

### The streaming API in the tutorial is newer than the pinned version

The tutorial's human-review example uses:

```python
stream = agent.stream_events({"messages": [...]}, config, version="v3")
if stream.interrupted:
    action = stream.interrupts[0]
```

In `langgraph` 0.6.11 — the version this course pins — `CompiledStateGraph` has
no `stream_events` method (`stream`, `astream`, `astream_events` and
`astream_log` exist). The equivalent 0.6 API is what `app/cli.py` uses:

```python
state = graph.invoke(input, config)
while "__interrupt__" in state:
    payload = state["__interrupt__"][0].value
    state = graph.invoke(Command(resume=decision), config)
```

The pause and resume semantics are the same; only the inspection API differs.

## What this build still lacks

- An evaluation set for SQL correctness. Five hand-checked questions is a demo,
  not a benchmark.
- A cost-aware query planner. The 2-second cap protects the process, not the
  database.
- Row-level permissions. A read-only connection still sees every row in the
  file; a multi-tenant database needs views or a per-user policy.
- Schema retrieval for large databases. With hundreds of tables, the tutorial's
  `list_tables` → `get_schema` step is necessary; a single prompt cannot hold
  the whole schema.
