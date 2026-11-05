# Phase 5 — Retrieval implementation plan

## Implementation status

The standalone retrieval service is implemented in `backend/app/retrieval/`.
It provides Qwen query embeddings, bounded PostgreSQL vector and full-text
search with shared filing filters, RRF, result metadata hydration, and
same-filing neighbor reads. It is intentionally not wired into the chat route
or a PydanticAI agent; that integration remains Phase 6 work.

Create and close the service in the eventual application lifespan or
dependency container:

```python
from app.retrieval import SearchFilters, create_retriever

async def search():
    retriever = create_retriever()
    try:
        return await retriever.search_filings(
            "How did revenue change?",
            SearchFilters(ticker="GOOGL", fiscal_year=2025, filing_type="10-K"),
        )
    finally:
        await retriever.aclose()
```

Default retrieval tests use fake embedding and database boundaries and need no
credentials. The client-brief relevance evaluation remains open because the
brief and its expected passage judgments are not present in the repository.

## Goal

Given an analyst question and optional company, fiscal-year, and filing-form
filters, return a small, ordered set of relevant filing passages with enough
source metadata and neighboring context for the Phase 6 agent to ground and
cite its answer.

Phase 5 implements retrieval as an independent, typed backend capability. It
does not add an LLM agent or change the chat stream; those belong to Phase 6.

## Current state and constraints

- The existing chat endpoint still emits a deterministic stub; it does not
  retrieve documents.
- `document_chunks` contains chunk text, `vector(1536)` embeddings, a generated
  English `search_vector`, chunk indices, optional source offsets, and JSONB
  metadata. `source_documents` contains ticker, fiscal year, filing type,
  filing date, accession number, source URL, and full Markdown content.
- Qwen settings already exist in `app.config`: `DASHSCOPE_API_KEY`,
  `QWEN_BASE_URL`, `QWEN_EMBEDDING_MODEL`, and
  `QWEN_EMBEDDING_DIMENSIONS`. The configured model and dimensions must match
  the model used to embed stored chunks.
- The database currently has GOOGL's 2025 chunks confirmed by the user. Other
  company/year combinations should return no results rather than imply corpus
  coverage that is not present.
- Some chunk source offsets may be null. Retrieval must return that fact as
  unavailable and must not manufacture character or page locations.
- Existing backend request handlers are async; avoid blocking the event loop
  with synchronous database or embedding calls.
- No new top-level dependency was needed. SQLAlchemy uses its `asyncio` extra
  (including greenlet) for the non-blocking Psycopg 3 session; the OpenAI SDK,
  pgvector SQLAlchemy type, Psycopg 3, Pydantic, and PydanticAI were already
  dependencies.

## Reference repository patterns and adaptation

