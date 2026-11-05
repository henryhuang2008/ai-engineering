# Data

Local data artifacts for development live here.

- `downloads/` holds raw source files fetched from SEC EDGAR, grouped by year.
- `markdown/` holds Docling-converted Markdown filings, grouped by year, with its own `manifest.json`.
- Downloaded and converted corpus payloads are gitignored because they can get large.
- Fetch a sample corpus with `uv run data/download.py` 

## Convert filings to Markdown

From the repository root, run:

```powershell
uv run --project backend python data/convert_to_markdown.py
```

The script uses the Docling dev dependency from the backend's `uv` environment.
It reads every `.htm` and `.html` file listed in `downloads/manifest.json`,
preserves the year folders and filing metadata, and writes `.md` files plus a
conversion manifest under `data/markdown/`. It does not delete the source files.
The output is regenerated when the command is run again.

Optional `--input-dir` and `--output-dir` arguments can be used to select other
directories. Run `uv run --project backend python data/convert_to_markdown.py --help`
for details.

## Ingest Markdown filings into Supabase

After applying the Alembic migration, set `DATABASE_URL` in `backend/.env` and
run from the repository root:

```powershell
uv run --project backend python data/ingest_source_documents.py
```

The script reads `markdown/manifest.json` and upserts each filing and its full
Markdown content into `public.source_documents`, keyed by ticker and accession
number. It updates existing rows on reruns and preserves the filing metadata
and source paths in the `metadata` column. An alternate manifest can be given
with `--manifest`.

## Chunk, embed, and ingest fiscal-year filings

The chunking pipeline defaults to fiscal year 2025, which currently selects
five filings from the Markdown manifest. First run the local dry run:

```powershell
uv run --project backend python data/ingest_chunks.py
```

The dry run uses Docling's hierarchical chunker for structural statistics and
its hybrid chunker for the final token-bounded chunks. It reports chunk counts,
token totals, and an estimated embedding cost; it does not call DashScope or
write to the database.

After reviewing the dry-run output and configuring `DASHSCOPE_API_KEY`,
`QWEN_BASE_URL`, and `DATABASE_URL` in `backend/.env`, test exactly one chunk.
For Google's 2025 filing, use:

```powershell
uv run --project backend python data/ingest_chunks.py --fiscal-year 2025 --pilot --ticker GOOGL --max-cost-cny 0.01
```

Pilot mode embeds only that filing's first chunk in deterministic order and
writes only that row to `public.document_chunks`. The cost cap is required and
checked before any API request. The script also verifies the fiscal-year-2025
source-document records in the database.

For only Google's 2025 filing, first run a dry run for the ticker to get its
specific chunk count and cost estimate:

```powershell
uv run --project backend python data/ingest_chunks.py --fiscal-year 2025 --ticker GOOGL
```

After reviewing the estimate and verifying the one-chunk pilot, embed and
ingest all remaining Google chunks with a cost cap you approve:

```powershell
uv run --project backend python data/ingest_chunks.py --fiscal-year 2025 --all --ticker GOOGL --max-cost-cny 0.20
```

Bulk ingestion is a separate explicit action; without `--ticker`, `--all`
selects all filings for the specified fiscal year. The 2025 GOOGL dry run
reported 53 hybrid chunks, 309,229 estimated input tokens, and an estimated
cost of CNY 0.1589. Choose a cap at or above the current estimate only if that
spend is acceptable; the cap is not a spending target.

The script uses `QWEN_EMBEDDING_MODEL=text-embedding-v4` and
`QWEN_EMBEDDING_DIMENSIONS=1536`, matching the database vector column. It
limits contextualized chunks to 7,000 tokens (below the model's documented
8,192-token per-input maximum), sends batches of no more than 10, and uses the
Qwen3 embedding tokenizer. Matching stored chunks are skipped; changed content
or embedding context is re-embedded and updated at the same chunk index when
the existing row has no citations. Cited chunks are never overwritten, and
stale uncited chunks are removed only after a successful `--all` run. The
database-generated `search_vector` is recalculated when chunk content is
inserted or updated.

Chunk metadata records the filing ticker, fiscal year, form, filing date,
accession number, source URL, Docling item metadata, page references when
available, and embedding configuration. Source offsets are matched directly
or through normalized text. The latest GOOGL dry run could not map any of its
53 chunks; those offsets remain null. Do not rely on offsets for citation
navigation until a reliable source map is added and the dry-run coverage is
verified.
