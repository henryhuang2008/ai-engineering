from typing import Annotated

from fastapi import Depends, HTTPException, Request, status

from app.chat.orchestrator import ChatOrchestrator


def get_chat_orchestrator(request: Request) -> ChatOrchestrator:
    runtime = getattr(request.app.state, "chat_runtime", None)
    if runtime is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The chat agent is not configured.",
        )
    return runtime.orchestrator


ChatOrchestratorDependency = Annotated[ChatOrchestrator, Depends(get_chat_orchestrator)]
