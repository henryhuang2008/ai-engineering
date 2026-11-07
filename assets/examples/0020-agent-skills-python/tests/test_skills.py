from __future__ import annotations

from pathlib import Path

import pytest

from app.skills import (
    SkillError,
    catalog_lines,
    discover,
    estimate_tokens,
    load_skill,
    split_frontmatter,
)
from tests.support import PROJECT_ROOT, write_skill

LIBRARY = PROJECT_ROOT / "skills"


def test_discovers_both_library_skills() -> None:
    skills = discover(LIBRARY)

    assert [skill.name for skill in skills] == ["csv-insights", "release-notes"]


def test_a_skill_keeps_its_description_and_bundled_files() -> None:
    skill = load_skill(LIBRARY / "csv-insights")

    assert skill.directory_name == "csv-insights"
    assert skill.description.startswith("Profile a CSV file")
    assert skill.relative_files() == [
        "references/metrics.md",
        "scripts/aggregate.py",
        "scripts/profile.py",
    ]


def test_body_lines_exclude_frontmatter() -> None:
    skill = load_skill(LIBRARY / "csv-insights")

    assert skill.body.startswith("# CSV insights")
    assert skill.body_lines == len(skill.body.splitlines())


def test_catalog_is_one_line_per_skill() -> None:
    lines = catalog_lines(discover(LIBRARY))

    assert len(lines) == 2
    assert lines[0].startswith("- csv-insights: ")


def test_frontmatter_must_be_closed() -> None:
    with pytest.raises(SkillError, match="not closed"):
        split_frontmatter("---\nname: x\n\nbody\n")


def test_name_is_required(tmp_path: Path) -> None:
    directory = tmp_path / "no-name"
    directory.mkdir()
    (directory / "SKILL.md").write_text("---\ndescription: does things\n---\n\nbody\n")

    with pytest.raises(SkillError, match="'name' is required"):
        load_skill(directory)


def test_name_must_be_lowercase_and_hyphenated(tmp_path: Path) -> None:
    directory = write_skill(
        tmp_path / "Bad_Name",
        "Bad_Name",
        description="Does things when the user asks.",
        body="body",
    )

    with pytest.raises(SkillError, match="lowercase"):
        load_skill(directory)


def test_description_length_is_capped(tmp_path: Path) -> None:
    directory = write_skill(
        tmp_path / "long-description",
        "long-description",
        description="x" * 1025,
        body="body",
    )

    with pytest.raises(SkillError, match="1024"):
        load_skill(directory)


def test_nested_directories_are_not_skills(tmp_path: Path) -> None:
    outer = write_skill(
        tmp_path / "outer",
        "outer",
        description="Outer skill, use when testing.",
        body="body",
    )
    write_skill(
        outer / "vendor",
        "vendor",
        description="Nested skill, use when testing.",
        body="body",
    )

    assert [skill.name for skill in discover(tmp_path)] == ["outer"]


def test_token_estimate_is_stable_and_positive() -> None:
    assert estimate_tokens("") == 1
    assert estimate_tokens("a" * 400) == 100
