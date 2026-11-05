# Phase 3 — Stubbed chat backend plan

## Goal

Provide authenticated chat threads and history, then stream and persist a
deterministic stub response through FastAPI before retrieval or LLM generation
is implemented.

## Prerequisite

The initial Alembic migration must be reviewed and applied to the intended
Supabase project before live persistence can be tested. Until then, validate
the backend with mocked Supabase requests. Do not run the migration without
review and explicit approval.

## Implementation sequence

### 1. Add user-scoped chat persistence

- Add async Supabase access for requests, using the authenticated user's
  bearer token so Postgres RLS applies.
- Add `app/database/chats.py` to create and list threads and load ordered
  messages.
- Ensure the user's `users` row exists before creating a thread, because
  `chat_threads.user_id` references `users.id` while Supabase Auth does not
  automatically populate this application table.
- Keep user ownership derived from the verified auth dependency, never from
  client-supplied `user_id` values.

### 2. Add authenticated thread and history endpoints

Implement API operations to:

- Create a chat thread.
- List the authenticated user's threads.
- Load a thread and its ordered message history.

Validate request and response data with Pydantic models. Ensure every database
query is user-scoped and that attempts to access another user's thread do not
reveal its contents.

### 3. Add the stub streaming endpoint

Implement `POST /chat/stream` with the AI SDK UI-message request format
described in [architecture.md](./architecture.md). The route should:

- Require `get_current_user`.
- Validate the thread and incoming messages.
- Confirm that the thread belongs to the authenticated user.
- Stream a deterministic assistant response and citation metadata using the
  wire format expected by the frontend.
- Return clear errors for invalid input, unauthorized or missing threads, and
  upstream Supabase failures.

The stub response should not claim support from retrieved documents. Its
content and citation metadata are placeholders for validating the streaming
contract, not evidence-grounded answers.

### 4. Persist completed turns

- Persist the submitted user message and final assistant message only after
  the stub response has completed successfully.
- Do not leave a partial user/assistant turn if generation or streaming fails.
- Keep message ordering deterministic for history reloads.

### 5. Add focused tests

Use mocked Supabase boundaries; unit tests must not require a live database or
network. Cover:

- Creating and listing a user's threads.
- Loading ordered message history.
- Rejecting access to another user's thread.
- Invalid thread IDs and malformed message payloads.
- AI SDK stream event format and deterministic stub output.
- Successful persistence and no persistence after a failed stream.
- Authentication failures before protected work starts.

## Acceptance criteria

- Authenticated users can create and list only their own threads.
- A thread's history reloads with messages in the correct order.
- `POST /chat/stream` emits the expected AI SDK-compatible stream and stub
  citation metadata.
- A completed turn persists both user and assistant messages; failed turns do
  not persist partial messages.
- The fast backend test suite passes without a live Supabase project.
- After migration approval and application, a manual Supabase-backed check
  verifies create, send, stream, and history restoration.

## Out of scope

- Document ingestion, retrieval, embeddings, or LLM calls.
- Grounding or validation of real citations.
- Frontend conversation UI implementation; it is tracked separately in
  Phase 3 of [todo.md](./todo.md).
