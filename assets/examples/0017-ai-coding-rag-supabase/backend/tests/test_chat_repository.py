import asyncio
import json
from uuid import UUID

import httpx
from pydantic import SecretStr

from app.assistant.outputs import CitationSource
from app.auth.dependencies import AuthenticatedSession, AuthenticatedUser
from app.database.chats import ChatRepository

USER_ID = UUID("a61b2c08-8c8d-4c54-9dbb-f9828eb04818")
THREAD_ID = UUID("6dc1c1fa-1429-4c8c-92b0-1cd9bf1f95b7")
ASSISTANT_ID = UUID("a61b2c08-8c8d-4c54-9dbb-f9828eb04819")
CHUNK_ID = UUID("a61b2c08-8c8d-4c54-9dbb-f9828eb04820")
SESSION = AuthenticatedSession(
    user=AuthenticatedUser(id=USER_ID, email="analyst@example.com"),
    access_token=SecretStr("test-user-token"),
)
CITATION = CitationSource(
    citation_index=1,
    chunk_id=CHUNK_ID,
    ticker="GOOGL",
    company_name="Alphabet Inc.",
    filing_type="10-K",
    filing_date="2026-02-05",
    fiscal_year=2025,
    accession_number="0001652044-26-000012",
    source_url="https://example.test/filing",
    section="Revenue",
    page_references=[12],
    passage="Exact passage.",
)


def test_save_turn_uses_authenticated_atomic_rpc_with_citations() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=str(ASSISTANT_ID))

    async def save_turn() -> UUID:
        async with httpx.AsyncClient(
            base_url="https://example.supabase.co/rest/v1/",
            transport=httpx.MockTransport(handler),
            headers={"Authorization": "Bearer test-user-token"},
        ) as client:
            repository = ChatRepository(client, SESSION)
            return await repository.save_turn(
                THREAD_ID,
                "Question",
                "Answer [1]",
                [CITATION],
            )

    assistant_id = asyncio.run(save_turn())

    assert assistant_id == ASSISTANT_ID
    assert len(requests) == 1
    assert requests[0].url.path.endswith("/rpc/save_chat_turn")
    assert requests[0].headers["authorization"] == "Bearer test-user-token"
    assert json.loads(requests[0].read()) == {
        "p_thread_id": str(THREAD_ID),
        "p_user_content": "Question",
        "p_assistant_content": "Answer [1]",
        "p_citations": [{"chunk_id": str(CHUNK_ID), "quote": None}],
    }


def test_get_messages_hydrates_persisted_citation_sources() -> None:
    row = {
        "id": str(ASSISTANT_ID),
        "role": "assistant",
        "content": "Answer [1]",
        "created_at": "2026-11-05T10:00:00Z",
        "message_citations": [
            {
                "citation_index": 0,
                "chunk_id": str(CHUNK_ID),
                "quote": None,
                "document_chunks": {
                    "content": "Exact passage.",
                    "section": "Revenue",
                    "metadata": {"page_references": [12]},
                    "source_documents": {
                        "ticker": "GOOGL",
                        "company_name": "Alphabet Inc.",
                        "filing_type": "10-K",
                        "filing_date": "2026-02-05",
                        "fiscal_year": 2025,
                        "accession_number": "0001652044-26-000012",
                        "source_url": "https://example.test/filing",
                    },
                },
            }
        ],
    }

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["limit"] == "30"
        assert "message_citations(" in request.url.params["select"]
        return httpx.Response(200, json=[row])

    async def get_messages() -> list[dict[str, object]]:
        async with httpx.AsyncClient(
            base_url="https://example.supabase.co/rest/v1/",
            transport=httpx.MockTransport(handler),
            headers={"Authorization": "Bearer test-user-token"},
        ) as client:
            return await ChatRepository(client, SESSION).get_messages(THREAD_ID)

    messages = asyncio.run(get_messages())

    assert len(messages) == 1
    citation = messages[0]["citations"][0]
    assert citation["citation_index"] == 1
    assert citation["page_references"] == [12]
    assert citation["passage"] == "Exact passage."


def test_get_recent_context_excludes_citation_payloads() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["select"] == "role,content"
        assert request.url.params["limit"] == "12"
        return httpx.Response(
            200,
            json=[{"role": "assistant", "content": "Previous answer"}],
        )

    async def get_context() -> list[dict[str, object]]:
        async with httpx.AsyncClient(
            base_url="https://example.supabase.co/rest/v1/",
            transport=httpx.MockTransport(handler),
            headers={"Authorization": "Bearer test-user-token"},
        ) as client:
            return await ChatRepository(client, SESSION).get_recent_context(THREAD_ID)

    assert asyncio.run(get_context()) == [{"role": "assistant", "content": "Previous answer"}]
