from types import SimpleNamespace
from unittest.mock import sentinel

import pytest
from pydantic import SecretStr
from supabase import ClientOptions

import app.database.supabase as supabase_db


@pytest.fixture
def configured_supabase(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        supabase_db,
        "settings",
        SimpleNamespace(
            supabase_url="https://example.supabase.co",
            supabase_anon_key=SecretStr("anon-test-key"),
            supabase_service_role_key=SecretStr("service-test-key"),
        ),
    )


def test_user_client_uses_anon_key_and_access_token(
    configured_supabase: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, str, ClientOptions | None]] = []

    def fake_create_client(
        url: str,
        key: str,
        options: ClientOptions | None = None,
    ) -> object:
        calls.append((url, key, options))
        return sentinel.client

    monkeypatch.setattr(supabase_db, "create_client", fake_create_client)

    client = supabase_db.create_user_client("  user-access-token  ")

    assert client is sentinel.client
    assert calls[0][0:2] == ("https://example.supabase.co", "anon-test-key")
    assert calls[0][2] is not None
    assert calls[0][2].headers["Authorization"] == "Bearer user-access-token"


def test_service_role_client_uses_service_role_key(
    configured_supabase: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, str]] = []

    def fake_create_client(url: str, key: str) -> object:
        calls.append((url, key))
        return sentinel.client

    monkeypatch.setattr(supabase_db, "create_client", fake_create_client)

    client = supabase_db.create_service_role_client()

    assert client is sentinel.client
    assert calls == [("https://example.supabase.co", "service-test-key")]


def test_client_creation_fails_for_missing_configuration(
    configured_supabase: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(supabase_db.settings, "supabase_anon_key", None)

    with pytest.raises(RuntimeError, match="SUPABASE_ANON_KEY"):
        supabase_db.create_user_client("user-access-token")


def test_user_client_rejects_empty_access_token(configured_supabase: None) -> None:
    with pytest.raises(ValueError, match="access token"):
        supabase_db.create_user_client("  ")
