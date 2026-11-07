from __future__ import annotations

from typing import Any

from pydantic_ai import Agent
from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from app.runtime import build_capability, probe, system_instructions
from tests.support import csv_path, make_settings


def run_calls(settings: Any, calls: list[tuple[str, dict[str, Any]]]) -> tuple[list[tuple[str, str]], list[str]]:
    """Run the agent through scripted tool calls; return tool results and prompt text."""
    pending = list(calls)
    results: list[tuple[str, str]] = []
    instructions: list[str] = []

    def model_fn(messages: Any, info: AgentInfo) -> ModelResponse:
        instructions.append(str(info.instructions))
        for message in messages:
            for part in getattr(message, "parts", []):
                if type(part).__name__ == "ToolReturnPart":
                    entry = (part.tool_name, str(part.content))
                    if entry not in results:
                        results.append(entry)
                elif type(part).__name__ == "UserPromptPart":
                    # A loaded skill arrives as a capability context block in the
                    # conversation, not in the system instructions.
                    prompt = str(part.content)
                    if "capability:" in prompt and prompt not in instructions:
                        instructions.append(prompt)
        if not pending:
            return ModelResponse(parts=[TextPart("done")])
        name, args = pending.pop(0)
        return ModelResponse(parts=[ToolCallPart(name, args)])

    agent = Agent(
        FunctionModel(model_fn),
        instructions=system_instructions(),
        capabilities=[build_capability(settings)],
    )
    agent.run_sync("test")
    return results, instructions


def test_the_catalog_lists_both_skills_before_any_load() -> None:
    captured = probe(make_settings())

    assert captured["tools"] == ["load_capability", "read_skill_resource", "run_skill_script"]
    assert "- csv-insights:" in captured["instructions"]
    assert "- release-notes:" in captured["instructions"]
    # Level 1 is names and descriptions only: no skill body has been injected.
    assert "# CSV insights" not in captured["instructions"]


def test_files_are_refused_until_the_skill_is_loaded() -> None:
    settings = make_settings()
    results, _ = run_calls(
        settings,
        [("read_skill_resource", {"skill_name": "csv-insights", "resource_name": "references/metrics.md"})],
    )

    assert "is not loaded" in results[0][1]
    assert "load_capability" in results[0][1]


def test_loading_injects_the_body_and_resolves_skill_dir() -> None:
    settings = make_settings()
    _, instructions = run_calls(settings, [("load_capability", {"id": "csv-insights"})])

    loaded = instructions[-1]
    assert "# CSV insights" in loaded
    assert "${SKILL_DIR}" not in loaded
    assert str(settings.library / "csv-insights") in loaded


def test_resource_reads_after_loading() -> None:
    settings = make_settings()
    results, _ = run_calls(
        settings,
        [
            ("load_capability", {"id": "csv-insights"}),
            ("read_skill_resource", {"skill_name": "csv-insights", "resource_name": "metrics"}),
        ],
    )

    assert "Metric definitions" in results[-1][1]
    assert "skew warning" in results[-1][1].lower()


def test_script_runs_through_the_bundled_executor() -> None:
    settings = make_settings()
    results, _ = run_calls(
        settings,
        [
            ("load_capability", {"id": "csv-insights"}),
            (
                "run_skill_script",
                {
                    "skill_name": "csv-insights",
                    "script_name": "profile.py",
                    "args": {"csv": str(csv_path())},
                },
            ),
        ],
    )

    script_output = results[-1][1]
    assert '"rows": 10' in script_output
    assert script_output.count("Stderr") == 0


def test_require_loaded_false_reaches_files_without_a_load() -> None:
    settings = make_settings(require_loaded=False)
    results, _ = run_calls(
        settings,
        [("read_skill_resource", {"skill_name": "release-notes", "resource_name": "references/style.md"})],
    )

    assert "Release note style" in results[-1][1]
