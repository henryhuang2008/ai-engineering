from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from tests.support import csv_path, script_path

GOOD_NOTE = """### Added

- You can export the current view as CSV from the export menu.

### Fixed

- Search now matches hyphenated words such as `release-notes`.
"""


def run(script: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(script), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def test_profile_reports_shape_and_statistics() -> None:
    result = run(script_path("csv-insights", "profile.py"), "--csv", str(csv_path()), "--json")

    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    columns = {column["name"]: column for column in report["columns"]}

    assert report["rows"] == 10
    assert columns["amount"]["inferred_type"] == "float"
    assert columns["amount"]["missing"] == 1
    assert columns["amount"]["distinct"] == 9
    assert columns["amount"]["max"] == 640.0
    assert columns["units"]["inferred_type"] == "int"
    assert columns["units"]["mean"] == 2.8
    assert columns["region"]["distinct"] == 4


def test_profile_refuses_a_missing_file() -> None:
    result = run(script_path("csv-insights", "profile.py"), "--csv", "nope.csv")

    assert result.returncode == 2
    assert "error:" in result.stderr


def test_aggregate_groups_and_sums() -> None:
    result = run(
        script_path("csv-insights", "aggregate.py"),
        "--csv",
        str(csv_path()),
        "--group",
        "region",
        "--value",
        "amount",
        "--agg",
        "sum",
    )

    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    by_region = {row["group"]: row for row in report["results"]}

    assert by_region["North"]["value"] == 1080.39
    assert by_region["South"]["value"] == 239.5
    assert by_region["East"]["n"] == 1
    assert by_region["North"]["rows"] == 4


def test_aggregate_count_needs_no_value_column() -> None:
    result = run(
        script_path("csv-insights", "aggregate.py"),
        "--csv",
        str(csv_path()),
        "--group",
        "channel",
        "--agg",
        "count",
    )

    assert result.returncode == 0, result.stderr
    by_channel = {row["group"]: row["value"] for row in json.loads(result.stdout)["results"]}
    assert by_channel == {"mobile": 2, "store": 4, "web": 4}


def test_lint_notes_accepts_a_good_draft(tmp_path: Path) -> None:
    draft = tmp_path / "note.md"
    draft.write_text(GOOD_NOTE, encoding="utf-8")

    result = run(script_path("release-notes", "lint_notes.py"), "--file", str(draft), "--json")

    assert result.returncode == 0, result.stdout
    assert json.loads(result.stdout)["problems"] == []


def test_lint_notes_rejects_filler_and_compound_bullets(tmp_path: Path) -> None:
    draft = tmp_path / "note.md"
    draft.write_text(
        "### Changed\n\n- Various improvements and performance improvements and minor changes.\n",
        encoding="utf-8",
    )

    result = run(script_path("release-notes", "lint_notes.py"), "--file", str(draft), "--json")

    assert result.returncode == 1
    found = {problem["rule"] for problem in json.loads(result.stdout)["problems"]}
    assert "banned-phrase" in found
    assert "compound-bullet" in found


def test_lint_notes_accepts_the_draft_as_text() -> None:
    result = run(
        script_path("release-notes", "lint_notes.py"),
        "--text",
        GOOD_NOTE,
        "--json",
    )

    assert result.returncode == 0, result.stdout
    assert json.loads(result.stdout)["source"] == "<text>"


def test_lint_notes_rejects_a_draft_without_groups(tmp_path: Path) -> None:
    draft = tmp_path / "note.md"
    draft.write_text("Just a paragraph, no headings.\n", encoding="utf-8")

    result = run(script_path("release-notes", "lint_notes.py"), "--file", str(draft))

    assert result.returncode == 1
    assert "no-groups" in result.stdout
