# Phase 4 — Chunking, embeddings, and database ingestion plan

## Goal

Turn the selected fiscal-year-2025 Markdown filing(s) into structurally useful,
size-bounded chunks; embed the chunks with Qwen `text-embedding-v4`; and store
them in `public.document_chunks`, linked to the existing `source_documents`
records. The current requested scope is Google's GOOGL filing only. The first
live embedding/write is strictly limited to one selected chunk. Do not start a
bulk embedding run until that pilot is reviewed and approved.

## Verified current state

- `data/markdown/manifest.json` describes 25 filings across 2021–2025 and
  five tickers. Their full Markdown content is already in
  `public.source_documents`. Filtering by `fiscal_year=2025` selects exactly
  five filings (one per ticker).
- `public.document_chunks` has the fields `document_id`, `chunk_index`,
  `content`, `section`, `token_count`, `source_start`, `source_end`,
  `embedding vector(1536)`, generated `search_vector`, and JSONB `metadata`.
- `source_documents` has a unique `(ticker, accession_number)` key; chunks
  have a unique `(document_id, chunk_index)` key.
- Docling's native chunkers accept a `DoclingDocument`, not a Markdown string.
  The local `.md` files can be loaded with `DocumentConverter` before chunking.
- The existing Markdown conversion exports document text but not a source
  character-offset map. Original HTML/page provenance therefore cannot be
  assumed to be recoverable from the exported Markdown.

## Documentation findings and decisions

### Chunking

Docling documents two native chunkers:

- `HierarchicalChunker` emits chunks based on detected document elements,
  generally merging list items and attaching relevant headings/captions and
  document provenance.
- `HybridChunker` starts from the hierarchical chunks, then uses a tokenizer
  to split oversized chunks and optionally merge adjacent undersized peers
  with matching headings/captions. `contextualize(chunk)` adds the heading and
  caption context intended for embedding.

Therefore, do not run the two chunkers in sequence and embed both outputs.
During the pilot, inspect both the hierarchical elements and the final Hybrid
chunks to understand the structural transformations. Embed only Hybrid's
final, contextualized chunks.

### Embedding constraints

Alibaba Cloud's current `text-embedding-v4` documentation lists:

- Maximum 8,192 tokens per input item.
- A maximum of 10 input rows per synchronous request.
- 1,536 dimensions as a supported output size, matching the existing
  `vector(1536)` column.

Use an initial Hybrid maximum of **7,000 tokens** for the *contextualized text*
to leave room below the provider limit. Count the exact string sent to the
embedding API, not only `chunk.text`. Confirm the tokenizer used for the hosted
`text-embedding-v4` model before setting the production tokenizer: Docling
recommends aligning the chunker tokenizer with the embedding model tokenizer,
but a similarly named downloadable tokenizer must not be assumed equivalent
without verification. Add a preflight assertion that every serialized chunk
is below both the configured chunk cap and the provider's 8,192-token limit.

The initial pipeline uses the public `Qwen/Qwen3-Embedding-0.6B` tokenizer,
which matches the Qwen3-Embedding model family named by the `text-embedding-v4`
documentation. The 7,000-token cap leaves a 1,192-token margin; verify against
the configured DashScope region before the first live pilot.

### Implemented pipeline and pilot status

- `data/ingest_chunks.py` defaults to the five `fiscal_year=2025` filings.
- Running it without `--pilot` or `--all` is a local dry run only.
- `--pilot --ticker TICKER --max-cost-cny LIMIT` embeds and inserts at most one
  first chunk from one filing.
- `--all --max-cost-cny LIMIT` is a distinct, explicit bulk operation and can
  be combined with `--ticker TICKER` to ingest only one company's filing.
- The verified GOOGL-only dry run produced 53 hybrid chunks, 309,229
  estimated input tokens, and an estimated cost of CNY 0.1589. This fits
  within a 1-million-token allowance if that allowance is unused.
- The one-chunk GOOGL pilot has been run, and its saved data was verified in
  Supabase.
- Chunk metadata includes filing identity and dates, source URL, Docling
  provenance, available page references, and embedding details. The database
  generates `search_vector` from chunk content on inserts and updates.
- `--all` skips unchanged chunks, re-embeds and updates changed uncited chunks,
  refuses to overwrite cited chunks, and removes stale uncited chunks only
  after the selected filing(s) have completed successfully.
- Live modes require the DashScope key/base URL, a cost cap, and matching
  fiscal-year-2025 source-document rows. The current script validates all five
  2025 source rows before writing, even when only GOOGL chunks are selected.
- Bulk ingestion of the remaining GOOGL chunks has not been run.

Keep the dimension fixed at 1,536 unless the database schema and all retrieval
consumers are deliberately migrated together.

### Citations and source locations

Keep `chunk.text` as the stored searchable content and use
`chunker.contextualize(chunk)` as the embedding input. Preserve Docling's
headings, page references, captions, and item provenance in chunk JSONB
metadata; store a concise heading path in `section`.

The schema expects offsets into the original `source_documents.content`.
Docling chunk provenance does not directly provide character offsets into the
Markdown export. The pipeline maps chunks by exact text or normalized
alphanumeric text; it leaves offsets null if neither mapping verifies the
chunk. The latest GOOGL dry run found no matches among its 53 chunks, so exact
source offsets remain unresolved and must not be used for citation navigation.
Docling metadata is retained regardless of whether an offset can be recovered.

