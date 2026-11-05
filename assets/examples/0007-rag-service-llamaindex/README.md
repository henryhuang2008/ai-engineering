# 0007 (LlamaIndex variant) — the same RAG service, framework-managed

This is the lesson 7 service rebuilt with **LlamaIndex** instead of the hand-written
LanceDB + LangChain path:

```
docs/  (reused from ../0007-rag-service/docs)
   │ parse.py: Docling -> HybridChunker -> contextualized text
   ▼
TextNode[] ── QwenEmbedding(text-embedding-v4) ──▶ LanceDBVectorStore
                                                      │
question ── VectorStoreIndex.as_query_engine(k=6) ────┘
   │
   ▼
DeepSeek (deepseek-flash) ──▶ answer + source_nodes
```

The corpus is the same three NimbusDesk documents, so both examples answer the
same five questions. The difference is who owns the pipeline:

| piece | main lab | this variant |
|---|---|---|
| parse/chunk | Docling `HybridChunker` | same |
| embedding | explicit Qwen batching | `QwenEmbedding(BaseEmbedding)` adapter |
| store | hand-written LanceDB table + FTS | `LanceDBVectorStore` |
| retrieval | explicit dense + BM25 + RRF | LlamaIndex `as_query_engine(k=6)` (dense) |
| answer | `ChatDeepSeek` + Pydantic + citations | `DeepSeek` + query engine; sources printed |
| incremental hashes | yes | `--rebuild` only |

If you need the explicit hybrid RRF and numbered citation validation, keep the
main lab. This variant shows how much of the plumbing LlamaIndex owns and what
you give up when you hand it over.

## Run

```powershell
$env:DASHSCOPE_API_KEY = "sk-..."     # Qwen embeddings
$env:DEEPSEEK_API_KEY = "sk-..."      # DeepSeek generation

cd assets\examples\0007-rag-service-llamaindex
uv sync

uv run python ingest.py --preview     # parse + chunk only; no key
uv run python ingest.py               # embed + index
uv run python ask.py "How many seats does the Team plan include?"
uv run python ask.py --show "What does E-311 mean?"
```

If Docling cannot reach `huggingface.co`, set the mirror once:

```powershell
$env:HF_ENDPOINT = "https://hf-mirror.com"
```

The first preview takes roughly 30–100 s on CPU: it imports PyTorch and runs the
layout model. Later runs use the cached models.

## What you should see

```
$ uv run python ingest.py --preview
15 chunks from 3 documents in 103.6s
characters per chunk: min 102  median 327  max 990
```

```
$ uv run python ingest.py
Generating embeddings: 100%|...| 15/15
indexed 15 chunks from 3 documents in 48.1s
stored in ...\index\lancedb
```

```
$ uv run python ask.py "How many seats does the Team plan include?"
question: How many seats does the Team plan include?

answer: 25 seats.

sources:
  [1] 0.3546  nimbusdesk-plans.docx  NimbusDesk plans and limits
  [2] 0.3111  release-notes.md  NimbusDesk release notes > 2026-05-19
  ...
```

Unanswerable question:

```
$ uv run python ask.py "What is the SLA for the mobile app?"
answer: INSUFFICIENT_CONTEXT
...
insufficient_context: True
```

The source list is the evidence. Unlike the main lab, this variant does not force
a numbered `citations` array; the query engine returns text plus `source_nodes`,
and the prompt tells the model to say `INSUFFICIENT_CONTEXT` rather than guess.

## The LlamaIndex pieces

```python
Settings.embed_model = QwenEmbedding()          # custom BaseEmbedding adapter
Settings.llm = DeepSeek(model="deepseek-flash", temperature=0, is_chat_model=True)

vector_store = LanceDBVectorStore(uri="index/lancedb", table_name="chunks_llamaindex")
index = VectorStoreIndex.from_vector_store(vector_store)
engine = index.as_query_engine(similarity_top_k=6, text_qa_template=TEXT_QA)
response = engine.query(question)
```

- `QwenEmbedding` wraps `text-embedding-v4` and preserves the `query` vs `document`
  split from lesson 6.
- `TextNode` carries the chunk text and metadata (`source`, `headings`, `pages`,
  `doc_hash`).
- `LanceDBVectorStore` persists nodes and vectors; `StorageContext` binds it to
  the index.
- `response.source_nodes` is the retrieved evidence, with scores.

## Files

| file | role |
|---|---|
| `common.py` | paths (shared corpus), Qwen constants, key checks |
| `qwen.py` | Qwen embeddings + `QwenEmbedding(BaseEmbedding)` |
| `parse.py` | Docling + HybridChunker, identical to the main lab |
| `ingest.py` | chunks → `TextNode` → Qwen → LanceDB |
| `ask.py` | `VectorStoreIndex` → query engine → answer + sources |
| `pyproject.toml` | uv project: llama-index-core, DeepSeek + LanceDB integrations, Docling |

## If it fails

- **`DASHSCOPE_API_KEY is not set`** / **`DEEPSEEK_API_KEY is not set`** — the
  scripts print the exact PowerShell lines and exit 1.
- **Docling download timeout** — set `HF_ENDPOINT=https://hf-mirror.com` and
  retry; the models are cached after the first success.
- **`no index found`** — run `uv run python ingest.py`.
- **`Table chunks_llamaindex doesn't exist yet`** — the index is empty or was
  deleted; re-run ingest.
- **Stale index after changing the embedding model** — run `ingest.py --rebuild`;
  vectors from different models are not comparable.
- **A dimension error from LanceDB** — the table was built with another embedder;
  rebuild it.
