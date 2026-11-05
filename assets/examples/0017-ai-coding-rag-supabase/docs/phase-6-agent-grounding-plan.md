# Phase 6 — LLM agent and grounding implementation plan

## Implementation status

The backend agent, three bounded retrieval tools, claim-level output contract,
referential grounding validator, chat orchestration, AI SDK-compatible SSE
serializer, and authenticated atomic turn persistence are implemented. The
new migration must be applied with `uv run alembic upgrade head` before chat
can save turns. Configure `DEEPSEEK_API_KEY` in `backend/.env`; startup fails
explicitly when it is missing.

The fast backend suite covers the agent tool allowlist, no-evidence refusal,
citation membership, history trust boundary, RPC payload, and stream ordering.
No live DeepSeek, Qwen, or Supabase call was run. Client-brief answer-quality
evaluation remains open because the confirmed corpus coverage is still too
limited to answer most of its ten questions.

## Goal

Replace the Phase 3 demo response with an authenticated, persisted chat turn
that answers only from retrieved filing passages. Every factual claim must
reference one or more retrieved passages; unsupported questions must receive a
clear evidence-limited response instead of a guessed answer.

Phase 6 wires the Phase 5 retriever into the existing chat stream. It does not
implement citation UI polish, broaden corpus ingestion, or claim that a
structural citation check proves a passage logically entails a claim.

## Current state and constraints

- `POST /chat/stream` currently returns a deterministic demo answer and a
  placeholder citation. It saves the user/assistant text pair only after the
  stub stream completes.
- `ChatStreamRequest` receives UI messages from the browser. Treat those
  messages as untrusted input; authorize the thread and read prior conversation
  context from server-side history rather than trusting client-supplied
  assistant text.
- The existing `ChatRepository` scopes its Supabase REST client to the
  authenticated user's bearer token. Thread ownership is checked before work.
- `chat_messages` and `message_citations` already have SQLAlchemy models,
  foreign keys, and user-scoped RLS policies. `message_citations` stores the
  assistant message ID, chunk ID, citation index, and optional quote.
- Phase 5 exposes a typed `HybridRetriever` with `search_filings`,
  `read_chunk`, and `read_surrounding_chunks`. Its construction needs
  `DATABASE_URL`, the configured Qwen endpoint and key, and a 1,536-dimension
  embedding model matching the ingested vectors.
- `Settings` currently has Qwen configuration but does not yet expose the
  DeepSeek key, base URL, or model. The checked-in `.env.example` documents
  these values; the settings module must become the app-code source of truth.
- The client brief is present at [client-brief.md](./client-brief.md) and
  defines ten sample questions. The currently confirmed corpus coverage is
  GOOGL fiscal year 2025 only, so most multi-company and multi-year questions
  cannot yet pass an evidence-coverage test. Do not fabricate answers or mark
  corpus coverage complete.
- Filing chunks may have null source offsets. Cite available section and
  `page_references` from chunk metadata when present; never infer or label a
  page number when no page reference exists.
- Keep the chat route, PydanticAI, retriever, and persistence dependencies
  injectable so unit tests can run without DeepSeek, Qwen, Supabase, or Postgres.

## Product and trust contract

1. Authenticate and authorize the thread before retrieval or model use.
2. Use server-owned chat history, bounded to a documented recent-turn/token
   limit; do not treat browser-sent prior assistant messages as evidence.
3. Give the model access only to the Phase 5 search and passage-reading
   operations. It must not issue SQL, access arbitrary URLs, or call tools
   outside the corpus.
4. Require typed output made of individually attributed factual claims. Each
   claim must reference one or more retrieved chunk IDs. A refusal is a valid
   answer when retrieval does not provide enough relevant support.
5. Validate every referenced chunk against the passages made available during
   that run. If a quote is returned, require it to be an exact substring of its
   cited passage. Reject unknown IDs, empty citations on factual claims,
   malformed output, or invalid quotes; do not stream a partial unvalidated
   answer.
6. Store only completed, validated turns and their citations. Make message
   writes and citation writes atomic and use the authenticated user's existing
   Supabase/RLS context.
7. Stream the validated answer and structured citation data using the existing
   AI SDK UI message SSE protocol. Citation metadata may identify a source
   section or known page references; missing page locations remain unavailable.
8. State clearly that referential validation confirms citations point to
   retrieved passages, not that software can mathematically prove semantic
   entailment. Validate answer quality with adversarial and client-brief
   evaluation, including human review of claim-to-passage support.
9. Never provide trading recommendations, stock picks, or investment advice.

## Proposed module boundaries

