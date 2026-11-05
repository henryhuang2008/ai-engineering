# 0004 — Streaming chat: FastAPI + LangChain, Next.js prompt input

A two-service chat product: **Python owns every AI decision**, Next.js owns the shell.
One DeepSeek model handle, one SSE endpoint, one thin translator, one shadcn prompt input.

Two folders, one job each:

```
0004-streaming-chat\
  backend\      Python + FastAPI + LangChain  -> the model, the key, the SSE endpoint
  frontend\     Next.js + shadcn prompt input -> the screen; no key, no model call
```

| layer | role | file |
|---|---|---|
| FastAPI | validates the conversation, calls `ChatDeepSeek.astream()`, frames each delta as `data: {"delta": "..."}` | `backend/main.py` |
| bare client | proves the Python side streams before Next.js exists; prints TTFT | `backend/test-client.html` |
| Next.js route | protocol translator only — no key, no model call | `frontend/app/api/chat/route.ts` |
| Next.js page | `useChat` + shadcn `InputGroup` prompt field | `frontend/app/page.tsx` |

## Run

### 1. backend — Python service

```powershell
cd assets\examples\0004-streaming-chat\backend
uv sync                                   # .venv from pyproject.toml + uv.lock
$env:DEEPSEEK_API_KEY = "sk-..."          # this terminal only
uv run python evals.py                    # 69 offline checks; +3 live with a key
uv run uvicorn main:app --reload          # http://127.0.0.1:8000
```

Open <http://127.0.0.1:8000/> for the bare test client. With no key the server
refuses to start and prints the two key commands — no silent fallback.

### 2. frontend — Next.js shell

```powershell
cd assets\examples\0004-streaming-chat\frontend
npm install                               # first run, or after deleting node_modules
npm run dev                               # http://localhost:3000
```

`frontend\.env.local` already points at the backend:

```
PY_BACKEND=http://127.0.0.1:8000
```

No copying, no scaffolding: the app is committed as source. The tree that matters:

```
frontend\
  app\
    api\
      chat\
        route.ts        <- POST /api/chat  (the BFF)
    page.tsx            <- the chat UI
    globals.css         <- theme + the font line
    layout.tsx          <- html shell, metadata title
  components\ui\input-group.tsx
  lib\utils.ts
  .env.local            <- PY_BACKEND=http://127.0.0.1:8000
  package.json
```

The page posts to `/api/chat`, the route translates to `{role, content}` and calls
FastAPI, and the answer streams back token by token.

<details>
<summary>How this frontend was scaffolded (only if you rebuild it yourself)</summary>

```powershell
npx --yes create-next-app@latest frontend --ts --tailwind --eslint --app --no-src-dir --import-alias "@/*" --turbopack --use-npm
cd frontend
npx --yes shadcn@latest init -d
npx --yes shadcn@latest add input-group -y
npm install ai @ai-sdk/react lucide-react
```

One line in the generated `app\globals.css` must be fixed or the whole page renders in
Times New Roman: the template says `--font-sans: var(--font-sans);` (it references
itself, so the value is empty). Change it to:

```css
--font-sans: var(--font-geist-sans);
```

The committed app already has that line, plus `app\page.tsx` and
`app\api\chat\route.ts` written by hand.
</details>

Verified end to end with Next.js 16.4, `ai` 7 and `@ai-sdk/react` 4: a production
`next build` type-checks clean, `POST /api/chat` relays `text-start` → `text-delta`… →
`text-end`, and against a live `ChatDeepSeek` backend the page streams real
`deepseek-flash` tokens. Newer/older majors may rename props; the seam stays the same.

