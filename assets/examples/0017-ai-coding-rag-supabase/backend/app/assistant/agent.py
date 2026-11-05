from __future__ import annotations

from pathlib import Path
from typing import Annotated
from uuid import UUID

from openai import AsyncOpenAI
from pydantic import Field
from pydantic_ai import Agent, RunContext
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from app.assistant.deps import DocumentAgentDeps, ProgressReporter
from app.assistant.evidence import (
    EvidencePassage,
    EvidencePassageWindow,
    to_evidence_passage,
    to_evidence_passages,
    to_evidence_window,
)
from app.assistant.outputs import GroundedAnswer
from app.chat.orchestrator import ChatOrchestrator
from app.config import Settings, settings
from app.retrieval import SearchFilters, create_retriever
from app.retrieval.models import MAX_NEIGHBOR_WINDOW, MAX_QUERY_LENGTH, MAX_RESULTS
from app.retrieval.retriever import HybridRetriever

MAX_AGENT_REQUESTS = 8
MAX_TOOL_CALLS = 12
MAX_AGENT_OUTPUT_TOKENS = 4_000


def create_document_agent(
    model: OpenAIChatModel,
) -> Agent[DocumentAgentDeps, GroundedAnswer]:
    instructions = Path(__file__).with_name("instructions.md").read_text(encoding="utf-8")
    agent = Agent(
        model,
        name="document_copilot",
        deps_type=DocumentAgentDeps,
        output_type=GroundedAnswer,
        instructions=instructions,
        retries=2,
    )

    @agent.tool
    async def search_filings(
        ctx: RunContext[DocumentAgentDeps],
        query: Annotated[str, Field(min_length=1, max_length=MAX_QUERY_LENGTH)],
        ticker: Annotated[str | None, Field(max_length=10)] = None,
        fiscal_year: Annotated[int | None, Field(ge=1900, le=2200)] = None,
        filing_type: Annotated[str | None, Field(max_length=20)] = None,
    ) -> list[EvidencePassage]:
        """Search filing passages with optional ticker, fiscal-year, and form filters."""
        filters = SearchFilters(
            ticker=ticker,
            fiscal_year=fiscal_year,
            filing_type=filing_type,
        )
        if ctx.deps.report_progress is not None:
            ctx.deps.report_progress("Searching additional filing passages...")
        passages = await ctx.deps.search_filings(
            query,
            filters,
            limit=MAX_RESULTS,
        )
        for passage in passages:
            ctx.deps.remember(passage)
        _report_generation_started(ctx.deps.report_progress)
        return to_evidence_passages(passages)

    @agent.tool
    async def read_chunk(
        ctx: RunContext[DocumentAgentDeps],
        chunk_id: UUID,
    ) -> EvidencePassage | None:
        """Read a retrieved filing chunk by its ID."""
        if ctx.deps.report_progress is not None:
            ctx.deps.report_progress("Reading a source passage...")
        passage = await ctx.deps.retriever.read_chunk(chunk_id)
        if passage is not None:
            ctx.deps.remember(passage)
        _report_generation_started(ctx.deps.report_progress)
        return to_evidence_passage(passage) if passage is not None else None

    @agent.tool
    async def read_surrounding_chunks(
        ctx: RunContext[DocumentAgentDeps],
        chunk_id: UUID,
        window: Annotated[int, Field(ge=0, le=MAX_NEIGHBOR_WINDOW)] = 1,
    ) -> EvidencePassageWindow | None:
        """Read the selected chunk with a bounded same-filing neighbor window."""
        if ctx.deps.report_progress is not None:
            ctx.deps.report_progress("Checking neighboring source passages...")
        passage_window = await ctx.deps.retriever.read_surrounding_chunks(
            chunk_id,
            window=window,
        )
        if passage_window is not None:
            ctx.deps.remember_window(passage_window)
        _report_generation_started(ctx.deps.report_progress)
        return to_evidence_window(passage_window) if passage_window is not None else None

    return agent


def _report_generation_started(report_progress: ProgressReporter | None) -> None:
    if report_progress is not None:
        report_progress("Generating an answer and verifying its citations...")


def create_chat_runtime(config: Settings = settings) -> ChatRuntime:
    if not config.deepseek_api_key:
        raise RuntimeError("DEEPSEEK_API_KEY is required for the chat agent.")
    if not config.deepseek_base_url.strip():
        raise RuntimeError("DEEPSEEK_BASE_URL must not be empty.")
    if not config.deepseek_model.strip():
        raise RuntimeError("DEEPSEEK_MODEL must not be empty.")

    retriever = create_retriever(config)
    client = AsyncOpenAI(
        api_key=config.deepseek_api_key.get_secret_value(),
        base_url=config.deepseek_base_url,
        timeout=90.0,
        max_retries=1,
    )
    model = OpenAIChatModel(
        config.deepseek_model,
        provider=OpenAIProvider(openai_client=client),
    )
    agent = create_document_agent(model)

    return ChatRuntime(ChatOrchestrator(agent, retriever), retriever, client)


class ChatRuntime:
    def __init__(
        self,
        orchestrator: ChatOrchestrator,
        retriever: HybridRetriever,
        client: AsyncOpenAI,
    ) -> None:
        self.orchestrator = orchestrator
        self._retriever = retriever
        self._client = client

    async def aclose(self) -> None:
        try:
            await self._retriever.aclose()
        finally:
            await self._client.close()


__all__ = ["ChatRuntime", "create_chat_runtime", "create_document_agent"]
