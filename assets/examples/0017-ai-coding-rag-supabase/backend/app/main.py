from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated, Literal

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.api.chat import router as chat_router
from app.assistant.agent import create_chat_runtime
from app.auth.dependencies import AuthenticatedUser, get_current_user
from app.config import settings


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"


def create_app() -> FastAPI:
    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        runtime = create_chat_runtime(settings)
        application.state.chat_runtime = runtime
        try:
            yield
        finally:
            await runtime.aclose()

    application = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        lifespan=lifespan,
    )
    application.include_router(chat_router)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
    )

    @application.get("/health", response_model=HealthResponse, tags=["system"])
    async def health() -> HealthResponse:
        return HealthResponse()

    @application.get("/auth/me", response_model=AuthenticatedUser, tags=["auth"])
    async def current_user(
        user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    ) -> AuthenticatedUser:
        return user

    return application


app = create_app()

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
