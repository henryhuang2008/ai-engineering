# Rag with Supabase — implementation checklist

Work top to bottom. Each phase unlocks the next. Check items off as they are completed.

This file tracks phases, not detailed implementation plans. Before starting an item,
generate a focused execution plan for its files, acceptance checks, and blockers.

## Where to start: backend, frontend, or both?

**Start with foundation, then backend-led vertical slices.**

| Order                          | Why                                                                                                 |
| ------------------------------ | --------------------------------------------------------------------------------------------------- |
| 1. Supabase + sample data      | Everything persists here; the corpus is needed to test retrieval and citations.                     |
| 2. Backend schema + migrations | Auth, chat, ingestion, and retrieval all depend on the data model.                                  |
| 3. Thin vertical slices        | Wire authentication, then a stubbed stream, then real RAG one layer at a time.                      |
| 4. Frontend in parallel        | Scaffold the SPA early, but finish citation and chat UI after the backend returns grounded answers. |

The critical path is **data model → ingestion → retrieval → LLM → citations**. The
frontend is primarily an authenticated streaming chat shell and should not get far
ahead of working APIs.

## Phase 0 — Prerequisites and foundation

- [x] Install Python 3.12+, `uv`, Node.js 20+, and `pnpm`.
- [x] Create the Supabase project and collect backend/frontend credentials.
- [x] Create DeepSeek and Qwen/DashScope API credentials.
- [x] Set `USER_AGENT` in `data/download.py` and download the sample corpus.
- [x] Confirm `data/downloads/manifest.json` lists AAPL, MSFT, NVDA, AMZN, and GOOGL filings across 2021–2025.

## Phase 1 — Backend scaffold and database

Goal: a running FastAPI service with a migrated Supabase schema.

- [x] Initialize backend dependencies and the project layout.
- [x] Add `app/config.py` for typed, fail-fast settings.
- [x] Add `app/main.py` with FastAPI, CORS, and `GET /health`.
- [x] Add SQLAlchemy models in `app/database/models/` for `users`, `source_documents`, `document_chunks` (embedding + generated tsvector), `chat_threads`, `chat_messages`, and `message_citations`.
- [x] Add Alembic configuration and initial migration: pgvector extension, 1536-dimensional embeddings, generated tsvector, HNSW and GIN indexes, and RLS policies.
- [x] Document Alembic setup, SQL preview, and migration commands in `backend/alembic/README.md`.
- [x] Run `uv run alembic upgrade head` against Supabase after reviewing SQL and confirming approval; not yet run.
- [x] Add `app/database/supabase.py` with user-scoped and service-role clients.
- [x] Verify: uv run uvicorn app.main:app --reload → health check returns 200

## Phase 2 — Authentication

Goal: analysts sign in with email, and FastAPI rejects unauthenticated requests.

### Backend

- [x] Verify Supabase bearer tokens and expose `get_current_user`.
- [x] Return `401` for missing, invalid, or expired tokens before protected work begins.

### Frontend

- [x] Scaffold Vite, React, TypeScript, Tailwind, and shadcn/ui.
- [x] Add validated environment configuration.
- [x] Add the browser Supabase client.
- [x] Add the shared fetch/API client with automatic bearer-token injection.
- [x] Add email sign-in/sign-up and protected-route handling.
- [x] End-to-end verify that a real Supabase session reaches FastAPI with a valid token; mocked auth-provider coverage is in `backend/tests/test_auth.py`.

## Phase 3 — Stubbed chat vertical slice

Goal: the browser streams a stubbed assistant response from FastAPI before RAG exists.

### Backend

- [x] Add endpoints to create threads, list threads, and load message history.
- [x] Add `POST /chat/stream` using the AI SDK message format.
- [x] Stream a deterministic stub response and citation metadata.
- [x] Persist the user and assistant messages after a successful stream.
- [x] Reject access to another user's thread.

### Frontend

- [x] Add login, conversation-list, and conversation routes.
- [x] Connect the AI SDK chat transport to FastAPI with the Supabase bearer token.
- [x] Add the conversation sidebar, message list, input, and streaming indicator.
- [x] Verify create, send, stream, reload, and history restoration.

## Phase 4 — Ingestion

Goal: the SEC corpus is parsed, chunked, embedded with Qwen, and stored in Supabase.

