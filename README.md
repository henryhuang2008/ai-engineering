# AI Engineering — From First LLM Call to a Grounded RAG Product

A 22-lesson, build-first course for experienced software engineers moving into AI engineering. It starts with a single chat-completion call, builds toward a Supabase + pgvector filing analyst whose answers are cited, validated and allowed to refuse, closes with a batch pipeline that turns YouTube RSS and transcripts into a daily email, covers the two memory systems that decide what an agent remembers and the skill format that decides what instructions it can carry, shows what happens when model output is about to touch a real system in a text-to-SQL agent, and ends with a voice agent built twice: once as a terminal loop, once over a LiveKit room.

**Start here → [Lesson 1: What an AI Engineer Is in 2026](lessons/0001-ai-engineering-landscape-2026.html)**

**Read the rendered course → <https://henryhuang2008.github.io/ai-engineering/>**

GitHub's file view shows `.html` files as source, not as pages. The Pages site
serves the same files as a site. If the link 404s, enable it once under
**Settings → Pages → Deploy from a branch → `main` / (root)**.

---

## The 22 lessons

| # | Lesson | What it covers | Time |
|---|--------|----------------|------|
| 1 | [What an AI Engineer Is in 2026](lessons/0001-ai-engineering-landscape-2026.html) | The six-layer application stack, the four hiring pillars, and which parts your existing software background already covers. | ~15 min |
| 2 | [Your First LLM Call](lessons/0002-your-first-llm-api-call.html) | The core atom: messages, streamed tokens, one tool round trip and pydantic-typed output, driven through LangChain against DeepSeek. | ~30 min |
| 3 | [Function Calling: The Model Asks, Your Code Acts](lessons/0003-function-calling.html) | Close the tool loop by hand — schemas, execution, results — then hand the same loop to `create_agent` and see what the framework does and does not hide. | ~35 min |
| 4 | [Streaming Chat: Python Backend, Next.js Shell](lessons/0004-streaming-chat.html) | A streaming Python backend, a thin Next.js route, and a real chat UI instead of a bare input. | ~40 min |
| 5 | [Your First Evals](lessons/0005-your-first-evals.html) | Build an eval set so "the output looks fine" becomes a measurable answer. | ~35 min |
| 6 | [RAG: The Pipeline, End to End](lessons/0006-rag-foundation.html) | The eight-stage RAG map: what each stage takes in, produces, and gets wrong. | ~30 min |
| 7 | [The RAG Service: Two Lanes, One Table, and a LlamaIndex Variant](lessons/0007-rag-service.html) | Build it by hand: ingest a corpus, index it in LanceDB, retrieve, and answer with citations. Then the same service rebuilt with LlamaIndex. | ~55 min |
| 8 | [RAG Appendix: Chunking Tools and Vector Stores](lessons/0008-rag-appendix.html) | The reference for chunking frameworks and the vector stores you are actually choosing between. | ~30 min |
| 9 | [MCP: Write the Tool Once, Call It From Any Client](lessons/0009-mcp.html) | Build an MCP server, call it with no model, then use a hand-written loop and LangChain's MCPAdapter. | ~60 min |
| 10 | [LangGraph: One Node, Then a Branch](lessons/0010-langgraph.html) | Go from a one-node graph to a program with a visible decision. | ~40 min |
| 11 | [LangGraph, Advanced: Fan-Out, Fan-In, and the Join That Fires Early](lessons/0011-langgraph-advanced.html) | Parallel branches, early joins, and reconciling results without waiting for the wrong things. | ~50 min |
| 12 | [Python Libraries Every AI Engineer Should Know](lessons/0012-python-libraries-for-ai.html) | The small contracts — validation, storage, tracing, testing, agents, MCP, evals — that make up a real stack. | ~50 min |
| 13 | [Pydantic: Make Bad Data Fail at the Boundary](lessons/0013-pydantic.html) | One validation contract shared by FastAPI, database code and the model. | ~45 min |
| 14 | [Ollama + LlamaIndex: A Local RAG Agent, No API Key](lessons/0014-ollama-local-rag.html) | The same RAG shape fully local, with Qwen3 4B and embeddings on your machine. | ~45 min |
| 15 | [AI Coding: The Tools, the Models, and the Loop That Ships](lessons/0015-ai-coding.html) | The nine-stage loop: repository rules, skills, TODO.md, gates and model choice. | ~55 min |
| 16 | [Kubernetes GitOps: Jenkins Builds, Git Declares, Argo CD Reconciles](lessons/0016-kubernetes-gitops.html) | Jenkins owns CI; Git owns desired state; Argo CD is the only cluster writer. | ~55 min |
| 17 | [Project: Supabase + RAG + AI Coding — A Grounded Filing Analyst](lessons/0017-project-supabase-rag-ai-coding.html) | Capstone: Supabase pgvector, hybrid retrieval, a grounded PydanticAI agent, a trust UI, and an honest scorecard. | ~60 min |
| 18 | [Project: AI News Digest — YouTube First](lessons/0018-project-youtube-digest.html) | Batch aggregator: unstable RSS, transcript fallbacks and IP bans, SQLAlchemy models with Alembic, a bounded DeepSeek prompt from your own editorial brief, strict JSON, gated email, and the scheduler phase left honestly open. | ~60 min |
| 19 | [Memory in Agents — Short-Term, Long-Term, and PostgreSQL](lessons/0019-memory-agents-langgraph.html) | When and why to use each memory; the example's demo, facts and chat workflow; trimming and summarization; and PostgresSaver plus PostgresStore with the restart test. | ~35 min |
| 20 | [Agent Skills — Run the Example](lessons/0020-agent-skills.html) | Run a two-skill library end to end — catalog, ask, script, lint, tests — follow one question through the tool calls, and learn the six rules and four failures that decide whether a skill works. | ~30 min |
| 21 | [Text to SQL — The Model Proposes, the Guard Decides](lessons/0021-text-to-sql.html) | A custom LangGraph SQL agent over SQLite: a strict query contract, a six-layer read-only guard, a bounded retry loop, human approve/edit/reject, and the questions the schema cannot answer. | ~40 min |
| 22 | [Voice Agents — The Terminal Loop, Then a LiveKit Room](lessons/0022-voice-agents-langgraph-livekit.html) | One expense agent built twice: a readable record → transcribe → graph → speak loop, then the same pipeline in a LiveKit room with VAD, barge-in, a browser client and a Docker media server. | ~45 min |


