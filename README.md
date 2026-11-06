# AI Engineering — From First LLM Call to a Grounded RAG Product

An 18-lesson, build-first course for experienced software engineers moving into AI engineering. It starts with a single chat-completion call, builds toward a Supabase + pgvector filing analyst whose answers are cited, validated and allowed to refuse, and closes with a batch pipeline that turns YouTube RSS and transcripts into a daily email.

**Start here → [Lesson 1: What an AI Engineer Is in 2026](lessons/0001-ai-engineering-landscape-2026.html)**

---

## The 18 lessons

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
| 18 | [Project: AI News Digest — YouTube First](lessons/0018-project-youtube-digest.html) | Batch aggregator: unstable RSS, transcript fallbacks and IP bans, SQLAlchemy models with Alembic, a bounded DeepSeek prompt from your own editorial brief, strict JSON, gated email, and the scheduler phase left honestly open. | ~60 min |


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
| [0018-ai-coding-youtube-transcript-postgresql](assets/examples/0018-ai-coding-youtube-transcript-postgresql/index.html) | Lesson 18 | AI news digest, YouTube collector first: RSS, transcripts, PostgreSQL and email |

---


## What you need

- **Python 3.12+** and [`uv`](https://docs.astral.sh/uv/) for every Python lab.
- **Node.js 20+** and `pnpm` for the frontend examples.
- **DeepSeek API key** for the hosted-model lessons. Some lessons also use **Qwen/DashScope** embeddings.
- **Ollama** for lesson 14; no API key is needed there.
- **Docker** for lesson 16's cluster rehearsal and lesson 18's local PostgreSQL container.
- **SMTP credentials** for lesson 18's optional email send; a Gmail app password works, and the lab previews without sending by default.