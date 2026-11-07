# Article notes — "Memory in Agents"

Section-by-section: what the article says, and what this repository does.

## Part 1 — Understanding STM

The article defines STM as thread-scoped state: per-conversation messages,
lost when the thread ends unless checkpointed. The characteristics table
(scope, persistence, speed, growth, use case) is accurate and is reproduced in
the lesson.

**Adopted as stated.** `app/stm.py` is exactly that.

## Part 2 — STM with LangGraph

Checkpointer, `thread_id`, `MessagesState`, `add_messages`.

One correction: the article says `MessagesState` includes
`user_input: Optional[str]`. It does not. In langgraph 0.6 its only field is
`messages: Annotated[list[AnyMessage], add_messages]`. Adding `user_id` requires
subclassing, which the article does later without mentioning the earlier error.

**Adopted with the comment corrected.**

## Part 3 — STM code

A one-node graph over `MessagesState`, `InMemorySaver`, two threads, Alice and
Bob.

Runs as written. **Adopted.** `tests/test_stm.py` asserts the isolation the
article demonstrates.

## Part 4 — PostgresSaver

`ConnectionPool`, `PostgresSaver(conn=pool)`, `checkpointer.setup()`.

The code is correct. `app/postgres.py` keeps the shared pool and calls
`setup()`. It is not exercised by the tests because it needs a database.

One addition: the article's "state persists across restarts" demo creates a
second graph in the same process, which does not actually prove a restart. A
real check needs a new process pointed at the same `thread_id`.

## Part 5 — Managing STM size

Three strategies: trim, delete, summarize.

- **Trim** — `trim_messages(...)` as written. Adopted.
- **Delete** — the code is broken twice: `to_remove = msgs[-keep_count:]`
  selects the newest messages, and `return {"messages": msg}` references an
  undefined `msg`. The import is also wrong (`langchain.messages`). Replaced
  with `delete_messages(ids)`.
- **Summarize** — the article returns `{"messages": [summary] + recent}`.
  `add_messages` appends, and messages with existing ids are updated in place,
  so this either duplicates `recent` or leaves the summary at the end. Here the
  summary goes into its own `summary` state key and the old messages are
  removed with `RemoveMessage`.

The `langmem.SummarizationNode` snippet is mentioned but not shipped: it is a
different package and the article's call shape (`summarization_node.summarize`)
is not the documented interface. The lesson explains the idea; the example
implements summarization directly.

## Part 6 — Understanding LTM

Store, namespace, semantic search, cross-session persistence. Accurate.

Adopted: `app/ltm.py` uses `(user_id, "facts")` and the four store operations.

## Part 7 — LTM with LangGraph

Namespace examples and the `BaseStore` interface. Accurate.

One nuance the article skips: `search(query=...)` is only semantic when the
store was constructed with an embedding index. Without one, the query is
accepted and ignored, and every item comes back with `score=None`. Verified
against `InMemoryStore` in `tests/test_ltm.py`.

## Part 8 — LTM code

InMemoryStore, extended state, retrieve/agent/update nodes.

Two defects:

1. `retrieve_user_facts` returns `{"context": ...}`, but `AgentState` has no
   `context` key. LangGraph drops unknown keys silently, so the retrieval node
   has no effect on state. The agent re-reads the store itself, which hides the
   bug.
2. `store.search(query=...)` on a plain `InMemoryStore` is not semantic (see
   Part 7).

Here `memory_context` is a declared key and retrieval happens once.

## Part 9 — PostgresStore

pgvector, `PostgresStore(index={...})`, `store.setup()`.

Adopted in `app/postgres.py`, including the shared pool. The article's SQL
inspection example (`SELECT * FROM store WHERE prefix = ...`) does not match the
tables the library creates; the lesson avoids repeating it.

## Part 10 — Combined finance agent

`retrieve_ltm`, `finance_agent`, `update_ltm`, compiled with the checkpointer.

Three problems:

- `retrieve_ltm` writes an undeclared `context` key (dropped), then
  `finance_agent` reads the same profile from the store again.
- The graph is compiled without `store=`, so the store is a module global; the
  dependency is invisible.
- `update_ltm` parses model JSON inside a bare `except`, so a parse failure is
  indistinguishable from "no new facts".

Here the combined graph declares every key, compiles with the store, and keeps
one retrieval node.

## Part 11 — Best practices

Thread vs user id, context management, timing.

The thread/user split is the most important sentence in the article and is
adopted. Timing is described in prose only; the example does not add metrics.

## What this repository adds

- Hash-keyed facts, so repeated extraction is idempotent.
- `forget_user`, because personal memory needs a delete path.
- A `summary` state key instead of mixing summaries into the message list.
- Tests for the behaviors the article asserts but does not check: isolation,
  trimming, replacement, dedupe, the no-index caveat.
