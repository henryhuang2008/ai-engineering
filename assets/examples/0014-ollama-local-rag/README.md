# 0014 — A fully local RAG agent with Ollama + LlamaIndex

A small RAG pipeline that runs entirely on your machine:

```
data/reviews.csv
      │  ingest.py
      ▼
LlamaIndex Documents ── OllamaEmbedding(nomic-embed-text) ──▶ Chroma
                                                               │
question ── VectorStoreIndex.as_query_engine(k=4) ─────────────┘
      │
      ▼
Ollama(qwen3:4b-instruct) ──▶ answer + source_nodes
```

No API key, no cloud call, no per-token bill. The tradeoff is model quality and speed: a 4B model is useful for grounded Q&A over a small corpus, not a replacement for a frontier API.

## 1. Install Ollama

**Windows**

```powershell
winget install Ollama.Ollama
# or download the installer: https://ollama.com/download
```

The desktop app starts the server for you. If you use the CLI only, run `ollama serve` in a terminal and leave it open. Verify:

```powershell
ollama --version
ollama list
```

**macOS**

Download the app from https://ollama.com/download (or `brew install ollama`). The app runs the server; `ollama serve` works from a terminal too.

**Linux**

```bash
curl -fsSL https://ollama.com/install.sh | sh
sudo systemctl status ollama     # the installer registers a service
```

The API listens on `http://localhost:11434`. Do not expose that port: Ollama has no authentication.

## 2. Pull a chat model and an embedding model

The original lab used `llama3.2` (3B, 2024) and `mxbai-embed-large`. A better small default in 2026 is Qwen3 4B Instruct: non-thinking, 2.5 GB, 256K context, and fast enough for RAG.

```powershell
ollama pull qwen3:4b-instruct   # ~2.5 GB, non-thinking instruct, 256K context
ollama pull nomic-embed-text    # ~274 MB, 768 dims
```

| chat model | size | use it when |
|---|---|---|
| **`qwen3:4b-instruct`** | ~2.5 GB | default here: non-thinking, fast, 256K context, fits an 8 GB machine |
| `qwen3.5:4b` | ~3.3-4.0 GB | newer Qwen, vision + tools; the upgrade if you have 16 GB |
| `qwen3.5:2b` | ~2.7-3.1 GB | 8 GB laptop, a little weaker than 4B |
| `qwen3.5:0.8b` | ~1.2-1.3 GB | smoke test or very low RAM; shallow answers |
| `qwen3:4b` | ~2.5 GB | Qwen3 4B with thinking mode; slower for RAG |
| `phi4-mini` | ~2.5 GB | reasoning/maths over chat; text only |
| `llama3.2:3b` | ~2.0 GB | the original lab's model; fast, older |

`qwen3:4b-instruct` is Qwen3-4B-Instruct-2507: the non-thinking variant, so it answers directly instead of emitting a reasoning trace first. That is what you want for retrieval-augmented answers.

Embedding alternatives:

| embedding model | size | dims | note |
|---|---|---|---|
| **`nomic-embed-text`** | ~274 MB | 768 | default; CPU-friendly, 8K native context |
| `qwen3-embedding:0.6b` | ~639 MB | 1024 | newer, 32K context, multilingual |
| `embeddinggemma` | ~622 MB | 768 | Google 300M; needs task prefixes |
| `mxbai-embed-large` | ~670 MB | 1024 | the original; 512-token chunks |
| `bge-m3` | ~1.2 GB | 1024 | multilingual, no prefix required |

`ollama list` shows what is installed; `ollama ps` shows what is loaded; `ollama rm <model>` frees disk.

## 3. Run the lab

```powershell
cd assets\examples\0014-ollama-local-rag
uv sync

Copy-Item .env.example .env      # first time only

uv run python ingest.py
uv run python ask.py "Is the gluten-free pizza good?"
uv run python ask.py             # interactive
```

`ingest.py` embeds the 20 reviews once and persists Chroma under `chroma_db/`. `ask.py` builds a LlamaIndex query engine over that index, retrieves four reviews, and calls the local chat model. Both scripts preflight Ollama and print the exact `ollama pull` command if a model is missing.