## Implementation sequence

### 1. Confirm model and runtime configuration

- Verify the configured DashScope region, model identifier, API endpoint,
  supported request format, tokenizer availability, and current price for that
  region from the vendor docs/account.
- Add `DASHSCOPE_API_KEY` to the backend settings module as a secret; do not
  read environment variables directly in the data script or print the key.
- Reuse the existing `openai` dependency only if the selected DashScope
  endpoint is OpenAI-compatible; otherwise use the vendor's documented client
  or HTTP interface. Do not add a dependency before confirming this.
- Do not make embedding requests during this setup stage.

### 2. Add deterministic chunk extraction

- Add a standalone script under `data/` that reads the local Markdown
  manifest and files; keep this ingestion pipeline out of FastAPI request code.
- Load each Markdown file with Docling's `DocumentConverter` to obtain a
  `DoclingDocument`.
- Instantiate `HierarchicalChunker` for structural inspection and
  `HybridChunker` with the verified tokenizer and a 7,000-token cap.
- Enumerate final Hybrid chunks in a stable document order, retaining the
  uncontextualized text, contextualized embedding text, heading/section,
  document provenance, page references, token counts, and source offsets when
  verified.
- Treat empty chunks, unsupported tokenization, chunks over the API limit,
  and missing manifest/source-document matches as explicit errors.

### 3. Add a no-cost preflight

- Provide a dry-run mode that never calls the embedding API and never writes
  to Supabase.
- Report chunks per filing, total chunks, token-count distribution, largest
  contextualized chunk, unmapped offsets, and estimated input-token total.
- Estimate cost using the configured region's current price, and require the
  operator to review the estimate before choosing the full-run option.
- Verify that the DB schema is at Alembic head and every manifest filing has a
  matching `source_documents` row before any paid API call.

### 4. Add a one-chunk live pilot (required gate)

- Require an explicit `--limit-chunks 1`/pilot mode and a selected filing;
  select the first deterministic chunk or allow a stable chunk index.
- Before calling the paid API, print the selected ticker/accession, chunk
  index, token count, and estimated cost; do not print secrets or full filing
  content.
- Request one embedding with `dimensions=1536`. Validate the response count,
  finite numeric values, and exactly 1,536 vector elements.
- Insert or update only that one `document_chunks` row, using
  `(document_id, chunk_index)` as the conflict key. Do not clear existing
  chunks or trigger embeddings for any other filing.
- Verify the persisted chunk's content, metadata, generated full-text vector,
  token count, offsets, and vector dimension. Report the exact pilot record.
- Stop after this pilot. Bulk mode must be a separate explicit invocation
  after the user reviews and approves the pilot and cost estimate.

### 5. Add controlled, repeatable bulk ingestion

- Only after pilot approval, submit at most 10 inputs per synchronous
  embedding request, respecting both row and per-item token limits.
- Match returned vectors to inputs by response index/ID and validate each
  vector before writing.
- Write chunks in bounded database transactions. Stable chunk indices and
  upserts make retries safe; unchanged chunks are skipped without embedding
  again, and changed uncited chunks are re-embedded and updated.
- Reconcile stale chunks after all selected chunks have been written. The
  pipeline refuses to update or remove chunks referenced by citations, since
  deleting a cited chunk can cascade to citation records.
- Log progress by ticker, accession number, chunk counts, retryable failures,
  and token usage without logging secrets or unnecessary full text.
- Support resuming after interruption without repeating successful embedding
  requests; persist a checkpoint or inspect existing chunks before deciding
  which inputs need paid embeddings.

### 6. Tests and verification

- Unit test Markdown manifest loading, metadata mapping, section extraction,
  deterministic chunk ordering, chunk token limits, source-offset mapping,
  and oversized/unmappable chunks.
- Mock the embedding API for batching, response ordering, dimensions,
  malformed responses, retry behavior, and error propagation.
- Test database writes and conflict updates without a live Supabase dependency.
- Run the pilot against Supabase only after confirming the target project and
  showing the one-chunk cost estimate. Do not run full ingestion as part of
  routine tests.
- Once the pilot is accepted, run bulk ingestion explicitly and verify
  per-document chunk counts, `vector(1536)` values, generated `search_vector`
  values, and no missing/duplicate chunk indices.

## Acceptance criteria

- A dry run is deterministic, makes no embedding calls, and writes nothing.
- The chunker sizes the final contextualized payload under the verified
  tokenizer's configured cap and the provider's hard 8,192-token limit.
- The pilot performs exactly one embedding request for one selected chunk and
  writes exactly one chunk row.
- A pilot row can be read back with its source-document link, expected
  metadata, verified offsets or documented provenance fallback, populated
  generated full-text vector, and a 1,536-element embedding.
- No bulk embedding run occurs until the user explicitly approves the pilot
  outcome and cost estimate.
- After approval, the full run is resumable and idempotent.

## Official references

- [Docling chunking concepts](https://docling-project.github.io/docling/concepts/chunking/)
- [Docling Hybrid chunking example](https://docling-project.github.io/docling/_generated/examples/hybrid_chunking/)
- [Alibaba Cloud text embedding synchronous API](https://help.aliyun.com/en/model-studio/text-embedding-synchronous-api)
- [Current implementation checklist](./todo.md)
- [Data conversion and source-document ingestion commands](../data/README.md)