The prompt field is the shadcn [Input Group](https://ui.shadcn.com/docs/components/input-group)
composition from the [Prompt Input](https://ui.shadcn.com/docs/ai-elements/base/prompt-input)
docs: textarea, Enter to send, Shift+Enter for a newline, and a button that turns into
Stop while streaming. Attachments and the model selector are extra `shadcn add` steps,
not required here.

## 404, 405, 502 — which layer broke

The page prints whatever came back. Three different failures, three different fixes:

| what you see | what it means | fix |
|---|---|---|
| a Next.js **404** HTML page ("This page could not be found") | no route handler at `/api/chat` — the file is in the wrong folder or misnamed | put it at `frontend\app\api\chat\route.ts` (or `src\app\api\chat\route.ts` if your app uses `src\`), then restart `npm run dev` |
| **502** with a plain-text body naming `PY_BACKEND` | the route is fine, Python isn't listening | start `uv run uvicorn main:app --reload` in `backend\` |
| a sentence from DeepSeek (e.g. `401 … invalid api key`) | both services are up; the model call failed | read the uvicorn terminal, fix `DEEPSEEK_API_KEY` |

Check the route without opening the browser:

```powershell
curl.exe -i http://localhost:3000/api/chat
# 405 Method Not Allowed -> the route exists (it only exports POST)   ✅
# 404 Not Found          -> the file is not at app\api\chat\route.ts  ❌
```

That asymmetry is your fastest diagnostic: Next.js answers `405` for a known route with
an unsupported method, and `404` when the segment doesn't exist at all. Creating
`app\api\chat\` while `npm run dev` is running usually works, but if the 404 persists,
restart the dev server — the route tree is read at boot in some versions.

## Wire format

Every delta is its own SSE event with a JSON body:

```
data: {"delta": "Stream"}

data: {"delta": "ing works"}

data: {"done": true}
```

JSON on purpose: a delta can contain a newline or a quote, and a raw `data: <text>`
frame would split one token into two events. Errors travel the same way
(`{"error": "..."}`) so the UI can show what broke instead of hanging.

## What the self-tests cover

Offline (69 checks): the pydantic request contract (roles restricted to
`system|user|assistant`, empty content and empty history rejected), the
message adapter to LangChain objects, SSE framing (blank-line termination, newline
and unicode safety, JSON round trip, done/error frames), the chunk-to-text reader
(string and block content), the model wiring (`ChatDeepSeek`, `deepseek-flash`,
`api.deepseek.com`, thinking disabled), environment overrides, the missing-key
message (startup refusal + CLI exit 1), the stack guard (no OpenAI SDK, no
`gpt-4o`, LangChain + pydantic + FastAPI present, page uses `InputGroupTextarea` and
turns a 404 HTML body into a hint, route parses SSE, forwards the abort signal, answers
failures as plain text, and the README documents the 405 check), and the uv project.

With a key, three more checks run: a live `astream()` must yield at least one
delta, the deltas must join into text, and the stream must actually be chunked.

## DeepSeek notes

- `deepseek-flash` streams tool calls, structured output, and plain text; the same
  loop works on other LangChain providers.
- The lab disables thinking (`extra_body={"thinking": {"type": "disabled"}}`).
  With thinking on, DeepSeek streams `reasoning_content` before the answer — fine
  for a reasoning UI, but it muddies "time to first *answer* token".
- `X-Accel-Buffering: no` is set on the response; nginx and friends buffer SSE by
  default, which turns a stream into one big blob at the end.

## Files

| file | role |
|---|---|
| `backend/main.py` | FastAPI app: pydantic contract, `ChatDeepSeek` wiring, `astream()` → SSE |
| `backend/test-client.html` | bare-browser test client served at `/` — first-token timing, no build step |
| `backend/evals.py` | 69 offline checks + a conditional live stream |
| `backend/pyproject.toml` | dependencies and Python floor — the single source of truth |
| `backend/uv.lock` | the pinned dependency graph `uv sync` installs |
| `frontend/app/api/chat/route.ts` | BFF translator: AI SDK UI stream ⇄ raw SSE |
| `frontend/app/page.tsx` | the whole UI: `useChat` + shadcn prompt input |
| `frontend/.env.local` | `PY_BACKEND=http://127.0.0.1:8000` |
| `index.html` | this page, generated for the course — not needed to run the lab |

Generated, safe to delete and recreate:

- `backend\.venv\` — `uv sync` (or any `uv run`) rebuilds it.
- `frontend\node_modules\` — `npm install`.
- `frontend\.next\` — `npm run dev` / `npm run build`.

The bare client is `backend/test-client.html`, not `chat.html`: the name says what the
file is (a test client, not the product), and FastAPI serves it at the root, so the
URL students open is still just `http://127.0.0.1:8000/`.

The UI shows three different states while it works, so a slow first token never
looks like a frozen page: a **spinner in the header pill** for the whole request,
**three bouncing dots** in the assistant bubble before the first delta arrives,
and a **blinking caret** after the first delta until `text-end`.

Versions pinned by `uv.lock`: `langchain 1.4.8`, `langchain-core 1.7.4`,
`langchain-deepseek 1.1.1`, `fastapi 0.162.0`, `uvicorn 0.54.0`, `pydantic 2.14.2`
(Python 3.12).

Lesson: [lessons/0004-streaming-chat.html](../../../lessons/0004-streaming-chat.html)
