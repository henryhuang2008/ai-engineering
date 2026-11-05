# AI Engineering — From First LLM Call to a Grounded RAG Product

A 17-lesson, build-first course for experienced software engineers moving into AI engineering. It starts with a single chat-completion call and ends with a capstone: a Supabase + pgvector filing analyst whose answers are cited, validated and allowed to refuse.

**Start here → [Lesson 1: What an AI Engineer Is in 2026](lessons/0001-ai-engineering-landscape-2026.html)**

The lessons are self-contained HTML pages. Read them in a browser, or publish this repository with GitHub Pages (see [How to read the course](#how-to-read-the-course)).

---

## The 17 lessons

| # | Lesson | What it covers | Time |
|---|--------|----------------|------|
| 1 | [What an AI Engineer Is in 2026](lessons/0001-ai-engineering-landscape-2026.html) | The six-layer application stack, the four hiring pillars, and which parts your existing software background already covers. | ~15 min |
| 2 | [Your First LLM Call](lessons/0002-your-first-llm-api-call.html) | The core atom: messages, streamed tokens, one tool round trip and pydantic-typed output, driven through LangChain against DeepSeek. | ~30 min |
| 3 | [Function Calling: The Model Asks, Your Code Acts](lessons/0003-function-calling.html) | Close the tool loop by hand — schemas, execution, results — so agent frameworks stop being magic. | ~25 min |
| 4 | [Streaming Chat: Python Backend, Next.js Shell](lessons/0004-streaming-chat.html) | A streaming Python backend, a thin Next.js route, and a real chat UI instead of a bare input. | ~40 min |
| 5 | [Your First Evals](lessons/0005-your-first-evals.html) | Build an eval set so "the output looks fine" becomes a measurable answer. | ~35 min |
| 6 | [RAG: The Pipeline, End to End](lessons/0006-rag-foundation.html) | The eight-stage RAG map: what each stage takes in, produces, and gets wrong. | ~30 min |
| 7 | [The RAG Service: Two Lanes, One Table](lessons/0007-rag-service.html) | Build it: ingest a corpus, index it in LanceDB, retrieve, and answer with citations. | ~55 min |
| 8 | [RAG Appendix: Chunking Tools and Vector Stores](lessons/0008-rag-appendix.html) | The reference for chunking frameworks and the vector stores you are actually choosing between. | ~30 min |
| 9 | [MCP: Write the Tool Once, Call It From Any Client](lessons/0009-mcp.html) | Build an MCP server, call it with no model, then let DeepSeek drive it. | ~45 min |
| 10 | [LangGraph: One Node, Then a Branch](lessons/0010-langgraph.html) | Go from a one-node graph to a program with a visible decision. | ~40 min |
| 11 | [LangGraph, Advanced: Fan-Out, Fan-In, and the Join That Fires Early](lessons/0011-langgraph-advanced.html) | Parallel branches, early joins, and reconciling results without waiting for the wrong things. | ~50 min |
| 12 | [Python Libraries Every AI Engineer Should Know](lessons/0012-python-libraries-for-ai.html) | The small contracts — validation, storage, tracing, testing, agents, MCP, evals — that make up a real stack. | ~50 min |
| 13 | [Pydantic: Make Bad Data Fail at the Boundary](lessons/0013-pydantic.html) | One validation contract shared by FastAPI, database code and the model. | ~45 min |
| 14 | [Ollama + LlamaIndex: A Local RAG Agent, No API Key](lessons/0014-ollama-local-rag.html) | The same RAG shape fully local, with Qwen3 4B and embeddings on your machine. | ~45 min |
| 15 | [AI Coding: The Tools, the Models, and the Loop That Ships](lessons/0015-ai-coding.html) | The nine-stage loop: repository rules, skills, TODO.md, gates and model choice. | ~55 min |
| 16 | [Kubernetes GitOps: Jenkins Builds, Git Declares, Argo CD Reconciles](lessons/0016-kubernetes-gitops.html) | Jenkins owns CI; Git owns desired state; Argo CD is the only cluster writer. | ~55 min |
| 17 | [Project: Supabase + RAG + AI Coding — A Grounded Filing Analyst](lessons/0017-project-supabase-rag-ai-coding.html) | Capstone: Supabase pgvector, hybrid retrieval, a grounded PydanticAI agent, a trust UI, and an honest scorecard. | ~60 min |

About 12 hours of lessons and labs. Each lesson ends with a quiz and links to primary sources.

---

## The two projects and the capstone

The course builds toward portfolio work, not certificates:

1. **Chat assistant** (lessons 2–5) — API call, tool loop, streaming React/Next.js UI, eval harness.
2. **Docs RAG service** (lessons 6–8, plus the local variant in 14) — ingestion, chunking, embeddings, retrieval, grounded citations.
3. **Capstone** (lesson 17) — the Supabase + RAG + AI-coding filing analyst, with its open verification gates left visible.

The capstone is a working repository through Phase 7. It does not claim to be production-verified: source offsets, client-brief retrieval coverage, representative-question grounding, and the browser citation path are still open, and the pilot and deployment phases have not started.

---

## Labs and example repositories

Every Python example is a `uv` project; every frontend uses `pnpm`. Run commands from the example's own README.

| Example | Companion lesson | What is inside |
|---------|------------------|----------------|
| [0002-first-llm-api](assets/examples/0002-first-llm-api/index.html) | Lesson 2 | First API call, streaming and typed output |
| [0003-function-calling](assets/examples/0003-function-calling/index.html) | Lesson 3 | The hand-written tool loop |
| [0004-streaming-chat](assets/examples/0004-streaming-chat/index.html) | Lesson 4 | Streaming backend and chat shell |
| [0005-first-evals](assets/examples/0005-first-evals/index.html) | Lesson 5 | Eval harness and test cases |
| [0007-rag-service](assets/examples/0007-rag-service/index.html) | Lesson 7 | LanceDB RAG pipeline |
| [0007-rag-service-llamaindex](assets/examples/0007-rag-service-llamaindex/index.html) | Lesson 7 | The LlamaIndex variant |
| [0009-mcp](assets/examples/0009-mcp/index.html) | Lesson 9 | MCP server and client calls |
| [0010-langgraph](assets/examples/0010-langgraph/index.html) | Lesson 10 | One node, then a branch |
| [0011-langgraph-advanced](assets/examples/0011-langgraph-advanced/index.html) | Lesson 11 | Fan-out and fan-in |
| [0013-pydantic](assets/examples/0013-pydantic/index.html) | Lesson 13 | Validation boundary and typed model output |
| [0014-ollama-local-rag](assets/examples/0014-ollama-local-rag/index.html) | Lesson 14 | Local LlamaIndex RAG |
| [0015-document-copilot](assets/examples/0015-document-copilot/index.html) | Lesson 15 | Client brief and skeleton for the AI-coding workflow |
| [0017-ai-coding-rag-supabase](assets/examples/0017-ai-coding-rag-supabase/index.html) | Lesson 17 | The capstone repository |

---

## How to read the course

### Locally

Clone the repository and open `lessons/0001-ai-engineering-landscape-2026.html` in a browser. The pages share `assets/course.css` and `assets/quiz.js`; keep the folder structure intact.

### On GitHub Pages

1. Push the repository to GitHub.
2. Open **Settings → Pages**.
3. Under **Build and deployment**, choose **Deploy from a branch**, then `main` and `/ (root)`.
4. Open `https://<your-username>.github.io/<repo-name>/`.

GitHub renders this README as the site home page, and the relative lesson links above open the actual HTML lessons. On `github.com` itself, clicking an `.html` file shows its source rather than the rendered page, so use Pages (or a local clone) for reading.

---

## What you need

- **Python 3.12+** and [`uv`](https://docs.astral.sh/uv/) for every Python lab.
- **Node.js 20+** and `pnpm` for the frontend examples.
- **DeepSeek API key** for the hosted-model lessons. Some lessons also use **Qwen/DashScope** embeddings.
- **Ollama** for lesson 14; no API key is needed there.
- **Docker** and a local Kubernetes cluster (`kind`) for lesson 16 if you run the rehearsal.

The labs are live: they call real providers or a real local model. There is no fake-model mode. If a key is missing, the lab tells you; it does not silently substitute a stub.

---

## Repository layout

```text
.
├─ lessons/             17 HTML lessons, in numeric order
├─ reference/           skill map, boundary map and glossary pages
├─ assets/
│  ├─ course.css        shared course stylesheet
│  ├─ quiz.js           quiz renderer
│  ├─ images/           diagrams used by the lessons
│  └─ examples/         runnable labs and the capstone repository
├─ check_links.py       verifies every local link and forward lesson link
└─ check_uv.py          verifies every Python example is a uv project
```

---

## Repository checks

```bash
python check_links.py
python check_uv.py
```

`check_links.py` verifies that every relative link resolves, that each lesson's **What's next** links to the next lesson, and that no page cites a lesson number that does not exist. `check_uv.py` verifies that every Python example carries a `pyproject.toml` and a sibling `uv.lock`.
