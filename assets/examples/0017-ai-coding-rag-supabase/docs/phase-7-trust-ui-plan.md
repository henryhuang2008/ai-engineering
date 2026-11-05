# Phase 7 — Trust UI implementation plan

## Goal

Let analysts inspect the exact persisted evidence for each citation, identify its
filing and location, and understand what to do when loading or answering fails.
This phase is a frontend change; the Phase 6 citation payload already includes
the filing metadata, passage text, optional exact quote, and source URL.

## Current state

- Conversation history and live streams both deliver typed `ChatCitation` data.
- The chat renders citations as expandable text blocks rather than as
  individually actionable citation chips.
- A conversation can be opened in an external source URL, but there is no
  dedicated selected-passage view.
- Thread loading has a generic error state; chat request failures display the
  underlying error without identifying authentication, retrieval, grounding,
  provider, or network issues.
- The frontend has no test runner by project convention. Validate with the
  production TypeScript/Vite build and review the citation-to-passage data flow.

## Scope and implementation sequence

1. **Plan and contract**
   - Reuse the existing `ChatCitation` shape; do not add a backend endpoint or
     duplicate source state.
   - Render each citation as a keyboard-accessible chip labeled with company,
     filing, filing date, and page or section when known.
2. **Evidence panel**
   - Selecting a chip opens a source panel for that exact citation payload.
   - Show the exact quote when supplied, otherwise the persisted chunk passage;
     show source metadata and an external filing link.
   - Provide a close control and responsive layout for narrow screens.
3. **Request and conversation states**
   - Retain an explicit empty state and accessible loading/streaming indicators.
   - Distinguish expired/missing authentication, unavailable retrieval,
     grounding rejection, provider failure, and network failure.
   - Give actionable retry, sign-in, or dismiss controls without hiding the
     original error.
4. **Documentation and verification**
   - Record the implemented behavior and any live-verification limitation.
   - Run the frontend production build, lint, and `git diff --check`.
   - Confirm from the component data flow that a selected chip displays its own
     citation passage and source URL. A live authenticated/provider smoke test
     remains a separate environment-dependent check.

## Acceptance criteria

- Each citation is an accessible button with company, form, filing date, and
  only known page/section location.
- Activating a citation opens the panel with that citation's persisted passage
  (or its supplied exact quote), filing metadata, and source URL.
- The source panel can be closed and works at mobile and desktop breakpoints.
- Empty, loading, streaming, auth, retrieval, grounding, provider, and network
  states are visible and actionable.
- Production build and formatting/whitespace checks pass. No dependency or
  backend/API changes are needed.

## Out of scope

- Changing citation generation, passage retrieval, persistence, or source
  offsets.
- Claim-to-passage semantic entailment guarantees.
- A live provider/Supabase check or representative answer-quality evaluation;
  those require configured services and corpus coverage.

## Implementation status

- [x] Add citation chips and a responsive source-passage panel.
- [x] Add explicit loading, streaming, authentication, retrieval, grounding,
  provider, and network error states.
- [x] Reuse persisted citation payloads so each chip opens its own passage.
- [x] Show an early transient progress message and surface stream errors/timeouts.
- [ ] Complete an authenticated browser smoke test with persisted citations and verify the external filing links.

## Validation

- `pnpm run build` passes, including the TypeScript project build.
- `git diff --check` passes.
- ESLint is blocked by the existing `typescript-eslint` incompatibility with
  the installed TypeScript 7.0.2.
- The authenticated browser smoke test remains pending; it requires a live
  signed-in session and persisted citations.
