from __future__ import annotations

from pathlib import Path

from app.lint import BLOCK, WARN, blocking, lint_library, lint_skill_dir
from tests.support import PROJECT_ROOT, write_skill

LIBRARY = PROJECT_ROOT / "skills"
BROKEN = PROJECT_ROOT / "fixtures" / "broken-library"


def rules(findings) -> set[str]:
    return {finding.rule for finding in findings}


def test_the_real_library_passes_cleanly() -> None:
    findings = lint_library(LIBRARY)

    assert findings == [], [finding.format(LIBRARY) for finding in findings]


def test_the_broken_fixture_reports_the_expected_rules() -> None:
    findings = lint_skill_dir(BROKEN / "legacy-notes")

    assert rules(findings) >= {"name-mismatch", "no-trigger", "dead-link", "pipe-to-shell", "model-id"}
    assert {finding.severity for finding in findings} == {BLOCK, WARN}


def test_a_dead_link_names_the_target() -> None:
    findings = lint_skill_dir(BROKEN / "legacy-notes")

    dead = next(finding for finding in findings if finding.rule == "dead-link")
    assert "schema.md" in dead.message


def test_body_over_the_hard_cap_blocks(tmp_path: Path) -> None:
    directory = write_skill(
        tmp_path / "huge-skill",
        "huge-skill",
        description="Huge skill, use when testing size limits.",
        body="\n".join(f"line {index}" for index in range(610)),
    )

    findings = lint_skill_dir(directory)

    assert "body-size" in rules(findings)
    assert any(finding.severity == BLOCK for finding in findings)


def test_body_over_the_target_warns(tmp_path: Path) -> None:
    directory = write_skill(
        tmp_path / "long-skill",
        "long-skill",
        description="Long skill, use when testing size limits.",
        body="\n".join(f"line {index}" for index in range(520)),
    )

    findings = lint_skill_dir(directory)

    size = [finding for finding in findings if finding.rule == "body-size"]
    assert size and size[0].severity == WARN


def test_inline_code_without_references_warns(tmp_path: Path) -> None:
    code = "\n".join(f"print({index})" for index in range(160))
    directory = write_skill(
        tmp_path / "inline-code",
        "inline-code",
        description="Inline code skill, use when testing the split rule.",
        body=f"```python\n{code}\n```",
    )

    findings = lint_skill_dir(directory)

    assert "language-split" in rules(findings)


def test_a_references_directory_satisfies_the_split_rule(tmp_path: Path) -> None:
    code = "\n".join(f"print({index})" for index in range(160))
    directory = write_skill(
        tmp_path / "split-code",
        "split-code",
        description="Split code skill, use when testing the split rule.",
        body=f"```python\n{code}\n```",
    )
    (directory / "references").mkdir()

    assert "language-split" not in rules(lint_skill_dir(directory))


def test_duplicate_descriptions_warn(tmp_path: Path) -> None:
    description = "Does the same thing, use when the user asks for it."
    write_skill(tmp_path / "one", "one", description=description, body="body")
    write_skill(tmp_path / "two", "two", description=description, body="body")

    findings = lint_library(tmp_path)

    assert "duplicate-description" in rules(findings)


def test_name_mismatch_blocks(tmp_path: Path) -> None:
    directory = write_skill(
        tmp_path / "right-name",
        "other-name",
        description="Mismatch, use when testing the name rule.",
        body="body",
    )

    findings = lint_skill_dir(directory)

    assert "name-mismatch" in rules(findings)
    assert blocking(findings)


def test_missing_skill_md_is_blocking(tmp_path: Path) -> None:
    directory = tmp_path / "empty"
    directory.mkdir()

    findings = lint_skill_dir(directory)

    assert rules(findings) == {"missing-skill-md"}
    assert blocking(findings)
