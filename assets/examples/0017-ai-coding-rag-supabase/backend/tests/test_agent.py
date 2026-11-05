import asyncio
from datetime import date
from types import SimpleNamespace
from uuid import UUID

from pydantic_ai.models.test import TestModel

from app.assistant.agent import create_document_agent
from app.assistant.evidence import (
    MAX_EVIDENCE_CONTEXT_LENGTH,
    MAX_EVIDENCE_PASSAGE_LENGTH,
    to_evidence_passages,
)
from app.retrieval.models import Passage

CHUNK_ID = UUID("a61b2c08-8c8d-4c54-9dbb-f9828eb04820")
GENERATING_ANSWER = "Generating an answer and verifying its citations..."


class FakeRetriever:
    async def search_filings(
        self,
        query: str,
        filters: object,
        *,
        limit: int,
        report_progress: object = None,
    ) -> list[object]:
        if callable(report_progress):
            report_progress("Fetching passage text and filing metadata...")
        return []

    async def read_chunk(self, chunk_id: UUID) -> None:
        return None

    async def read_surrounding_chunks(self, chunk_id: UUID, *, window: int) -> None:
        return None


class FakeDeps:
    def __init__(self, progress: list[str]) -> None:
        self.report_progress = progress.append
        self.retriever = FakeRetriever()

    def remember(self, passage: object) -> None:
        return None

    def remember_window(self, window: object) -> None:
        return None

    async def search_filings(self, query: str, filters: object, *, limit: int) -> list[object]:
        return []


def test_agent_registers_only_the_three_bounded_retrieval_tools() -> None:
    agent = create_document_agent(TestModel())

    assert set(agent._function_toolset.tools) == {
        "search_filings",
        "read_chunk",
        "read_surrounding_chunks",
    }


def test_retrieval_tools_switch_progress_back_to_answer_generation() -> None:
    agent = create_document_agent(TestModel())
    tools = agent._function_toolset.tools
    progress: list[str] = []
    context = SimpleNamespace(deps=FakeDeps(progress))

    calls = (
        (tools["search_filings"].function, {"query": "revenue"}),
        (tools["read_chunk"].function, {"chunk_id": CHUNK_ID}),
        (tools["read_surrounding_chunks"].function, {"chunk_id": CHUNK_ID, "window": 0}),
    )
    for tool, kwargs in calls:
        progress.clear()
        asyncio.run(tool(context, **kwargs))
        assert progress[-1] == GENERATING_ANSWER


def test_tool_evidence_strips_large_metadata_and_bounds_content() -> None:
    passages = [
        _passage(content=str(index) * (MAX_EVIDENCE_PASSAGE_LENGTH + 100))
        for index in range(10)
    ]

    evidence = to_evidence_passages(passages)

    assert sum(len(passage.content) for passage in evidence) == MAX_EVIDENCE_CONTEXT_LENGTH
    assert all(len(passage.content) <= MAX_EVIDENCE_PASSAGE_LENGTH for passage in evidence)
    assert evidence[0].page_references == [12]
    assert "chunk_metadata" not in evidence[0].model_dump()


def _passage(*, content: str) -> Passage:
    return Passage(
        chunk_id=CHUNK_ID,
        document_id=UUID("a61b2c08-8c8d-4c54-9dbb-f9828eb04818"),
        chunk_index=0,
        content=content,
        section="Revenue",
        source_start=None,
        source_end=None,
        chunk_metadata={"page_references": [12], "docling_metadata": {"large": "x" * 50_000}},
        document_metadata={"large": "x" * 50_000},
        ticker="GOOGL",
        company_name="Alphabet Inc.",
        fiscal_year=2025,
        filing_type="10-K",
        filing_date=date(2026, 2, 5),
        accession_number="0001652044-26-000012",
        source_url="https://example.test/filing",
    )