- [x] Add a repeatable corpus-ingestion command.
- [x] Parse SEC HTML into normalized Markdown while preserving page and section metadata.
- [x] Upsert all 25 converted Markdown filings and filing metadata into `source_documents`.
- [x] Add standalone Docling chunking and embedding ingestion with fiscal-year-2025 scope, dry-run default, and one-chunk pilot gate.
- [x] Chunk filings within the Qwen embedding context limit and preserve Docling provenance in chunk metadata.
- [ ] Resolve source offsets: the current GOOGL dry run still reports 53/53 chunks unavailable after exact and normalized matching; do not rely on null offsets for citation navigation.
- [x] Implement storage of filing identity, source URL, available page references, section, chunk text, token count, and embedding metadata.
- [x] Implement Qwen `text-embedding-v4` vector generation/storage, verified with the one-chunk pilot; complete the remaining GOOGL chunks below.
- [x] Use the database-generated full-text search vector on chunk inserts and updates; verified with the one-chunk pilot.
- [x] Implement idempotent upsert/re-embedding for changed uncited chunks and safe cleanup of stale uncited chunks; cited rows are protected.
- [x] Add unit tests for manifest parsing, chunking, source-offset mapping, metadata extraction, embeddings, and citation-safe upserts.
- [x] Run and review the fiscal-year-2025 dry run for GOOGL: 53 hybrid chunks, 309,229 estimated input tokens, estimated cost CNY 0.1589.
- [x] Run the one-chunk GOOGL embedding/database pilot and verify the saved data in Supabase.
- [x] Ingest the fiscal-year-2025 GOOGL filing into document chunks and embeddings (remaining four companies are out of current scope).
- [x] Audit GOOGL chunk coverage and manually spot-check known passages and citation locations.

## Phase 5 — Retrieval

Goal: an analyst question returns ranked, relevant passages from the corpus.

See the [Phase 5 retrieval implementation plan](./phase-5-retrieval-plan.md).

- [x] Embed queries with Qwen `text-embedding-v4` using the configured async client and validate response dimensions and finite values.
- [x] Add bounded pgvector semantic search with ticker, year, and form filters.
- [x] Add Postgres full-text search with matching metadata filters.
- [x] Fuse semantic and lexical rankings with deterministic Reciprocal Rank Fusion.
- [x] Add bounded, same-filing neighboring-passage reads for verification and grounding.
- [x] Add credential-free unit tests for query assembly, embedding response validation, RRF, hydration order, and neighbor bounds.
- [ ] Verify that the client-brief questions retrieve evidence from the required companies and years.

## Phase 6 — LLM agent and grounding

Goal: DeepSeek produces answers whose factual claims are enforced against retrieved evidence.

See the [Phase 6 agent and grounding implementation plan](./phase-6-agent-grounding-plan.md).

- [x] Write agent instructions covering citations, insufficient evidence, and no investment advice.
- [x] Add a PydanticAI agent using the configured DeepSeek model.
- [x] Add typed dependencies, grounded-answer output, and citation/source models.
- [x] Expose only `search_filings`, `read_chunk`, and `read_surrounding_chunks` as agent tools.
- [x] Add the orchestrator for retrieve → agent → validate → persist → stream.
- [x] Validate claim citations against passages retrieved in the current run and fail closed on invalid references.
- [x] Stream validated text deltas and structured citation metadata in the AI SDK-compatible format.
- [x] Persist citations linked to the assistant message using one authenticated atomic RPC.
- [x] Add unit tests for citation validation, grounding enforcement, and message conversion.
- [ ] Verify representative client-brief questions, including the evidence-limited refusal case.

## Phase 7 — Trust UI

Goal: analysts can verify every cited claim in one click.

- See the [Phase 7 trust UI implementation plan](./phase-7-trust-ui-plan.md).

- [x] Add citation chips showing company, filing, date, and page or section.
- [x] Add a source-passage panel showing the exact cited excerpt.
- [x] Add empty, loading, streaming, authentication, retrieval, grounding, provider, and network error states.
- [ ] Run an authenticated browser smoke test confirming each citation opens its corresponding passage and filing source.

## Phase 8 — Pilot readiness

Goal: five senior analysts can use the product for a week and report at least three hours saved each.

- [ ] Add copy-paste local setup and corpus-ingestion instructions to the README.
- [ ] Smoke-test all 10 example questions from the client brief.
- [ ] Confirm that conversation and citation history persists across sessions.
- [ ] Confirm that the design supports roughly 40 analysts without single-user assumptions.
- [ ] Add structured backend logging for failed and slow turns.
- [ ] Measure time to first streamed token and full-response latency.
- [ ] Run the five-analyst pilot and capture time-saved and citation-trust feedback.

## Phase 9 — deployment

Goal: deploy a production-like frontend, backend, and migrated Supabase database.

- [ ] Configure the backend service, environment variables, and allowed origins.
- [ ] Configure the frontend service and build-time `VITE_*` variables.
- [ ] Enable production-appropriate Supabase email authentication and access restrictions.
- [ ] Run reviewed migrations against the production-like Supabase database.
- [ ] Run the audited ingestion job against the same corpus.
- [ ] Test the complete flow from deployed frontend to backend, Supabase, DeepSeek, and Qwen.
- [ ] Verify health checks, SPA refresh routing, logging, and rollback steps.

## Quick reference

| Document                                             | Purpose                                            |
| ---------------------------------------------------- | -------------------------------------------------- |
| [client-brief.md](client-brief.md)                   | Client requirements and example analyst questions  |
| [architecture.md](architecture.md)                   | Service design, data model, and streaming contract |
| [guides/supabase-setup.md](guides/supabase-setup.md) | Supabase Postgres and Auth                         |
| [guides/backend-setup.md](guides/backend-setup.md)   | FastAPI and Alembic setup                          |
| [guides/frontend-setup.md](guides/frontend-setup.md) | Vite and React setup                               |
