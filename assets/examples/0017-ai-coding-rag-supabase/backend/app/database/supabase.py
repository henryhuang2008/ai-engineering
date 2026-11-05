from supabase import Client, ClientOptions, create_client

from app.config import settings


def _require_supabase_url() -> str:
    if not settings.supabase_url:
        raise RuntimeError("SUPABASE_URL is required to create a Supabase client.")
    return settings.supabase_url


def create_user_client(access_token: str) -> Client:
    token = access_token.strip()
    if not token:
        raise ValueError("A non-empty Supabase access token is required.")
    if not settings.supabase_anon_key:
        raise RuntimeError("SUPABASE_ANON_KEY is required to create a user-scoped client.")

    return create_client(
        _require_supabase_url(),
        settings.supabase_anon_key.get_secret_value(),
        options=ClientOptions(headers={"Authorization": f"Bearer {token}"}),
    )


def create_service_role_client() -> Client:
    if not settings.supabase_service_role_key:
        raise RuntimeError("SUPABASE_SERVICE_ROLE_KEY is required to create a service-role client.")

    return create_client(
        _require_supabase_url(),
        settings.supabase_service_role_key.get_secret_value(),
    )