## What you should see

```
$ uv run python ingest.py
Generating embeddings: 100%|...| 20/20
read 20 rows from reviews.csv
embedded 20 documents with nomic-embed-text
stored in ...\chroma_db
```

```
$ uv run python ask.py "Is the gluten-free pizza good?"
querying 4 local chunks with qwen3:4b-instruct ...

Yes, the gluten-free pizza is good. It is described as the best gluten-free
option locally, with a base that does not fall apart and is cooked on a
separate tray.

sources:
  [Great gluten-free option] rating=5 2026-09-14
  [Staff know the menu] rating=5 2026-10-14
  [Great lunch special] rating=5 2026-10-23
  [Best crust in town] rating=5 2026-09-02
```

The source list above is from a real retrieval run with `nomic-embed-text`; the generated wording will vary by model. The sources are the check: every claim should be supported by one of the four retrieved reviews.

**Expected speed:** the first call loads the model into RAM/VRAM. A 4B model on a modern CPU produces roughly 15-30 tokens/second; a GPU is faster. Embedding 20 short reviews takes a few seconds.

## Change the models

Edit `.env`:

```
OLLAMA_MODEL=qwen3.5:4b
OLLAMA_EMBED_MODEL=qwen3-embedding:0.6b
```

**Changing the embedding model requires rebuilding the store**: vectors from different models do not share a space. Delete `chroma_db/` and rerun `ingest.py`. The chat model can change freely.

## The LlamaIndex pieces

- `OllamaEmbedding` is set as `Settings.embed_model`; `Ollama` as `Settings.llm`. These are process-wide, so configure them once at startup.
- `ChromaVectorStore(chroma_collection=...)` wraps the same persisted Chroma collection that `ingest.py` writes.
- `VectorStoreIndex.from_documents(...)` embeds and stores; `VectorStoreIndex.from_vector_store(...)` reads it back.
- `index.as_query_engine(similarity_top_k=4)` builds the retrieve-then-synthesize pipeline. `response.source_nodes` is the evidence list.

## Files

| file | role |
|---|---|
| `common.py` | config, Ollama preflight, LlamaIndex `Settings` wiring |
| `ingest.py` | CSV → `Document`s → embeddings → Chroma |
| `ask.py` | `VectorStoreIndex` → query engine → answer + sources |
| `data/reviews.csv` | 20 synthetic Nimbus Pizza reviews |
| `.env.example` | model names and base URL |
| `pyproject.toml` | uv project: llama-index-core, Ollama + Chroma integrations, pandas |

## If it fails

- **`Ollama is not reachable at http://localhost:11434`** — install it, then run `ollama serve` (or open the desktop app). The script prints the install commands.
- **`these models are missing`** — run the printed `ollama pull ...` lines. Tags matter: `qwen3:4b-instruct` is not `qwen3:latest`.
- **Very slow first answer** — the model is loading. Watch `ollama ps`; keep it warm by asking two questions in one session.
- **`llama-server process has terminated ... out-of-memory ... failed to allocate buffer for kv cache`** — the client asked for the model's full 262K context. Keep `OLLAMA_NUM_CTX=4096` (the default in `common.py`) or lower it to 2048, and close other model-heavy apps. The model's advertised maximum is not the working context you should request.
- **Out of memory** — use `qwen3.5:2b` or `qwen3.5:0.8b`, lower `OLLAMA_NUM_CTX`, and close other model-heavy apps.
- **`the vector store is empty`** — run `uv run python ingest.py`.
- **`Collection expecting embedding with dimension of X, got Y`** — the collection was built with a different embedding model. Delete `chroma_db/` and re-ingest.
- **Changed the embedding model and answers got worse** — old and new vectors are not comparable; rebuild the store.
- **Port 11434 already in use** — another Ollama instance is serving; use it instead of starting a second one.
- **Privacy** — this pipeline sends nothing to a provider. The model files and the vector store are local.