---


## Labs and example repositories

Every Python example is a `uv` project; every frontend uses `pnpm`. Run commands from the example's own README.

| Example | Companion lesson | What is inside |
|---------|------------------|----------------|
| [0002-first-llm-api](assets/examples/0002-first-llm-api/index.html) | Lesson 2 | First API call, streaming and typed output |
| [0003-function-calling](assets/examples/0003-function-calling/index.html) | Lesson 3 | The hand-written tool loop and the same task as an agent call |
| [0004-streaming-chat](assets/examples/0004-streaming-chat/index.html) | Lesson 4 | Streaming backend and chat shell |
| [0005-first-evals](assets/examples/0005-first-evals/index.html) | Lesson 5 | Eval harness and test cases |
| [0007-rag-service](assets/examples/0007-rag-service/index.html) | Lesson 7 | LanceDB RAG pipeline |
| [0007-rag-service-llamaindex](assets/examples/0007-rag-service-llamaindex/index.html) | Lesson 7 | The LlamaIndex variant |
| [0009-mcp](assets/examples/0009-mcp/index.html) | Lesson 9 | MCP server, raw clients, and LangChain's MCPAdapter |
| [0010-langgraph](assets/examples/0010-langgraph/index.html) | Lesson 10 | One node, then a branch |
| [0011-langgraph-advanced](assets/examples/0011-langgraph-advanced/index.html) | Lesson 11 | Fan-out and fan-in |
| [0013-pydantic](assets/examples/0013-pydantic/index.html) | Lesson 13 | Validation boundary and typed model output |
| [0014-ollama-local-rag](assets/examples/0014-ollama-local-rag/index.html) | Lesson 14 | Local LlamaIndex RAG |
| [0015-document-copilot](assets/examples/0015-document-copilot/index.html) | Lesson 15 | Client brief and skeleton for the AI-coding workflow |
| [0017-ai-coding-rag-supabase](assets/examples/0017-ai-coding-rag-supabase/index.html) | Lesson 17 | The capstone repository |
| [0018-ai-coding-youtube-transcript-postgresql](assets/examples/0018-ai-coding-youtube-transcript-postgresql/index.html) | Lesson 18 | AI news digest, YouTube collector first: RSS, transcripts, PostgreSQL and email |
| [0019-memory-agents-langgraph](assets/examples/0019-memory-agents-langgraph/index.html) | Lesson 19 | Memory in agents: LangGraph checkpointer and store, trimming and summarization, 19 tests |
| [0020-agent-skills-python](assets/examples/0020-agent-skills-python/index.html) | Lesson 20 | Agent Skills in Python: SKILL.md library, 18-rule linter, Pydantic AI deferred capabilities, 34 tests |
| [0021-text-to-sql](assets/examples/0021-text-to-sql/index.html) | Lesson 21 | Text to SQL: seeded SQLite, guarded LangGraph agent, review interrupt, 29 tests |
| [example-Voice-langgraph](assets/examples/example-Voice-langgraph/index.html) | Lesson 22 | Terminal voice agent: mic → whisper/Qwen ASR → LangGraph + MCP → Qwen3-TTS, 56 offline checks |
| [example-livekit-langgraph](assets/examples/example-livekit-langgraph/index.html) | Lesson 22 | The same agent in a LiveKit room: Docker server, browser client, VAD and barge-in, 30 offline checks |

---


## What you need

- **Python 3.12+** and [`uv`](https://docs.astral.sh/uv/) for every Python lab.
- **Node.js 20+** and `pnpm` for the frontend examples.
- **DeepSeek API key** for the hosted-model lessons. Some lessons also use **Qwen/DashScope** embeddings; lesson 22 uses it for both speech directions.
- **Ollama** for lesson 14; no API key is needed there.
- **Docker** for lesson 16's cluster rehearsal, lesson 18's local PostgreSQL container, and lesson 22's LiveKit server.
- **A microphone and a browser** for lesson 22's live paths; both examples ship a smoke script that runs a full turn without either.
- **SMTP credentials** for lesson 18's optional email send; a Gmail app password works, and the lab previews without sending by default.