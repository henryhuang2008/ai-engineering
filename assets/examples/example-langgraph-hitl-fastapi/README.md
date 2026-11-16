# Human-in-the-Loop LangGraph Demo (FastAPI + React)

This project demonstrates a realistic Human-in-the-Loop (HITL) workflow using [LangGraph](https://github.com/langchain-ai/langgraph), embedded inside a Python FastAPI backend, with a React frontend. It is designed as a learning resource for developers interested in building interactive AI agent flows that pause for human input and then resume execution.

This copy runs on **DeepSeek** instead of OpenAI and installs with **uv** instead of pip. The graph code is otherwise the upstream demo.

## What is Human-in-the-Loop (HITL)?

HITL systems combine automated AI workflows with critical points where human feedback or decisions are required. In this demo, a LangGraph node can pause execution, request user input via the frontend, and then continue processing once the input is received.

## Architecture Overview

- **Backend:** Python FastAPI server running an embedded LangGraph agent.
- **Model:** `ChatDeepSeek` (`DEEPSEEK_MODEL`, default `deepseek-flash`), which supports tool calls.
- **Frontend:** React app for interacting with the agent (sending messages, providing input when requested, viewing results).
- **Communication:**
  - **Basic Version**: REST API endpoints with blocking request/response pattern.
  - **Advanced Version**: Server-Sent Events (SSE) for real-time streaming of LangGraph outputs.
- **State Management:** The backend manages the graph's state, including pausing and resuming at human input nodes.

## Three lessons in one backend

| Router | File | Shape |
|--------|------|-------|
| `/graph/start`, `/graph/resume` | `backend/app/lesson_01_blocking.py` | one blocking call per step; the response says `user_feedback` or `finished` |
| `/graph/stream/*` | `backend/app/lesson_02_streaming.py` | the client POSTs the decision, then GETs an SSE stream of tokens |
| `/mcp/start`, `/mcp/approve` | `backend/app/lesson_03_async_mcp.py` | an MCP tool call pauses inside `interrupt()` until it is approved or rejected |

Lesson 1's graph is `backend/app/graph.py`: `assistant_draft -> human_feedback -> assistant_finalize`, compiled with `interrupt_before=["human_feedback"]` and a `MemorySaver`. Lesson 3's graph is built by `backend/app/mcp_agent.py`; each MCP tool is wrapped so the tool body starts with `interrupt({"awaiting": ..., "args": ...})`.

## Setup

Everything below runs from `backend/`.

1. **Create `backend/.env`** (copy the template):

   ```powershell
   Copy-Item .env.example .env
   ```

   ```dotenv
   DEEPSEEK_API_KEY=sk-your-key
   DEEPSEEK_MODEL=deepseek-flash
   GITHUB_PERSONAL_ACCESS_TOKEN=ghp_your-token   # only for lesson 3
   ```

   `.env` is gitignored. `backend/app/config.py` loads it for the API, the notebooks and the MCP agent, so no shell exports are required.

2. **Install** (creates `.venv`, installs the backend and the notebook kernel):

   ```powershell
   uv sync
   ```

3. **Run the API**:

   ```powershell
   uv run uvicorn app.main:app --reload
   ```

   Interactive docs: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs).

Measured on this machine against the DeepSeek API (one run, seconds):

| Step | Time | Result |
|------|------|--------|
| `POST /graph/start` | 1.60 s | `user_feedback`, draft returned |
| `POST /graph/resume` (`feedback`) | 1.05 s | `user_feedback`, revised draft |
| `POST /graph/resume` (`approved`) | 0.77 s | `finished`, final text |
| `POST /graph/stream/create` | 0.004 s | `pending` (nothing ran yet) |
| `GET /graph/stream/{id}` | 1.65 s | 163 SSE `data:` lines, the last one `status: user_feedback` |
| `POST /mcp/start` | 2.29 s | `user_feedback`, `I want to call the tool ...` |
| `POST /mcp/approve` (`approved`) | 1.77 s | `finished`, answer built from the tool result |
| `POST /mcp/approve` (`rejected`) | 1.78 s | `finished`, model continues without the tool |

## Testing the Extended HITL Scenario (SSE/Streaming)

This section demonstrates how to test a full Human-in-the-Loop (HITL) scenario using the advanced streaming server endpoints. The following curl commands walk through starting a run, streaming the response, providing feedback, streaming again, approving the answer, and finalizing the run.

1) **Create a new run**
```bash
curl -X POST -H "Content-Type: application/json" -d '{"human_request": "Explain what is HITL"}' http://localhost:8000/graph/stream/create
```

2) **Stream the result**
```bash
curl --no-buffer http://localhost:8000/graph/stream/{thread_id}
```

