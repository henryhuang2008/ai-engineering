"""Check a release-note draft against the house style. Exit 1 on problems."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

GROUPS = ("Added", "Changed", "Fixed", "Removed")
BANNED = (
    "various improvements",
    "performance improvements",
    "bug fixes and stability",
    "minor changes",
    "under the hood",
)
HEADING = re.compile(r"^### (?P<name>.+?)\s*$")


def lint(text: str) -> list[dict[str, object]]:
    problems: list[dict[str, object]] = []
    lines = text.splitlines()
    headings: list[str] = []
    bullet_count = 0

    for number, line in enumerate(lines, start=1):
        heading = HEADING.match(line)
        if heading:
            name = heading.group("name")
            headings.append(name)
            if name not in GROUPS:
                problems.append(
                    {
                        "line": number,
                        "rule": "unknown-group",
                        "message": f"'{name}' is not one of {list(GROUPS)}",
                    }
                )
            continue

        if line.lstrip().startswith("- "):
            bullet_count += 1
            body = line.lstrip()[2:].strip()
            if len(body.split()) > 30:
                problems.append(
                    {
                        "line": number,
                        "rule": "long-bullet",
                        "message": f"{len(body.split())} words; split or shorten",
                    }
                )
            if body.count(" and ") >= 2:
                problems.append(
                    {
                        "line": number,
                        "rule": "compound-bullet",
                        "message": "more than one change in a bullet",
                    }
                )

        lowered = line.lower()
        for phrase in BANNED:
            if phrase in lowered:
                problems.append(
                    {
                        "line": number,
                        "rule": "banned-phrase",
                        "message": f"'{phrase}' says nothing; name the change",
                    }
                )

    if not headings:
        problems.append({"line": 1, "rule": "no-groups", "message": "no ### group headings"})
    if bullet_count == 0:
        problems.append({"line": 1, "rule": "no-bullets", "message": "no bullet entries"})
    if len(headings) != len(set(headings)):
        problems.append({"line": 1, "rule": "duplicate-group", "message": "a group appears twice"})

    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Lint a release-note draft.")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--file", type=Path)
    # The agent has no file-write tool, so a draft that only exists in the
    # conversation must be checkable without saving it first.
    source.add_argument("--text")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    label = str(args.file) if args.file else "<text>"
    if args.file:
        try:
            text = args.file.read_text(encoding="utf-8")
        except OSError as error:
            print(f"error: {error}", file=sys.stderr)
            return 2
    else:
        text = args.text

    problems = lint(text)

    if args.json:
        print(json.dumps({"source": label, "problems": problems}, indent=2))
    else:
        for problem in problems:
            print(f"{label}:{problem['line']}: {problem['rule']}: {problem['message']}")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
