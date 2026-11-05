from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated, Any
from uuid import UUID

import httpx
from fastapi import Depends, HTTPException, status

from app.assistant.outputs import CitationSource
from app.auth.dependencies import AuthenticatedSession, get_authenticated_session
from app.config import settings

CHAT_HISTORY_LIMIT = 30
CHAT_CONTEXT_LIMIT = 12


class ChatRepository:
    def __init__(
        self,
        client: httpx.AsyncClient,
        session: AuthenticatedSession,
    ) -> None:
        self._client = client
        self._session = session
        self._user_id = session.user.id

    async def create_thread(self, title: str) -> dict[str, Any]:
        email = self._session.user.email
        if not email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="An email address is required to create a chat thread.",
            )

        await self._request(
            "POST",
            "users",
            params={"on_conflict": "id"},
            headers={"Prefer": "resolution=merge-duplicates,return=minimal"},
            json={"id": str(self._user_id), "email": email},
        )
        rows = await self._request(
            "POST",
            "chat_threads",
            params={"select": "id,title,created_at,updated_at"},
            headers={"Prefer": "return=representation"},
            json={"user_id": str(self._user_id), "title": title},
        )
        return self._first_row(rows)

    async def list_threads(self) -> list[dict[str, Any]]:
        rows = await self._request(
            "GET",
            "chat_threads",
            params={
                "select": "id,title,created_at,updated_at",
                "order": "updated_at.desc,created_at.desc",
                "limit": "100",
            },
        )
        if not isinstance(rows, list):
            raise self._invalid_response()
        return rows

    async def get_thread(self, thread_id: UUID) -> dict[str, Any]:
        rows = await self._request(
            "GET",
            "chat_threads",
            params={
                "id": f"eq.{thread_id}",
                "select": "id,title,created_at,updated_at",
                "limit": "1",
            },
        )
        thread = self._first_optional_row(rows)
        if thread is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Chat thread not found.",
            )
        return thread

    async def get_messages(self, thread_id: UUID) -> list[dict[str, Any]]:
        rows = await self._request(
            "GET",
            "chat_messages",
            params={
                "thread_id": f"eq.{thread_id}",
                "select": (
                    "id,role,content,created_at,message_citations("
                    "citation_index,quote,chunk_id,document_chunks("
                    "content,section,metadata,source_documents("
                    "ticker,company_name,filing_type,filing_date,fiscal_year,"
                    "accession_number,source_url)))"
                ),
                "order": "created_at.desc,id.desc",
                "limit": str(CHAT_HISTORY_LIMIT),
            },
        )
        if not isinstance(rows, list):
            raise self._invalid_response()
        messages = [self._include_citations(row) for row in rows]
        return list(reversed(messages))

    async def get_recent_context(self, thread_id: UUID) -> list[dict[str, Any]]:
        rows = await self._request(
            "GET",
            "chat_messages",
            params={
                "thread_id": f"eq.{thread_id}",
                "select": "role,content",
                "order": "created_at.desc,id.desc",
                "limit": str(CHAT_CONTEXT_LIMIT),
            },
        )
        if not isinstance(rows, list) or any(
            not isinstance(row, dict)
            or row.get("role") not in {"user", "assistant"}
            or not isinstance(row.get("content"), str)
            for row in rows
        ):
            raise self._invalid_response()
        return list(reversed(rows))

    async def save_turn(
        self,
        thread_id: UUID,
        user_content: str,
        assistant_content: str,
        citations: list[CitationSource],
    ) -> UUID:
        result = await self._request(
            "POST",
            "rpc/save_chat_turn",
            headers={"Prefer": "return=representation"},
            json={
                "p_thread_id": str(thread_id),
                "p_user_content": user_content,
                "p_assistant_content": assistant_content,
                "p_citations": [
                    {"chunk_id": str(citation.chunk_id), "quote": citation.quote}
                    for citation in citations
                ],
            },
        )
        try:
            return UUID(result)
        except (TypeError, ValueError) as exc:
            raise self._invalid_response() from exc

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
        json: Any = None,
    ) -> Any:
        try:
            response = await self._client.request(
                method,
                path,
                params=params,
                headers=headers,
                json=json,
            )
        except httpx.TimeoutException as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Supabase database request timed out.",
            ) from exc
        except httpx.RequestError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Supabase database is unavailable.",
            ) from exc

        if response.status_code in {
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        }:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Supabase rejected the authenticated session.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        if response.is_error:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Supabase database request failed.",
            )
        if response.status_code == status.HTTP_204_NO_CONTENT or not response.content:
            return None

        try:
            return response.json()
        except ValueError as exc:
            raise self._invalid_response() from exc

    @staticmethod
    def _first_row(value: Any) -> dict[str, Any]:
        row = ChatRepository._first_optional_row(value)
        if row is None:
            raise ChatRepository._invalid_response()
        return row

    @staticmethod
    def _first_optional_row(value: Any) -> dict[str, Any] | None:
        if not isinstance(value, list):
            raise ChatRepository._invalid_response()
        if not value:
            return None
        row = value[0]
        if not isinstance(row, dict):
            raise ChatRepository._invalid_response()
        return row

    @staticmethod
    def _invalid_response() -> HTTPException:
        return HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Supabase returned an invalid database response.",
        )

    @staticmethod
    def _include_citations(message: Any) -> dict[str, Any]:
        if not isinstance(message, dict):
            raise ChatRepository._invalid_response()
        raw_citations = message.get("message_citations", [])
        if not isinstance(raw_citations, list):
            raise ChatRepository._invalid_response()
        if any(
            not isinstance(citation, dict)
            or not isinstance(citation.get("citation_index"), int)
            or isinstance(citation.get("citation_index"), bool)
            for citation in raw_citations
        ):
            raise ChatRepository._invalid_response()
        citations = []
        for raw in sorted(raw_citations, key=lambda item: item["citation_index"]):
            try:
                citations.append(_citation_from_row(raw))
            except (KeyError, TypeError, ValueError) as exc:
                raise ChatRepository._invalid_response() from exc
        return {**message, "citations": citations}


