"""The runtime: a Pydantic AI agent whose skills are deferred capabilities.

Three things are load-bearing and all three are library behavior, not ours:

* the catalog is one line (`name: description`) per skill in the instructions;
* loading a skill injects its body as a capability context block;
* `read_skill_resource` and `run_skill_script` are always visible but refuse a
  skill the model has not loaded.

This module adds no caching and no custom selection. It exists to make the
boundary visible and to fail with a useful message when the platform cannot
build the capability.
"""

from __future__ import annotations

from typing import Any

from app.config import Settings

SYSTEM_INSTRUCTIONS = """You answer questions by using the skills in the catalog.

Load a skill before you use its files or scripts. When a skill ships a script
that computes an answer, run the script instead of estimating the number. If a
skill tells you to read a reference before answering, read it.

Working directory: {root}
Skill scripts run with their own scripts/ directory as the working directory,
so turn every relative path in the question into an absolute path under the
working directory before passing it to a script.
"""


def system_instructions() -> str:
    """The system prompt with the process working directory filled in."""
    from pathlib import Path

    return SYSTEM_INSTRUCTIONS.replace("{root}", str(Path.cwd()))


class RuntimeUnavailable(RuntimeError):
    """The runtime cannot be constructed on this platform or install."""


def build_capability(settings: Settings) -> Any:
    try:
        from pydantic_ai_skills import SkillsCapability
    except ImportError as error:  # pragma: no cover - dependency is declared
        raise RuntimeUnavailable(f"pydantic-ai-skills is not installed: {error}") from error

    try:
        return SkillsCapability(
            settings.library,
            require_loaded=settings.require_loaded,
        )
    except NotImplementedError as error:
        # pydantic-ai-harness >= 0.52 builds a POSIX-only LocalWorkspaceBackend
        # when it discovers skills per run. The symptom on Windows is this
        # NotImplementedError at construction, before any model call.
        raise RuntimeUnavailable(
            "pydantic-ai-harness >= 0.52 builds a POSIX-only LocalWorkspaceBackend "
            "when discovering skills, so SkillsCapability cannot be constructed on "
            "this platform. This project pins harness < 0.52; see "
            "docs/runtime-notes.md."
        ) from error


def build_model(settings: Settings) -> Any:
    from pydantic_ai.models.openai import OpenAIChatModel
    from pydantic_ai.providers.openai import OpenAIProvider

    api_key, base_url, model_name = settings.require_llm()
    return OpenAIChatModel(
        model_name,
        provider=OpenAIProvider(base_url=base_url, api_key=api_key),
    )


def build_agent(settings: Settings, *, model: Any | None = None) -> Any:
    from pydantic_ai import Agent

    capability = build_capability(settings)
    return Agent(
        model or build_model(settings),
        instructions=system_instructions(),
        capabilities=[capability],
    )


def ask(settings: Settings, question: str) -> str:
    agent = build_agent(settings)
    return str(agent.run_sync(question).output)


def probe(settings: Settings) -> dict[str, Any]:
    """Build the capability, then capture what one run would expose.

    Uses a scripted model so it needs no provider key: this is a structural
    check (which tools exist, what the catalog says), not a quality check.
    """
    from pydantic_ai import Agent
    from pydantic_ai.messages import ModelResponse, TextPart
    from pydantic_ai.models.function import AgentInfo, FunctionModel

    captured: dict[str, Any] = {}

    def reply(messages: Any, info: AgentInfo) -> ModelResponse:
        captured["tools"] = [tool.name for tool in info.function_tools]
        captured["instructions"] = str(info.instructions)
        return ModelResponse(parts=[TextPart("ok")])

    agent = Agent(
        FunctionModel(reply),
        instructions=SYSTEM_INSTRUCTIONS,
        capabilities=[build_capability(settings)],
    )
    agent.run_sync("tool discovery")
    return captured
