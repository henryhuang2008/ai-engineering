from collections.abc import Callable
from types import SimpleNamespace
from uuid import UUID

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

import app.auth.dependencies as auth_dependencies
from app.main import app

client = TestClient(app)
USER_ID = UUID("a61b2c08-8c8d-4c54-9dbb-f9828eb04818")


@pytest.fixture(autouse=True)
def auth_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        auth_dependencies,
        "settings",
        SimpleNamespace(
            supabase_url="https://example.supabase.co/",
            supabase_anon_key=SecretStr("test-anon-key"),
        ),
    )


def mock_auth_response(
    monkeypatch: pytest.MonkeyPatch,
    handler: Callable[[httpx.Request], httpx.Response],
) -> None:
    async_client = httpx.AsyncClient

    def create_client(*, timeout: float) -> httpx.AsyncClient:
        return async_client(
            transport=httpx.MockTransport(handler),
            timeout=timeout,
        )

    monkeypatch.setattr(auth_dependencies.httpx, "AsyncClient", create_client)


def test_current_user_rejects_missing_or_malformed_bearer_token() -> None:
    for headers in ({}, {"Authorization": "Basic credentials"}):
        response = client.get("/auth/me", headers=headers)

        assert response.status_code == 401
        assert response.headers["www-authenticate"] == "Bearer"


def test_current_user_validates_token_with_supabase(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://example.supabase.co/auth/v1/user"
        assert request.headers["apikey"] == "test-anon-key"
        assert request.headers["authorization"] == "Bearer valid-user-token"
        return httpx.Response(
            200,
            json={"id": str(USER_ID), "email": "analyst@example.com"},
        )

    mock_auth_response(monkeypatch, handler)

    response = client.get(
        "/auth/me",
        headers={"Authorization": "Bearer valid-user-token"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "id": str(USER_ID),
        "email": "analyst@example.com",
    }


def test_current_user_rejects_invalid_supabase_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mock_auth_response(
        monkeypatch,
        lambda _: httpx.Response(401, json={"message": "invalid token"}),
    )

    response = client.get(
        "/auth/me",
        headers={"Authorization": "Bearer expired-token"},
    )

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_current_user_reports_supabase_outage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mock_auth_response(
        monkeypatch,
        lambda _: httpx.Response(503, json={"message": "unavailable"}),
    )

    response = client.get(
        "/auth/me",
        headers={"Authorization": "Bearer valid-user-token"},
    )

    assert response.status_code == 502
