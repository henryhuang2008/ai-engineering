"""Read a skill library: SKILL.md frontmatter, body, and bundled files.

Pure stdlib plus PyYAML. Nothing here imports the agent runtime, so linting and
cataloguing work even when the runtime cannot be constructed (see
docs/runtime-notes.md).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

NAME_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
NAME_MAX = 64
DESCRIPTION_MAX = 1024


class SkillError(ValueError):
    """A skill on disk does not meet the format contract."""


@dataclass(frozen=True)
class Skill:
    name: str
    description: str
    path: Path
    body: str
    frontmatter: dict[str, object] = field(default_factory=dict)

    @property
    def directory_name(self) -> str:
        return self.path.name

    @property
    def body_lines(self) -> int:
        return len(self.body.splitlines())

    @property
    def resources(self) -> list[Path]:
        return sorted(path for path in self.path.rglob("*") if path.is_file())

    def relative_files(self) -> list[str]:
        return sorted(
            str(path.relative_to(self.path)).replace("\\", "/")
            for path in self.resources
            if path.name != "SKILL.md"
        )


def split_frontmatter(text: str) -> tuple[dict[str, object], str]:
    """Split `---` YAML frontmatter from the Markdown body."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise SkillError("SKILL.md must start with a --- frontmatter block")

    for index in range(1, len(lines)):
        if lines[index].strip() in {"---", "..."}:
            raw = "\n".join(lines[1:index])
            body = "\n".join(lines[index + 1 :]).lstrip("\n")
            try:
                parsed = yaml.safe_load(raw) or {}
            except yaml.YAMLError as error:
                raise SkillError(f"frontmatter is not valid YAML: {error}") from error
            if not isinstance(parsed, dict):
                raise SkillError("frontmatter must be a mapping of fields")
            return {str(key): value for key, value in parsed.items()}, body

    raise SkillError("frontmatter block is not closed with ---")


def load_skill(path: Path) -> Skill:
    """Parse one skill package. `path` is the directory holding SKILL.md."""
    skill_file = path / "SKILL.md"
    if not skill_file.is_file():
        raise SkillError(f"{path} has no SKILL.md")

    frontmatter, body = split_frontmatter(skill_file.read_text(encoding="utf-8"))

    name = frontmatter.get("name")
    if not isinstance(name, str) or not name.strip():
        raise SkillError("frontmatter field 'name' is required and must be a string")
    name = name.strip()
    if not NAME_PATTERN.match(name):
        raise SkillError(
            f"name {name!r} must be lowercase letters, digits and single hyphens"
        )
    if len(name) > NAME_MAX:
        raise SkillError(f"name is {len(name)} characters; the limit is {NAME_MAX}")

    description = frontmatter.get("description")
    if not isinstance(description, str) or not description.strip():
        raise SkillError("frontmatter field 'description' is required and must be a string")
    description = " ".join(description.split())
    if len(description) > DESCRIPTION_MAX:
        raise SkillError(
            f"description is {len(description)} characters; the limit is {DESCRIPTION_MAX}"
        )

    return Skill(
        name=name,
        description=description,
        path=path,
        body=body,
        frontmatter=frontmatter,
    )


def discover(library: Path) -> list[Skill]:
    """Load every immediate child of `library` that contains a SKILL.md.

    Immediate children only: nesting is not searched, which is the contract both
    langchain-skills and pydantic-ai-skills follow. A directory without SKILL.md
    is skipped rather than guessed at.
    """
    if not library.is_dir():
        raise SkillError(f"skill library not found: {library}")

    skills: list[Skill] = []
    for child in sorted(library.iterdir()):
        if child.is_dir() and (child / "SKILL.md").is_file():
            skills.append(load_skill(child))
    return skills


def catalog_lines(skills: list[Skill]) -> list[str]:
    """The always-on level-1 catalog: one name and description per skill."""
    return [f"- {skill.name}: {skill.description}" for skill in skills]


def estimate_tokens(text: str) -> int:
    """Rough token estimate for budgeting: four characters per token.

    Deliberately not a tokenizer: the point is a stable number you can compare
    across edits, not a billing figure.
    """
    return max(1, len(text) // 4)