def _citation_from_row(row: Any) -> dict[str, Any]:
    if not isinstance(row, dict):
        raise ValueError("Invalid citation row.")
    chunk = row.get("document_chunks")
    if not isinstance(chunk, dict):
        raise ValueError("Missing cited chunk.")
    document = chunk.get("source_documents")
    if not isinstance(document, dict):
        raise ValueError("Missing citation source document.")
    metadata = chunk.get("metadata")
    if not isinstance(metadata, dict):
        raise ValueError("Invalid chunk metadata.")
    raw_pages = metadata.get("page_references", [])
    page_references = (
        [
            page
            for page in raw_pages
            if isinstance(page, int) and not isinstance(page, bool) and page > 0
        ]
        if isinstance(raw_pages, list)
        else []
    )

    source = CitationSource(
        citation_index=row["citation_index"] + 1,
        chunk_id=row["chunk_id"],
        quote=row.get("quote"),
        ticker=document["ticker"],
        company_name=document["company_name"],
        filing_type=document["filing_type"],
        filing_date=document["filing_date"],
        fiscal_year=document["fiscal_year"],
        accession_number=document["accession_number"],
        source_url=document["source_url"],
        section=chunk.get("section"),
        page_references=page_references,
        passage=chunk["content"],
    )
    return source.model_dump(mode="json")


async def get_chat_repository(
    session: Annotated[AuthenticatedSession, Depends(get_authenticated_session)],
) -> AsyncIterator[ChatRepository]:
    if not settings.supabase_url or not settings.supabase_anon_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Supabase database access is not configured.",
        )

    async with httpx.AsyncClient(
        base_url=f"{settings.supabase_url.rstrip('/')}/rest/v1/",
        headers={
            "apikey": settings.supabase_anon_key.get_secret_value(),
            "Authorization": f"Bearer {session.access_token.get_secret_value()}",
        },
        timeout=15.0,
    ) as client:
        yield ChatRepository(client, session)