```text
backend/app/
├── assistant/
│   ├── agent.py             # DeepSeek PydanticAI agent and bounded tools
│   ├── deps.py              # Typed run dependencies: retriever and turn context
│   ├── outputs.py           # GroundedAnswer, claim, citation, and source types
│   └── instructions.md      # Evidence, refusal, citation, and advice policy
├── grounding/
│   └── validator.py         # Citation membership and exact-quote validation
├── chat/
│   └── orchestrator.py      # Retrieve, run agent, validate, persist, stream
├── api/
│   └── chat.py              # Existing authenticated route and SSE adapter
└── database/
    └── chats.py             # User-scoped turn and citation persistence
```

Keep the PydanticAI agent independent of FastAPI globals. The route owns
request parsing and thread authorization; the orchestrator owns the turn
lifecycle; retrieval owns search; grounding owns the citation contract; the
repository owns durable writes.

## Implementation sequence

### 1. Configure and own long-lived clients

- Add typed `DEEPSEEK_API_KEY`, `DEEPSEEK_BASE_URL`, and `DEEPSEEK_MODEL`
  settings with secret handling, defaults consistent with `.env.example`, and
  explicit validation when constructing the agent.
- Add the required DeepSeek variables to setup documentation and the example
  environment file if the current names/defaults do not already match.
- Construct one retriever and one configured agent/model client in the FastAPI
  application lifespan (or an equivalent app-state provider); close async
  clients and the SQLAlchemy engine at shutdown.
- Fail clearly at startup if mandatory Phase 6 provider or database settings
  are missing. Do not read environment variables directly in route or agent
  code.
- Keep model and retriever factories injectable for tests. Do not create a new
  dependency unless the existing PydanticAI/OpenAI clients cannot meet the
  typed-output and lifecycle requirements.

### 2. Define typed agent dependencies and answer output

- Define `DocumentAgentDeps` with the authenticated user ID, authorized thread
  ID, retriever interface, and bounded server-side conversation context. Do not
  put service secrets, request objects, or a Supabase admin client in agent
  dependencies.
- Define a structured output such as `GroundedAnswer` containing a list of
  `GroundedClaim` values and an explicit evidence-insufficient/refusal state.
  Each factual claim carries the IDs of one or more citations. Citation source
  fields include chunk ID, short exact quote where available, and metadata
  needed by the stream: company, filing type/date, fiscal year, accession,
  source URL, section, and only known page references.
- Render the user-facing answer from validated claims and their citation
  markers rather than accepting a separate free-form paragraph that could
  contain uncited claims.
- Enforce output-size and claim/citation-count bounds. Avoid unbounded history,
  result sets, or model-produced quote lengths.

### 3. Add the PydanticAI agent and bounded tools

- Configure the installed PydanticAI API for the DeepSeek model through
  explicit settings and dependency injection.
- Register only `search_filings`, `read_chunk`, and
  `read_surrounding_chunks`. Tool arguments use typed filters and bounded
  query/window limits; tools return the Phase 5 typed passage models.
- Ensure every citation points to a passage returned in this run's retrieval
  context or fetched through an allowed read tool. Maintain a per-run registry
  of passage IDs and metadata for grounding validation.
- Do not add general-purpose SQL, web search, unrestricted URL fetching,
  arbitrary code execution, or a reranker in this phase.
- Keep tool/retrieval errors explicit. Do not convert provider/database
  failures into the evidence-insufficient response; refusal is for insufficient
  corpus evidence, not broken infrastructure.

### 4. Implement instructions and grounding enforcement

- Add `assistant/instructions.md` covering: answer only from provided filings;
  cite each factual claim; distinguish filing statements from synthesis;
  preserve dates, units, and company/fiscal-year scope; refuse unsupported
  comparisons; explain when only some requested years/companies are available;
  and provide no trading or investment advice.
- Add a deterministic validator that checks:
  - the output is a valid typed answer and within configured bounds;
  - every factual claim has at least one citation;
  - every citation chunk ID is in the current run's retrieved/read passage
    registry;
  - any supplied quote exactly occurs in its cited passage;
  - cited company, filing, year, page, and section metadata come from the
    hydrated passage, not model-invented fields;
  - refusal output does not contain unsupported factual claims.
- Fail closed on validator errors: do not persist or stream the generated
  answer. Surface a safe error to the client and log enough context for
  diagnosis without logging secrets or unnecessary filing text.
- Do not describe this deterministic validation as a proof of entailment.
  Evaluate semantic support through curated examples and human review.

### 5. Orchestrate a safe chat turn

- Keep the current authenticated route and require `repository.get_thread()`
  before retrieval or DeepSeek calls.
- Build model context from bounded, server-loaded history and the current user
  question. Ignore client-provided prior assistant text as model authority.
- Run the turn in this order:
  `authorize → load history → retrieve/use tools → produce typed answer →
  validate → persist atomically → stream validated answer`.
- Validate the complete answer before opening the successful SSE stream. This
  intentionally means first-token latency includes generation and persistence:
  streaming model tokens before grounding validation would expose unsupported
  claims that cannot be retracted. Once validated and durable, emit text in
  bounded deltas.
