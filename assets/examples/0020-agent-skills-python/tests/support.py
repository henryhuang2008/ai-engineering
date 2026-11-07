from __future__ import annotations

from pathlib import Path
from typing import Any

from app.config import Settings

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def make_settings(**overrides: Any) -> Settings:
    values = dict(
        api_key="test-key",
        base_url="https://example.invalid/v1",
        model="test-model",
        library=PROJECT_ROOT / "skills",
        require_loaded=True,
    )
    values.update(overrides)
    return Settings(**values)


def csv_path() -> Path:
    return (PROJECT_ROOT / "data" / "sales.csv").resolve()


def script_path(skill: str, script: str) -> Path:
    return PROJECT_ROOT / "skills" / skill / "scripts" / script


def write_skill(directory: Path, name: str, *, description: str, body: str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {description}\n---\n\n{body}\n",
        encoding="utf-8",
    )
    return directory
