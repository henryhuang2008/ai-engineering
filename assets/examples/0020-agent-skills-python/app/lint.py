"""Lint a skill library against the Agent Skills format and house rules.

The rules are a port of langchain-ai/langchain-skills `scripts/lint_skills.py`,
which layers its own checks on top of the Agent Skills spec. The block/warn
split and the numeric gates are that repository's; the description checks are
this example's addition, because a description is the only part of a skill the
model sees before deciding to load it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from app.skills import (
    DESCRIPTION_MAX,
    NAME_MAX,
    NAME_PATTERN,
    Skill,
    SkillError,
    discover,
    estimate_tokens,
    split_frontmatter,
)

BLOCK = "BLOCK"
WARN = "WARN"

BODY_LINE_WARN = 500
BODY_LINE_BLOCK = 600
ON_INVOKE_TOKEN_WARN = 6000
LANGUAGE_SPLIT_WARN = 150
DESCRIPTION_BUDGET_WARN = 400

ALLOWED_MODELS = {
    "claude-sonnet-5",
    "claude-opus-5",
    "claude-fable-5-1",
    "claude-haiku-4-5-20251001",
    "gpt-5.5",
}

MODEL_PATTERN = re.compile(r"\b(claude-[a-z0-9.\-]*\d[a-z0-9.\-]*|gpt-[0-9][a-z0-9.\-]*)")
PIPE_TO_SHELL = re.compile(r"curl[^\n|]*\|\s*(?:sudo\s+)?(?:sh|bash)\b")
MARKDOWN_LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
FENCE = re.compile(r"^```([A-Za-z0-9_+-]*)\s*$")
TRIGGER_WORDS = ("use when", "use this", "when the user", "when you")

PYTHON_LANGS = {"python", "py"}
TS_LANGS = {"typescript", "ts", "javascript", "js", "tsx", "jsx"}


@dataclass(frozen=True)
class Finding:
    severity: str
    rule: str
    path: Path
    line: int
    message: str

    def format(self, root: Path) -> str:
        try:
            location = self.path.resolve().relative_to(root.resolve())
        except ValueError:
            location = self.path
        return f"{self.severity:<5} {self.rule:<20} {location}:{self.line}  {self.message}"


def _inline_language_lines(lines: list[str]) -> dict[str, int]:
    """Count fenced lines per language, the way the upstream linter does."""
    counts: dict[str, int] = {}
    language: str | None = None
    for line in lines:
        fence = FENCE.match(line)
        if fence is not None:
            language = None if language is not None else (fence.group(1).lower() or "text")
            continue
        if language is None:
            continue
        bucket = (
            "python"
            if language in PYTHON_LANGS
            else "typescript"
            if language in TS_LANGS
            else None
        )
        if bucket:
            counts[bucket] = counts.get(bucket, 0) + 1
    return counts


def lint_skill_dir(path: Path) -> list[Finding]:
    skill_file = path / "SKILL.md"
    findings: list[Finding] = []

    if not skill_file.is_file():
        return [Finding(BLOCK, "missing-skill-md", path, 1, "no SKILL.md in this directory")]

    text = skill_file.read_text(encoding="utf-8")
    lines = text.splitlines()

    try:
        frontmatter, body = split_frontmatter(text)
    except SkillError as error:
        return [Finding(BLOCK, "frontmatter", skill_file, 1, str(error))]

    name = frontmatter.get("name")
    if not isinstance(name, str) or not name.strip():
        findings.append(Finding(BLOCK, "name", skill_file, 2, "field 'name' is required"))
    else:
        name = name.strip()
        if name != path.name:
            findings.append(
                Finding(
                    BLOCK,
                    "name-mismatch",
                    skill_file,
                    2,
                    f"name '{name}' does not match directory '{path.name}'",
                )
            )
        if not NAME_PATTERN.match(name):
            findings.append(
                Finding(
                    BLOCK,
                    "name-format",
                    skill_file,
                    2,
                    "name must be lowercase letters, digits and single hyphens",
                )
            )
        if len(name) > NAME_MAX:
            findings.append(
                Finding(BLOCK, "name-length", skill_file, 2, f"{len(name)} > {NAME_MAX} characters")
            )

    description = frontmatter.get("description")
    if not isinstance(description, str) or not description.strip():
        findings.append(
            Finding(BLOCK, "description", skill_file, 3, "field 'description' is required")
        )
    else:
        description = " ".join(description.split())
        if len(description) > DESCRIPTION_MAX:
            findings.append(
                Finding(
                    BLOCK,
                    "description-length",
                    skill_file,
                    3,
                    f"{len(description)} > {DESCRIPTION_MAX} characters",
                )
            )
        elif len(description) > DESCRIPTION_BUDGET_WARN:
            findings.append(
                Finding(
                    WARN,
                    "description-budget",
                    skill_file,
                    3,
                    f"{len(description)} characters is always-on prompt; aim under {DESCRIPTION_BUDGET_WARN}",
                )
            )
        if not any(word in description.lower() for word in TRIGGER_WORDS):
            findings.append(
                Finding(
                    WARN,
                    "no-trigger",
                    skill_file,
                    3,
                    "description never says when to use the skill",
                )
            )

    body_lines = len(body.splitlines())
    if body_lines > BODY_LINE_BLOCK:
        findings.append(
            Finding(
                BLOCK,
                "body-size",
                skill_file,
                1,
                f"{body_lines} lines exceeds the hard cap of {BODY_LINE_BLOCK}",
            )
        )
    elif body_lines > BODY_LINE_WARN:
        findings.append(
            Finding(
                WARN,
                "body-size",
                skill_file,
                1,
                f"{body_lines} lines exceeds the target of {BODY_LINE_WARN}",
            )
        )

    if not (path / "references").is_dir():
        for language, total in _inline_language_lines(lines).items():
            if total > LANGUAGE_SPLIT_WARN:
                findings.append(
                    Finding(
                        WARN,
                        "language-split",
                        skill_file,
                        1,
                        f"{total} lines of {language} inline with no references/ split",
                    )
                )

    tokens = estimate_tokens(body)
    if tokens > ON_INVOKE_TOKEN_WARN:
        findings.append(
            Finding(
                WARN,
                "on-invoke-budget",
                skill_file,
                1,
                f"~{tokens:,} tokens on load exceeds the ~{ON_INVOKE_TOKEN_WARN:,} budget",
            )
        )

    for number, line in enumerate(lines, start=1):
        if PIPE_TO_SHELL.search(line):
            findings.append(
                Finding(WARN, "pipe-to-shell", skill_file, number, "pipes a remote script into a shell")
            )
        for model in MODEL_PATTERN.findall(line):
            if model not in ALLOWED_MODELS:
                findings.append(
                    Finding(
                        WARN,
                        "model-id",
                        skill_file,
                        number,
                        f"'{model}' is not in the allowlist; pin a supported id",
                    )
                )
        for target in MARKDOWN_LINK.findall(line):
            if target.startswith(("http://", "https://", "#", "mailto:", "${")):
                continue
            resolved = (path / target.split("#", 1)[0]).resolve()
            try:
                resolved.relative_to(path.resolve())
            except ValueError:
                findings.append(
                    Finding(WARN, "dead-link", skill_file, number, f"'{target}' leaves the skill directory")
                )
                continue
            if not resolved.exists():
                findings.append(
                    Finding(WARN, "dead-link", skill_file, number, f"'{target}' does not resolve")
                )

    return findings


def lint_library(library: Path) -> list[Finding]:
    """Lint every immediate child skill and the catalog they form together."""
    if not library.is_dir():
        raise SkillError(f"skill library not found: {library}")

    findings: list[Finding] = []
    for child in sorted(library.iterdir()):
        if child.is_dir():
            findings.extend(lint_skill_dir(child))

    seen: dict[str, Path] = {}
    for child in sorted(library.iterdir()):
        skill_file = child / "SKILL.md"
        if not child.is_dir() or not skill_file.is_file():
            continue
        try:
            frontmatter, _ = split_frontmatter(skill_file.read_text(encoding="utf-8"))
        except SkillError:
            continue
        description = frontmatter.get("description")
        if not isinstance(description, str):
            continue
        key = " ".join(description.lower().split())
        if key in seen and seen[key] != child:
            findings.append(
                Finding(
                    WARN,
                    "duplicate-description",
                    skill_file,
                    3,
                    f"same description as {seen[key].name}; the model cannot tell them apart",
                )
            )
        else:
            seen[key] = child

    try:
        loaded = discover(library)
    except SkillError:
        loaded = []
    if loaded:
        catalog = "\n".join(f"- {skill.name}: {skill.description}" for skill in loaded)
        tokens = estimate_tokens(catalog)
        if tokens > 1200:
            findings.append(
                Finding(
                    WARN,
                    "catalog-budget",
                    library,
                    1,
                    f"~{tokens:,} tokens of always-on catalog for {len(loaded)} skills",
                )
            )

    return findings


def blocking(findings: list[Finding]) -> list[Finding]:
    return [finding for finding in findings if finding.severity == BLOCK]