- For insufficient retrieval, stream an explicit refusal with no fabricated
  citations and persist it as a normal completed assistant turn if validation
  passes.
- Preserve request cancellation behavior; do not continue expensive model or
  retrieval work after a disconnected request where cancellation is observable.

### 6. Persist messages and citations consistently

- Extend `ChatRepository` to save a validated assistant turn with ordered
  citations and return the persisted assistant message ID.
- Keep writes scoped to the existing authenticated user JWT and RLS policies.
  Do not use the service-role key just to simplify writes.
- Make the user message, assistant message, and citation rows atomic. Prefer a
  narrowly scoped `SECURITY INVOKER` Postgres RPC and Alembic migration called
  through the authenticated Supabase REST client, or document/test an
  equivalent transaction that preserves the same RLS guarantees. Do not rely
  on separate REST inserts that can leave a completed answer without citations.
- Store `message_citations.chunk_id`, stable citation index, and exact quote
  when present. Source-document fields can be hydrated by joining through the
  existing chunk/document tables; do not duplicate untrusted metadata.
- Update thread timestamps and history response behavior as needed so persisted
  citation metadata can be reloaded and associated with the assistant message.
- Add migration/RLS tests if a database function or policy change is required.

### 7. Emit the AI SDK-compatible stream

- Replace the stub generator with a focused serializer for the installed AI SDK
  UI message stream version. Keep the existing headers and SSE framing.
- Emit start, text-start, text-delta, structured citation data parts,
  text-end, finish, and `[DONE]` in the exact protocol order. Preserve stable
  citation IDs/indices so history and the UI can identify sources.
- Align the structured citation payload with frontend types. It should carry
  source identity plus section/known page references and no fabricated page.
  Phase 7 owns the polished citation chips and source panel; Phase 6 only needs
  a usable data contract and compatible rendering.
- Handle failures before streaming through normal HTTP errors where possible.
  Once a stream has started, emit a protocol error and never emit a successful
  finish for a failed persistence/stream operation.
- Keep the existing stub behavior out of production paths; tests should assert
  no demo citation or placeholder answer remains.

### 8. Test, evaluate, and document

- Keep default tests credential-, network-, and database-free using fakes at
  agent, repository, and retriever boundaries. Mark live DeepSeek/Qwen/Postgres
  checks as integration tests.
- Unit-test claim/citation validation, unknown chunk IDs, exact/invalid quotes,
  empty citations, refusal, metadata provenance, output bounds, and
  persistence ordering/atomicity behavior.
- Unit-test that only the three allowed tools are registered, filters and
  neighbor limits remain bounded, and agent/tool/provider errors are not
  mistaken for a safe refusal.
- Test unauthorized/missing thread cases do not trigger retriever or model
  calls; test untrusted client assistant messages are not used as history.
- Test AI SDK stream event ordering, citation payload shape, successful
  persistence before stream completion, and that failures never produce a
  success finish or `[DONE]`.
- Use the ten analyst questions in [client-brief.md](./client-brief.md) as the
  evaluation set. Record expected company/year requirements, retrieve
  evidence, inspect cited claims/passages, and include question 10 as an
  evidence-limited refusal test.
- Since the currently confirmed corpus is GOOGL 2025 only, classify
  multi-company/year questions as corpus-coverage blocked until ingestion
  supplies those filings; do not grade unavailable evidence as an agent
  success. The AI must explicitly report the coverage gap.
- Document local setup, required DeepSeek settings, how to run tests, and how
  to run opt-in provider/database integration checks.

## Acceptance criteria

- Auth and thread ownership checks occur before any retrieval or model calls.
- The agent receives only explicit typed dependencies and can call only the
  three bounded retrieval tools.
- Every user-facing factual claim has citation references that resolve to
  passages from the current run; supplied quotes are exact; unknown or
  malformed references fail closed.
- The validator derives all citation metadata from hydrated source records and
  never invents page numbers when source page references are missing.
- Insufficient evidence is distinguished from upstream failures, and the
  client-brief unsupported-inference case refuses clearly.
- The completed turn and citations are durably persisted atomically under the
  authenticated user's RLS context before a successful stream is emitted.
- The stream follows the installed AI SDK UI message protocol and restores
  persisted citation metadata on history reads.
- Fast backend tests remain free of live provider/database requirements;
  targeted checks and the fast suite pass.
- The ten-question evaluation reports model grounding quality separately from
  missing corpus coverage. Do not claim all questions are supported until the
  required years and companies are actually ingested and audited.

## Not included in Phase 6

- Citation chip/source-panel polish and full client-side evidence navigation
  (Phase 7).
- Ingesting the remaining companies/years or resolving unavailable source
  offsets (Phase 4 corpus work).
- General web search, unrestricted SQL, reranking, or unsupported external
  sources.
- Trading recommendations, stock picks, or investment advice.
- Production deployment and the five-analyst pilot (Phases 8–9).
