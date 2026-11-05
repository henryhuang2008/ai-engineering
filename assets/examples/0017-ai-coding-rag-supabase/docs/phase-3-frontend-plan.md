# Phase 3 — Stubbed chat frontend plan

## Goal

Build the authenticated conversation experience and connect it to FastAPI's
stubbed streaming endpoint, before retrieval or LLM generation is implemented.

## Current foundation

The frontend already has:

- Supabase email sign-in/sign-up and a protected route.
- A browser Supabase client and validated environment configuration.
- A shared API client that injects the current Supabase bearer token.
- Vite, React, TypeScript, Tailwind, React Router, and shadcn/ui.

Phase 3 should extend these pieces rather than add duplicate auth or HTTP
handling.

## Dependencies and prerequisites

- Coordinate request/response shapes and stream events with the Phase 3
  backend implementation before wiring the chat UI.
- The architecture proposes Vercel AI SDK React chat primitives. The SDK is
  not currently listed in `frontend/package.json`; check compatibility with
  the installed React and TypeScript versions, then add only the required
  package(s) using pnpm.
- The database migration is still pending. UI and mocked stream behavior can
  be developed before it is applied, but live history/persistence checks
  require the migration and working backend persistence.

## Implementation sequence

### 1. Confirm the API and streaming contract

Coordinate with the backend implementation to confirm:

- Thread creation, listing, and history endpoints.
- Request and response fields and error status codes.
- The AI SDK UI-message request shape.
- The stream event format, including how stub citation metadata is sent.

Keep the frontend transport pointed directly at FastAPI; do not introduce a
frontend server route.

### 2. Add typed thread API calls

Extend `src/lib/api.ts` with typed operations to:

- Create a conversation.
- List the signed-in user's conversations.
- Fetch ordered message history for a conversation.

Use the existing API client so bearer-token injection, timeouts, and typed
errors stay consistent.

### 3. Add conversation routes and layout

- Keep the existing login route and protected-route behavior.
- Add a conversation-list or home route.
- Add a route for an individual conversation, keyed by thread ID.
- Build a responsive conversation layout with a thread sidebar and active
  chat panel.
- Provide clear loading, empty, not-found, and API error states.

### 4. Connect chat state and streaming

- Initialize each chat from history returned by the backend.
- Use the AI SDK chat primitives with a transport targeting FastAPI's
  `/chat/stream`.
- Let the shared API/session behavior supply the Supabase bearer token.
- Render user and assistant messages, the input form, and a visible streaming
  indicator.
- Render stub citation metadata as placeholder metadata only; do not imply
  that the response is supported by retrieved documents.
- Prevent duplicate submissions while a request is streaming and surface
  stream/API errors to the user.

### 5. Verify the user flow

Manually check:

1. Sign in and open the conversation list.
2. Create a conversation and open its route.
3. Send a message and observe streamed assistant output.
4. Confirm citation metadata and error/loading states render correctly.
5. Refresh the page and confirm the conversation and prior messages restore.
6. Confirm unauthenticated users are redirected to login.

Until live backend persistence is available, use mocked responses or the
backend's local stub where possible and keep the live persistence step pending.

## Acceptance criteria

- Signed-in users can navigate between their conversations and open a specific
  thread.
- The active conversation loads and displays stored messages in order.
- Sending a message streams the backend's deterministic stub response.
- The UI displays streaming status, errors, empty states, and stub citation
  metadata clearly.
- Refreshing restores history once persistence is available.
- The frontend production build/type-check passes.
- Manual create, send, stream, reload, and history restoration are verified
  against the running backend after its endpoints and persistence are ready.

## Out of scope

- Frontend auth implementation, which is covered in Phase 2.
- Real retrieval, embeddings, LLM responses, citation grounding, or source
  document viewing.
- Replacing the FastAPI streaming endpoint with a frontend server route.

## Related documentation

- [Implementation checklist](./todo.md)
- [System architecture and streaming contract](./architecture.md)
- [Backend Phase 3 plan](./phase-3-backend-plan.md)
