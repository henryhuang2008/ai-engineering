from typing import Annotated
from uuid import UUID

import httpx
from fastapi import Depends, Header, HTTPException, status
from pydantic import BaseModel, SecretStr, ValidationError

from app.config import settings


class AuthenticatedUser(BaseModel):
    id: UUID
    email: str | None = None


class AuthenticatedSession(BaseModel):
    user: AuthenticatedUser
    access_token: SecretStr


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Missing or invalid bearer token.",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_authenticated_session(
    authorization: str | None = Header(default=None),
) -> AuthenticatedSession:
    scheme, separator, access_token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not separator or not access_token.strip():
        raise _unauthorized()

    if not settings.supabase_url or not settings.supabase_anon_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Supabase authentication is not configured.",
        )

    headers = {
        "apikey": settings.supabase_anon_key.get_secret_value(),
        "Authorization": f"Bearer {access_token.strip()}",
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{settings.supabase_url.rstrip('/')}/auth/v1/user",
                headers=headers,
            )
    except httpx.TimeoutException as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Supabase authentication timed out.",
        ) from exc
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Supabase authentication is unavailable.",
        ) from exc

    if response.status_code in {
        status.HTTP_400_BAD_REQUEST,
        status.HTTP_401_UNAUTHORIZED,
        status.HTTP_403_FORBIDDEN,
    }:
        raise _unauthorized()
    if response.is_error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Supabase authentication returned an error.",
        )

    try:
        payload = response.json()
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Supabase authentication returned invalid JSON.",
        ) from exc

    try:
        user = AuthenticatedUser.model_validate(payload)
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Supabase authentication returned an invalid user response.",
        ) from exc
    return AuthenticatedSession(
        user=user,
        access_token=SecretStr(access_token.strip()),
    )


async def get_current_user(
    session: Annotated[AuthenticatedSession, Depends(get_authenticated_session)],
) -> AuthenticatedUser:
    return session.user