3) **Provide feedback**
```bash
curl -X POST -H "Content-Type: application/json" -d '{
  "thread_id": "{thread_id}",
  "review_action": "feedback",
  "human_comment": "Make your answer only one sentence short."
}' http://localhost:8000/graph/stream/resume
```

4) **Stream the revised result**
```bash
curl --no-buffer http://localhost:8000/graph/stream/{thread_id}
```

5) **Approve the answer**
```bash
curl -X POST -H "Content-Type: application/json" -d '{
  "thread_id": "{thread_id}",
  "review_action": "approved"
}' http://localhost:8000/graph/stream/resume
```

6) **Stream the final result**
```bash
curl --no-buffer http://localhost:8000/graph/stream/{thread_id}
```

The POST stores the decision; the GET runs the graph and streams it. That split is what makes `curl --no-buffer` usable: the request that blocks on the model is the one you watch.

## Testing the async MCP tool calling (simple)

Lesson 3 starts GitHub's MCP server **in Docker** (`backend/config/mcp_servers.json`, `ghcr.io/github/github-mcp-server`). Docker Desktop must be running and `GITHUB_PERSONAL_ACCESS_TOKEN` must be set, or `/mcp/*` fails while lessons 1 and 2 keep working. The tool-approval code path is independent of which server is configured; it was exercised here against a local stdio MCP server, with the same client and the same `interrupt()` wrapper.

1) **Start processing**
```bash
curl -X POST -H "Content-Type: application/json" -d '{"human_request": "Provide info about my account on github"}' http://localhost:8000/mcp/start
```

2) **Approve the tool**
```bash
curl -X POST -H "Content-Type: application/json" -d '{
  "thread_id": "{thread_id}",
  "approve_action": "approved"
}' http://localhost:8000/mcp/approve
```

3) **Start processing 2**
```bash
curl -X POST -H "Content-Type: application/json" -d '{"human_request": "Create a new github repo with the name langgraph-mcp"}' http://localhost:8000/mcp/start
```

4) **Reject the tool**
```bash
curl -X POST -H "Content-Type: application/json" -d '{
  "thread_id": "{thread_id}",
  "approve_action": "rejected"
}' http://localhost:8000/mcp/approve
```

Replace `{thread_id}` with the actual thread_id you receive from the creation endpoint. You can also use the interactive API docs at [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs) to experiment with these endpoints.

## Notebooks

`backend/notebooks/` walks the same three ideas without HTTP, one cell per step:

```powershell
uv run jupyter lab notebooks
```

- `graph.ipynb` - build the draft/review graph, invoke it, `update_state` with feedback, resume, approve.
- `streaming_graph.ipynb` - `graph.stream(..., stream_mode="messages")`.
- `mcp_agent.ipynb` - load MCP servers, wrap tools with `interrupt()`, approve a call.

The diagram helper in `notebooks/tools.py` renders through mermaid.ink.

## LangGraph Studio (optional)

`backend/studio/langgraph.json` points Studio at `human-in-the-loop.py` and at `../.env`. Install the CLI and start it from that folder:

```powershell
uv add --dev "langgraph-cli[inmem]"
cd studio
uv run langgraph dev
```

## How to Run the Frontend

```powershell
cd frontend
npm install
npm start
```

Open [http://localhost:3000](http://localhost:3000). The frontend talks to the backend at [http://localhost:8000](http://localhost:8000).

## Differences from the upstream demo

| Upstream | Here | Why |
|----------|------|-----|
| `ChatOpenAI(model="gpt-4o-mini")`, `model="openai:gpt-4o-mini"` in the agent | `ChatDeepSeek(model=MODEL)` from `app/config.py` | the course runs on DeepSeek |
| `requirements.txt` in `backend/` and `backend/studio/` | `pyproject.toml` + `uv.lock` | one lock, one `uv sync` |
| `OPENAI_API_KEY` exported by the shell | `backend/.env` via `python-dotenv` | the API, notebooks, and Studio read the same file |
| `pyppeteer` for notebook diagrams | `MermaidDrawMethod.API` (mermaid.ink) | pyppeteer pins `websockets<11`, which breaks uvicorn 0.5x at startup |
| `dependencies: ["."]` in `studio/langgraph.json` with a second requirements file | `dependencies: [".."]` | Studio installs the one backend project |

## Learning Goals

- Understand how to embed LangGraph in a real backend application.
- See how to implement HITL workflows that pause for human input and resume programmatically.
- Learn how to connect a Python backend to a modern React frontend.
- Explore practical patterns for managing agent state and user interaction.
- Compare blocking vs streaming implementations for AI-powered applications.
