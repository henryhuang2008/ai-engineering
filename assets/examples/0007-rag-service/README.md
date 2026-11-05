# 0007 — The RAG service: index once, answer every query

Lesson 6 drew the pipeline. This is the first real build of it: a corpus of three
documents, an offline lane that turns them into a LanceDB table, and an online lane
that answers questions from that table with citations.

**Two parts, two commands.**

| part | lanes | command | what it produces |
|---|---|---|---|
| offline | stages 1–4 | `uv run python ingest.py` | chunks, 1024-d vectors and a BM25 index in one LanceDB table |
| online | stages 5–8 | `uv run python ask.py "..."` | a grounded answer with validated citations |

There is no fake model and no cached answer. The embedder is **Qwen
`text-embedding-v4`**, the generator is **DeepSeek `deepseek-flash`**, and the store is
**LanceDB** because it ships BM25 and hybrid search on the same table as the vectors.

---

## Keys

Two vendors, because DeepSeek has no embeddings endpoint. Both are needed for a full
run; `--preview` needs neither.

```powershell
$env:DASHSCOPE_API_KEY = "sk-..."     # Qwen embeddings
$env:DEEPSEEK_API_KEY = "sk-..."      # DeepSeek generation
```

Persist them with `setx` and reopen the terminal. No key prints these commands and
exits 1.

- Qwen key: <https://bailian.console.alibabacloud.com/>
- DeepSeek key: <https://platform.deepseek.com/api_keys>

Keys are region-specific. If the embedding call returns 401, set the endpoint from
your DashScope console:

```powershell
$env:DASHSCOPE_BASE_URL = "https://<your-region-host>/api/v1"
```

## Run

```powershell
cd assets\examples\0007-rag-service
uv sync                                  # first run is large: Docling + PyTorch
uv run python ingest.py --preview        # parse + chunk, no API key, no index
uv run python ingest.py                  # embed and index (writes index/lancedb)
uv run python ask.py "How many seats does the Team plan include?"
```

`uv run python ask.py` with no question starts a prompt loop. `--show` prints the
retrieved evidence; `--k` changes how many chunks reach the model (default 6);
`--rerank` adds a cross-encoder, off by default so you can measure the difference.
`--ocr` turns OCR on for scanned PDFs (off by default; it roughly doubles parse time).

### First run downloads models

Docling downloads its layout models once (a few hundred MB) and caches them. If
`huggingface.co` is unreachable, use a mirror:

```powershell
$env:HF_ENDPOINT = "https://hf-mirror.com"
```

The lab prints this hint itself when the download fails.

---

## The corpus

`docs/` holds three formats on purpose, so the parse stage has real work to do:

| file | format | why it is here |
|---|---|---|
| `nimbusdesk-handbook.pdf` | PDF | headings, page anchors, a troubleshooting table |
| `nimbusdesk-plans.docx` | DOCX | a real table: seats, storage, API limits, SSO |
| `release-notes.md` | Markdown | dated entries; exact error codes and version facts |

NimbusDesk is fictional, but the facts are specific and checkable: 25 Team seats,
E-311, a 14-day refund window, SAML on Business only.

### What `--preview` prints

```
corpus: 3 documents in ...\0007-rag-service\docs
  load    Docling (first run imports PyTorch and downloads models; be patient)
  load    converter
  load    chunker (512-token budget)
  parse   nimbusdesk-handbook.pdf
          10 chunks
  parse   nimbusdesk-plans.docx
          1 chunks
  parse   release-notes.md
          4 chunks

15 chunks from 3 documents in 34.7s
characters per chunk: min 102  median 327  max 990
```

That first **35 seconds is Docling**, not a hang: importing PyTorch plus running the
layout model on CPU. Later stages reuse the loaded process, but every `uv run` is a
fresh process, so plan for it. If you press Ctrl+C, the script exits with
`interrupted` instead of a traceback.

Inspect this before spending tokens. If a chunk is a single heading, or a table is
split in half, fix the corpus or the chunk budget — not the prompt.

## What a good answer looks like

The ids, scores and wording vary between runs. The facts and the shape should not:

```
question: How many seats does the Team plan include?
retrieved 6 chunks (hybrid, RRF)
  [1] 0.0xxx  nimbusdesk-plans.docx  NimbusDesk plans and limits
  ...

answer: The Team plan includes 25 seats [1].
insufficient_context: False
citations:
  [1] nimbusdesk-plans.docx  chunk <id>
```

Five questions to try, with the fact to check:

| question | must contain | best source |
|---|---|---|
| How many seats does the Team plan include? | 25 | plans DOCX |
| What does E-311 mean? | mailbox storage quota | handbook §7 |
| How long do I have to request a refund? | 14 days | handbook §6 |
| Is SAML SSO available on Team? | no, Business only | plans DOCX / handbook §3 |
| What happens to deleted conversations? | recoverable 30 days, then purged | handbook §4 |

Ask something the corpus does **not** answer ("What is the SLA for the mobile app?")
and the `insufficient_context` flag is the thing to watch, not the prose.

---

## How it maps to lesson 6

| stage | in the code |
|---|---|
| 1 parse | `DocumentConverter().convert(path)` — Docling reads order, headings, tables |
| 2 chunk | `HybridChunker(max_tokens=512, merge_peers=True)`; `contextualize()` prepends the heading path |
| 3 embed + index | `text_type="document"`, 1024 dims, batches of 10; BM25 index on the same text |
| 4 store | one LanceDB table: id, text, source, headings, pages, doc_hash, vector |
| 5 prepare query | `text_type="query"`, same model and dimension |
| 6 retrieve | one hybrid query; dense + BM25 fused by `RRFReranker` |
| 7 rerank | `--rerank` swaps in `CrossEncoderReranker`; off by default |
| 8 generate | `ChatDeepSeek` + `with_structured_output(Answer, method="function_calling")`; citation numbers checked against the retrieved set |

Incremental indexing is real, not a TODO: each row stores the document's sha256, an
unchanged file is skipped, and a changed file has its rows deleted before the new ones
are added. Delete `index/` to start clean, or pass `--rebuild`.

## Files

| file | role |
|---|---|
| `common.py` | paths, model name, dimension, key checks |
| `qwen.py` | `text-embedding-v4` wrapper: batching and `query`/`document` |
| `store.py` | LanceDB schema, FTS index, hybrid query |
| `ingest.py` | offline lane + `--preview` |
| `ask.py` | online lane + citation validation |
| `docs/` | the corpus |
| `index/` | generated LanceDB database (not source) |

## Notes and limits

- **Batch limit:** Qwen accepts at most 10 texts per embedding request. `qwen.py`
  batches for you; do not remove it.
- **Dimension is fixed:** 1024 is written into the table schema. Changing the model or
  the dimension means rebuilding the index, not migrating it.
- **Chunk budget:** 512 tokens. The DOCX table lands as one 990-character chunk because
  it is short; longer tables are repeated per chunk with their header.
- **No vector index:** 15 rows do not need one. LanceDB brute-forces small tables; an
  IVF/HNSW index is a later lesson.
- **No rerank by default:** stage 7 is a flag, not a default, so the difference is
  measurable rather than assumed.
- **Cost:** embedding 15 chunks and a handful of queries is well under a cent at
  `text-embedding-v4` list price. Generation dominates the bill.