The linked [hybrid-retrieval example](https://github.com/daveebbelaar/ai-cookbook/tree/main/knowledge/hybrid-retrieval)
separates dense retrieval, lexical retrieval, rank fusion, and evaluation into
small components. Its
[retrievers](https://github.com/daveebbelaar/ai-cookbook/blob/main/knowledge/hybrid-retrieval/utils/retrievers.py)
produce independent ranked lists, and its
[fusion helper](https://github.com/daveebbelaar/ai-cookbook/blob/main/knowledge/hybrid-retrieval/utils/fusion.py)
uses Reciprocal Rank Fusion (RRF) on document IDs rather than mixing
incomparable raw scores. Its
[evaluation script](https://github.com/daveebbelaar/ai-cookbook/blob/main/knowledge/hybrid-retrieval/6-evaluate.py)
compares retrieval stages with NDCG@10 against relevance judgments.

Adapt those boundaries to this product:

- Replace local BM25 with Postgres full-text search over `search_vector`.
- Replace in-memory dense scoring with a bounded `pgvector` cosine-distance
  query.
- Apply identical filing filters to both database searches before ranking.
- Use RRF to merge chunk IDs and ranks; do not average cosine distance and
  `ts_rank` scores.
- Do not copy the example's local BM25 indexes, module-global OpenAI client,
  direct environment reads, or Cohere reranker. The app uses settings-based
  configuration and this phase does not include reranking.

The example is not itself a PydanticAI orchestration pattern. In this app,
retrieval remains a standalone service testable without an LLM. Phase 6 will
expose its typed search and passage-reading methods as bounded PydanticAI
tools, using explicit agent dependencies as described in
[architecture.md](./architecture.md). The agent will not generate SQL or
implement its own ranking logic.

The Phase 6 handoff should be explicit: `DocumentAgentDeps` receives the
retriever, and tools such as `search_filings`, `read_chunk`, and
`read_surrounding_chunks` call that retriever and return typed passage models.
PydanticAI chooses when to call those tools; the retrieval module owns the
filters, SQL, ranking, and source lookup. Retrieval unit tests therefore do
not instantiate an agent or call a language model.

## Module boundaries

```text
backend/app/
├── retrieval/
│   ├── models.py       # Search filters, ranked chunk, passage/source types
│   ├── embeddings.py   # Async query embedding via configured Qwen endpoint
│   ├── queries.py      # Parameterized pgvector and Postgres FTS statements
│   ├── fusion.py       # Pure Python Reciprocal Rank Fusion
│   └── retriever.py    # Hybrid search, source hydration, neighbor reads
└── database/
    └── documents.py    # Shared document/chunk reads if a third caller appears
```

Keep the initial implementation focused; place database query helpers in
`retrieval/queries.py` unless another database feature needs to reuse them.
Add files only where responsibilities warrant them.

## Implementation sequence

### 1. Define retrieval contracts and bounds

- Add typed optional filters for `ticker`, `fiscal_year`, and `filing_type`.
- Define typed results that include chunk ID/index, document ID, text, section,
  optional source offsets, ticker/company, fiscal year, form, filing date,
  accession number, source URL, and retrieval scores/ranks.
- Set explicit limits for candidate count, final result count, and neighbor
  window. Start with up to 50 candidates from each retriever, 10 fused results,
  and one neighbor on either side; keep constants bounded and adjust only
  from evaluation.
- Validate the query is non-empty and cap its length before provider/database
  work.

### 2. Embed the query

- Use the existing Qwen model, endpoint, API key, and 1,536 dimensions, through
  the async OpenAI-compatible client so network I/O does not block FastAPI.
- Request one query vector and validate response count, dimension, and finite
  values before passing it to SQL.
- Keep query embedding independent of PydanticAI and chat orchestration.
- Return provider errors explicitly; do not silently fall back to lexical-only
  search because that would hide a broken hybrid path.

### 3. Implement bounded database retrievers

- Semantic query: join chunks to source documents, apply the optional metadata
  filters, order by pgvector cosine distance ascending, and limit candidates.
- Lexical query: build an English `tsquery` with
  `websearch_to_tsquery('english', :query)`, match the generated
  `search_vector`, rank with `ts_rank_cd`, apply the same filters, and limit
  candidates.
- Parameterize all user-provided query and filter values. Never build SQL by
  interpolating query text.
- Return IDs and ranks/scores from each branch. Fetch selected passage content
  and filing metadata after fusion rather than transferring the full corpus.
- Use a non-blocking database strategy compatible with existing Psycopg 3 and
  SQLAlchemy. Prefer the async Psycopg dialect; if implementation uses the
  current synchronous engine, offload those calls to the thread pool.
- Check the existing HNSW and GIN indexes against the actual query shapes.
  Add a migration or new index only if query plans and corpus measurements
  show the current schema is insufficient.

### 4. Fuse ranked candidates

- Implement a pure function:
  `rrf_score(id) = sum(1 / (k + rank))`, with ranks starting at 1.
- Start with the reference's conventional `k=60`, and combine the semantic
  and lexical result lists by stable chunk ID.
- Use deterministic tie-breaking (for example, fused score then chunk ID).
- Return the top bounded result set, preserving each branch's rank and score
  for observability and evaluation.

### 5. Hydrate passages and read neighbors

- Fetch final chunks with their source-document metadata and restore the fused
  result order explicitly.
- Implement bounded neighboring-passage reads within the same document using
  adjacent `chunk_index` values; do not cross filing boundaries.
- Include existing section/page/provenance metadata. If offsets are null,
  represent them as null and use the available section and Docling provenance
  instead.
- Keep this API typed and independent so Phase 6 tools can call
  `search_filings`, `read_chunk`, and `read_surrounding_chunks` without direct
  database access.

### 6. Unit and integration testing

- Unit tests (no network/DB): query validation and embedding-response checks;
  SQL query shape, filter application, and limits; RRF rank math, duplicates,
  missing items, empty lists, and deterministic ties; result hydration order;
  and neighbor bounds/document isolation.
- Mock the embedding and database boundaries to verify error propagation and
  that both searches receive the same filters.
- Mark live Qwen/Postgres tests `integration`; never run them as part of the
  default fast suite.
- Add retrieval evaluation cases from the actual client brief. Record expected
  companies/years and relevant passages, then review top-k coverage and
  ranking (e.g. Recall@k or NDCG@10 where relevance grades are available).
- The workspace checklist references ten client-brief questions, but the
  brief itself was not found in the repository during planning. Locate that
  source before claiming the ten-question retrieval acceptance check is done;
  do not invent expected answers or relevance labels.

## Acceptance criteria

- The same query and filters produce bounded semantic and lexical rankings;
  both branches constrain results to the same ticker/year/form scope.
- RRF combines ranks, not raw scores, and has deterministic ordering.
- Final results contain enough source-document and chunk metadata for the
  Phase 6 agent to cite; missing offsets remain explicitly unavailable.
- Neighbor reads are limited to adjacent chunks from the same filing.
- Unit tests run without credentials, network, or Supabase.
- Integration/evaluation results demonstrate expected client-brief company
  and year coverage before Phase 5 is marked complete.
- No BM25, reranker, new API route, or PydanticAI agent is added in this phase;
  those are either replaced by the locked Postgres stack or belong to Phase 6.

## Not included in Phase 5

- PydanticAI agent configuration, tools, grounding checks, and chat-stream
  integration (Phase 6).
- Cohere or another cross-encoder reranker (not in the Phase 5 checklist).
- Re-embedding filings or changing the embedding model/dimension.
- Frontend citation UI (Phase 7).
