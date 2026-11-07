# Memory in agents — short-term and long-term, rebuilt

The architecture is the article's: a checkpointer for thread-scoped short-term
memory, a namespace store for cross-thread long-term memory, trimming and
summarization, and one combined agent. Several code paths in the article do not
run as written; every fix is listed below and explained in
[`docs/article-notes.md`](docs/article-notes.md).

## The two memories

|                  | Short-term (STM)                                 | Long-term (LTM)                           |
| ---------------- | ------------------------------------------------ | ----------------------------------------- |
| Scope            | one `thread_id`                                  | one `user_id`, across threads             |
| Mechanism        | checkpointer (`InMemorySaver` / `PostgresSaver`) | store (`InMemoryStore` / `PostgresStore`) |
| Content          | the message list and state keys                  | facts extracted from turns                |
| Bounded by       | trimming + summarization in the prompt           | namespace + retrieval limit               |
| Survives restart | only with `PostgresSaver`                        | only with `PostgresStore`                 |

## Layout

```text
app/
├── stm.py        # message graph + checkpointer; thread isolation
├── history.py    # trim, summarize (RemoveMessage), delete, summary key
├── ltm.py        # namespace store, fact extraction, dedupe, recall, forget
├── graph.py      # compress → retrieve → agent → extract
├── postgres.py   # PostgresSaver + PostgresStore over one pool
├── llm.py        # ChatOpenAI pointed at DeepSeek
├── config.py     # one settings object
└── cli.py        # demo | facts | chat | forget
tests/
└── test_stm.py, test_history.py, test_ltm.py, test_graph.py
docker/docker-compose.yml   # pgvector/pgvector:pg16
```

## Run it

```shell
cp .env.example .env      # set OPENAI_API_KEY
uv sync

uv run python main.py demo        # STM: two threads, separate state
uv run python main.py facts       # LTM: same user, new thread
uv run python main.py chat        # both, interactive
uv run pytest -q
```

`demo` needs no database. `facts` and `chat` use in-memory stores unless you
pass `--postgres`, which requires the database below.

## Workflow

| step | command | what it shows |
| ---- | ------- | ------------- |
| 1 | `demo` | two threads, two histories; the third turn still knows the name |
| 2 | `facts` | facts stored under one `user_id`, recalled in a new thread |
| 3 | `chat` | both memories in one session (choose user id and thread id) |
| 4 | `pytest -q` | 19 tests over the same behavior, with no network |

Every turn in `facts` and `chat` runs `compress → retrieve → agent → extract`:

1. `compress` summarizes the old window and removes those messages.
2. `retrieve` reads the user's facts into `memory_context`.
3. `agent` calls the model with system prompt + facts + summary + trimmed window.
4. `extract` pulls durable facts from the human turn and writes them to the store.

The checkpointer stores the full thread; the model sees the bounded window. That
separation is the point of the example.


### PostgreSQL (optional)

```shell
docker compose -f docker/docker-compose.yml up -d
psql "postgresql://postgres:postgres@localhost:5432/agent_memory" -c "CREATE EXTENSION IF NOT EXISTS vector;"
```

Then set `DATABASE_URL` and run with the flag **before** the subcommand:

```shell
uv run python main.py --postgres facts
```

`PostgresSaver.setup()` and `PostgresStore.setup()` create their tables. The
`vector` extension is only needed for semantic recall.

### Semantic recall (optional)

Without an embedding provider, `store.search(query=...)` accepts the query and
ignores it — items come back with `score=None`. That is LangGraph's behavior,
not a bug in this repo. To get ranked recall:

```shell
EMBED_MODEL=text-embedding-v4
EMBED_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
EMBED_API_KEY=...
EMBED_DIMS=1536
```

DeepSeek does not serve embeddings; point these at a provider that does.

## What changed from the article

| Article                                                              | Here                                                    | Why                                                                                             |
| -------------------------------------------------------------------- | ------------------------------------------------------- | ----------------------------------------------------------------------------------------------- |
| `MessagesState includes user_input`                                  | only `messages`                                         | Current `MessagesState` is `messages: Annotated[list[AnyMessage], add_messages]`.               |
| Nodes return `{"context": ...}` on a state without that key          | `memory_context` is declared                            | Undeclared keys are silently dropped; the context never reaches the next node. Verified on 0.6. |
| `store.search(query=...)` with a plain `InMemoryStore`               | query only passed when an index exists                  | Without embeddings the query is ignored and `score` is `None`; there is no semantic search.     |
| Delete helper takes `msgs[-keep_count:]` and returns `msg`           | `delete_messages(ids)`                                  | The original deletes the _newest_ messages and references an undefined variable.                |
| `from langchain.messages import RemoveMessage`                       | `langchain_core.messages`                               | Import moved.                                                                                   |
| `return {"messages": [summary] + recent}`                            | summary stored in a `summary` key; old messages removed | `add_messages` preserves existing ids, so appending re-adds a second copy of `recent`.          |
| Combined agent compiles without `store` and re-reads it in two nodes | one `retrieve` node, `compile(store=...)`               | The article's duplication hides which node owns retrieval.                                      |
| Facts appended with random UUIDs                                     | key = hash of normalized text                           | Re-extracting the same fact should overwrite, not duplicate.                                    |
| No deletion path                                                     | `forget_user` + `main.py forget`                        | Long-term memory holds personal data; it needs an erase path.                                   |

## Test suite

19 tests, no network, no database, no provider key. They cover thread
isolation, message accumulation, trimming, summarization via `RemoveMessage`,
fact extraction and dedupe, namespace isolation, the declared `memory_context`
key, and the "no index means no ranking" caveat.

## Known limits

- The PostgreSQL path is not exercised by the tests and was not run here
  (no Docker daemon). It is a documented gate, not a verified claim.
- Verified live against DeepSeek `deepseek-chat` and Qwen `text-embedding-v4`
  (1536 dims): thread isolation, fact extraction, cross-thread recall, and
  ranked semantic search with real scores. One run, not a benchmark.
- Extraction quality is prompt-dependent; there is no eval for "is this fact
  worth remembering".
- No TTL, no per-fact confidence, no conflict resolution when a new fact
  contradicts an old one.
