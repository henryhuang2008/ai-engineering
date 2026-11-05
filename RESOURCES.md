# AI Engineering Resources

## Knowledge

- [Book: _AI Engineering: Building Applications with Foundation Models_ by Chip Huyen (O'Reilly, 2025)](https://www.oreilly.com/library/view/ai-engineering/9781098166298/)
  The definitive textbook on application-direction AI engineering: LLM APIs, prompt engineering, RAG, agents, evaluation, deployment. Most-read O'Reilly book of 2025. Use for: everything from stack overview to production tradeoffs. [Companion resources repo](https://github.com/chiphuyen/aie-book/blob/main/resources.md).
- [AI Engineering Skills Map — DeepLearning.AI](https://www.deeplearning.ai/resources/ai-engineering-skills/)
  Analysis of 10,000+ job postings + expert interviews. Identifies the four pillars: building/deploying AI apps, software engineering fundamentals, using coding agents, shaping the build. Use for: prioritization, understanding what employers actually hire for.
- [AI Engineer Roadmap — roadmap.sh](https://roadmap.sh/ai-engineer)
  Community-maintained step-by-step skill tree with curated links per topic. Use for: checking off skills, finding per-topic tutorials.
- [Anthropic Prompt Engineering Interactive Tutorial](https://github.com/anthropics/prompt-engineering-interactive-tutorial)
  Hands-on exercises for prompting Claude. Use for: first contact with LLM APIs and prompt patterns.
- [dair-ai/Prompt Engineering Guide](https://github.com/dair-ai/Prompt-Engineering-Guide)
  Comprehensive, open collection of prompt techniques (zero-shot, few-shot, CoT, ReAct). Use for: prompt technique reference.
- [Anthropic: Introducing Contextual Retrieval](https://www.anthropic.com/news/contextual-retrieval)
  Practical techniques for preparing data for RAG; when to use RAG vs long context. Use for: RAG pipeline design.
- [OpenAI API Documentation](https://platform.openai.com/docs) / [Anthropic API Documentation](https://docs.anthropic.com)
  Primary sources for the two dominant model APIs: chat, tools, structured outputs, streaming. Use for: API-level details when building.
- [LangChain Documentation](https://python.langchain.com/docs/introduction/) / [LangGraph](https://langchain-ai.github.io/langgraph/)
  Dominant orchestration frameworks for RAG and agents. Use for: after the raw API basics are solid.
- [Roadmap: The Roadmap to Becoming an LLM Engineer in 2026 — KDnuggets](https://www.kdnuggets.com/the-roadmap-to-becoming-an-llm-engineer-in-2026)
  Clean five-stage path: foundations → prompting/tool-calling → retrieval → fine-tuning/alignment → serving/ops. Use for: sequencing projects.
- [Model Context Protocol — official spec](https://modelcontextprotocol.io)
  The open standard for agent↔tool connections. Use for: building MCP servers, understanding tools/resources/transports. Now governed by the Linux Foundation's Agentic AI Foundation.
- [Anthropic: Donating MCP & the Agentic AI Foundation](https://www.anthropic.com/news/donating-the-model-context-protocol-and-establishing-of-the-agentic-ai-foundation)
  The announcement establishing MCP as industry infrastructure (OpenAI, Google, Microsoft, AWS co-governing). Use for: understanding why MCP is a durable hiring bet, not a fad.
- [Anthropic Agent Skills documentation](https://docs.claude.com/en/docs/agents-and-tools/agent-skills)
  How file-based agent Skills work. Use for: the complementary standard to MCP — encoding reusable know-how for agents.
- [LangGraph documentation](https://langchain-ai.github.io/langgraph/) + [LangChain Academy (free courses)](https://academy.langchain.com/)
  The market-default agent orchestration framework (state graphs, checkpointing, human-in-the-loop). Use for: the agents phase of the curriculum, after raw API basics.
- [OpenAI Agents SDK](https://openai.github.io/openai-agents-python/)
  Lightweight vendor-native agent runtime with built-in tracing. Use for: understanding the minimal agent primitives (agents, handoffs, guardrails) — compare against LangGraph's approach.
- [Semantic Kernel (Microsoft)](https://learn.microsoft.com/en-us/semantic-kernel/overview)
  Microsoft's enterprise AI SDK — C#, Python, Java; DI-style kernel, plugins, MCP, Azure-first. Use for: Henry's .NET-differentiator path; enterprise Azure shops demand this.

## Wisdom (Communities)

- [r/MachineLearning](https://reddit.com/r/MachineLearning)
  Research-heavy but high-moderation; filter to `[D]` discussion and industry threads for application insight.
- [r/LocalLLaMA](https://reddit.com/r/LocalLLaMA)
  Very active practitioner community on running/open models, tooling tradeoffs. Use for: model selection, deployment reality-checks.
- [AI Engineer Discord / conference community](https://www.ai.engineer)
  The conference that named the role; community of practice with practitioners shipping LLM apps. Use for: hiring signals, system design discussions.
- [LangChain Discord](https://discord.gg/langchain)
  High volume of real RAG/agent debugging questions with framework maintainers present.

## Gaps

- No single high-quality source yet for **AI engineering with a .NET/C# stack** — most ecosystem material is Python. This will need curated C#-specific resources (Semantic Kernel, Microsoft Foundry) as Henry progresses.
- Evals (evaluation-driven development) as a standalone learning resource is thin; will need to lean on Chip Huyen's eval chapters + LangSmith docs initially.
