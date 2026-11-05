import asyncio
from datetime import date
from types import SimpleNamespace
from uuid import UUID

from app.assistant.deps import DocumentAgentDeps, ProgressReporter
from app.assistant.outputs import GroundedAnswer, GroundedClaim
from app.chat.orchestrator import (
    MAX_AGENT_INPUT_TOKENS,
    MAX_AGENT_OUTPUT_TOKENS,
    MAX_AGENT_REQUESTS,
    MAX_AGENT_TOTAL_TOKENS,
    MAX_TOOL_CALLS,
    ChatOrchestrator,
)
from app.retrieval.models import MAX_RESULTS, Passage

USER_ID = UUID("a61b2c08-8c8d-4c54-9dbb-f9828eb04818")
THREAD_ID = UUID("6dc1c1fa-1429-4c8c-92b0-1cd9bf1f95b7")
CHUNK_ID = UUID("a61b2c08-8c8d-4c54-9dbb-f9828eb04820")


class FakeRetriever:
    def __init__(self, passages: list[Passage] | None = None) -> None:
        self.passages = passages if passages is not None else [_passage()]
        self.search_calls = 0

    async def search_filings(
        self,
        query: str,
        filters: object = None,
        *,
        limit: int,
        report_progress: ProgressReporter | None = None,
    ) -> list[Passage]:
        self.search_calls += 1
        if report_progress is not None:
            report_progress("Searching filing chunks in PostgreSQL...")
        assert limit == MAX_RESULTS
        return self.passages


class FakeAgent:
    def __init__(self) -> None:
        self.prompt: str | None = None
        self.deps: object | None = None
        self.usage_limits: object | None = None

    async def run(self, prompt: str, *, deps: object, usage_limits: object) -> object:
        self.prompt = prompt
        self.deps = deps
        self.usage_limits = usage_limits
        deps.remember(
            Passage(
                chunk_id=CHUNK_ID,
                document_id=THREAD_ID,
                chunk_index=0,
                content="The filing reported revenue.",
                section="Revenue",
                source_start=None,
                source_end=None,
                chunk_metadata={"page_references": []},
                document_metadata={},
                ticker="GOOGL",
                company_name="Alphabet Inc.",
                fiscal_year=2025,
                filing_type="10-K",
                filing_date=date(2026, 2, 5),
                accession_number="0001652044-26-000012",
                source_url="https://example.test/filing",
            )
        )
        return SimpleNamespace(
            output=GroundedAnswer(
                insufficient_evidence=False,
                claims=[GroundedClaim(text="Revenue increased.", citation_ids=[CHUNK_ID])],
            )
        )


def test_orchestrator_uses_bounded_server_history_and_agent_limits() -> None:
    agent = FakeAgent()
    orchestrator = ChatOrchestrator(agent, FakeRetriever())
    history = [
        {"role": "user", "content": "Previous question"},
        {"role": "assistant", "content": "Previous answer"},
    ]

    answer = asyncio.run(
        orchestrator.complete_turn(
            user_id=USER_ID,
            thread_id=THREAD_ID,
            question="What changed?",
            history=history,
        )
    )

    assert agent.prompt is not None
    assert "Previous server-stored conversation" in agent.prompt
    assert "Previous answer" in agent.prompt
    assert "Initial retrieved filing passages" in agent.prompt
    assert "What changed?" in agent.prompt
    assert answer.text == "Revenue increased. [1]"
    assert agent.usage_limits.request_limit == MAX_AGENT_REQUESTS
    assert agent.usage_limits.tool_calls_limit == MAX_TOOL_CALLS
    assert agent.usage_limits.output_tokens_limit == MAX_AGENT_OUTPUT_TOKENS
    assert agent.usage_limits.input_tokens_limit == MAX_AGENT_INPUT_TOKENS
    assert agent.usage_limits.total_tokens_limit == MAX_AGENT_TOTAL_TOKENS


def test_orchestrator_truncates_long_history() -> None:
    agent = FakeAgent()
    orchestrator = ChatOrchestrator(agent, FakeRetriever())

    asyncio.run(
        orchestrator.complete_turn(
            user_id=USER_ID,
            thread_id=THREAD_ID,
            question="Question",
            history=[{"role": "user", "content": "x" * 10_000}],
        )
    )

    assert agent.deps.conversation_context.count("x") <= 2_000


def test_orchestrator_returns_refusal_without_calling_model_when_no_passages() -> None:
    agent = FakeAgent()
    orchestrator = ChatOrchestrator(agent, FakeRetriever(passages=[]))

    answer = asyncio.run(
        orchestrator.complete_turn(
            user_id=USER_ID,
            thread_id=THREAD_ID,
            question="What changed?",
            history=[],
        )
    )

    assert answer.citations == []
    assert "not sufficient" in answer.text
    assert agent.prompt is None


def test_orchestrator_reports_retrieval_and_generation_progress() -> None:
    agent = FakeAgent()
    orchestrator = ChatOrchestrator(agent, FakeRetriever())
    progress: list[str] = []

    asyncio.run(
        orchestrator.complete_turn(
            user_id=USER_ID,
            thread_id=THREAD_ID,
            question="Question",
            history=[],
            report_progress=progress.append,
        )
    )

    assert "Searching the filing corpus..." in progress
    assert "Searching filing chunks in PostgreSQL..." in progress
    assert "Generating an answer and verifying its citations..." in progress


def test_agent_dependencies_coalesce_identical_supabase_searches() -> None:
    retriever = FakeRetriever()
    deps = DocumentAgentDeps(
        user_id=USER_ID,
        thread_id=THREAD_ID,
        retriever=retriever,
        conversation_context="[]",
    )

    async def search_twice() -> tuple[list[Passage], list[Passage]]:
        return await asyncio.gather(
            deps.search_filings("Revenue", limit=MAX_RESULTS),
            deps.search_filings(" Revenue ", limit=MAX_RESULTS),
        )

    results = asyncio.run(search_twice())

    assert retriever.search_calls == 1
    assert results[0] == results[1]


def _passage() -> Passage:
    return Passage(
        chunk_id=CHUNK_ID,
        document_id=THREAD_ID,
        chunk_index=0,
        content="The filing reported revenue.",
        section="Revenue",
        source_start=None,
        source_end=None,
        chunk_metadata={"page_references": []},
        document_metadata={},
        ticker="GOOGL",
        company_name="Alphabet Inc.",
        fiscal_year=2025,
        filing_type="10-K",
        filing_date=date(2026, 2, 5),
        accession_number="0001652044-26-000012",
        source_url="https://example.test/filing",
    )
