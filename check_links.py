#!/usr/bin/env python
"""Repo guard: every local link resolves, every lesson links forward, no stale lesson numbers.

Run from anywhere:

    python check_links.py

Checks, for the course pages (lessons/, reference/, assets/examples/*/index.html):
  1. every relative href/src points at a file that exists
  2. each lesson's "What's next" section links to the next lesson in numeric order
  3. a link label that names a lesson ("Lesson 7", "L7") matches the target file
  4. no page cites a lesson number or range above the current lesson count

External URLs are not fetched; this is a filesystem check, not a crawl.

Exit code 0 = consistent, 1 = drift found.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LESSONS = ROOT / "lessons"

LINK_RE = re.compile(r'(?:href|src)="([^"#][^"]*)"')
NEXT_RE = re.compile(r"<h2>What's next[^<]*</h2>(.*?)(?=<h2>|<div class=\"footer-nav\"|$)", re.S)
ANCHOR_RE = re.compile(r'<a href="(?:\.\./lessons/)?(\d{4})-[^"]+">(.*?)</a>', re.S)


def pages() -> list[Path]:
    found = sorted(LESSONS.glob("*.html"))
    reference = ROOT / "reference"
    if reference.is_dir():
        found += sorted(reference.rglob("*.html"))
    found += sorted((ROOT / "assets" / "examples").glob("*/index.html"))
    return found


def broken_targets(page: Path, text: str) -> list[str]:
    out: list[str] = []
    for match in LINK_RE.finditer(text):
        target = match.group(1)
        if target.startswith(("http://", "https://", "mailto:", "//", "data:")):
            continue
        target = target.split("#", 1)[0].split("?", 1)[0]
        if not target:
            continue
        if not (page.parent / target.replace("\\", "/")).resolve().exists():
            out.append(f"{page.relative_to(ROOT)}: broken link -> {target}")
    return out


def next_link_issues(lessons: list[Path]) -> list[str]:
    out: list[str] = []
    for index, lesson in enumerate(lessons):
        match = NEXT_RE.search(lesson.read_text(encoding="utf-8"))
        if match is None:
            out.append(f"{lesson.relative_to(ROOT)}: no What's next section")
            continue
        if index + 1 == len(lessons):
            continue
        expected = lessons[index + 1].name
        if expected not in match.group(1):
            out.append(f"{lesson.relative_to(ROOT)}: What's next does not link to {expected}")
    return out


def label_issues(page: Path, text: str) -> list[str]:
    out: list[str] = []
    for match in ANCHOR_RE.finditer(text):
        number = int(match.group(1))
        label = re.sub(r"<[^>]+>", " ", match.group(2))
        claimed = [int(n) for n in re.findall(r"(?i)\b(?:lesson|l)\s?(\d{1,2})\b", label)]
        if claimed and number not in claimed:
            out.append(
                f"{page.relative_to(ROOT)}: link labelled {claimed} points at {match.group(1)}"
            )
    return out


def stale_references(page: Path, text: str, lesson_count: int) -> list[str]:
    out: list[str] = []
    pattern = re.compile(r"(?i)\b(?:lesson|L)\s?(\d{1,2})\b")
    for match in pattern.finditer(text):
        number = int(match.group(1))
        if number > lesson_count:
            line = text[: match.start()].count("\n") + 1
            out.append(f"{page.relative_to(ROOT)}:{line}: cites Lesson {number} (only {lesson_count} exist)")

    ranges = re.compile(r"(?i)\b(?:lessons?|Ls?)\s?(\d{1,2})s?\s?[–—-]\s?(\d{1,2})\b")
    for match in ranges.finditer(text):
        high = int(match.group(2))
        if high > lesson_count:
            line = text[: match.start()].count("\n") + 1
            out.append(
                f"{page.relative_to(ROOT)}:{line}: cites a lesson range ending at {high} "
                f"(only {lesson_count} exist)"
            )
    return out


def main() -> int:
    course_pages = pages()
    lessons = sorted(LESSONS.glob("*.html"))
    count = len(lessons)

    problems: list[str] = []
    for page in course_pages:
        text = page.read_text(encoding="utf-8")
        problems += broken_targets(page, text)
        problems += label_issues(page, text)
        if page.parent == LESSONS:
            problems += stale_references(page, text, count)
    problems += next_link_issues(lessons)

    if problems:
        print(f"FAIL — {len(problems)} link issue(s):")
        for item in problems:
            print(" -", item)
        return 1

    print(f"OK — {len(course_pages)} pages, all local links resolve, {count} lessons link forward")
    return 0


if __name__ == "__main__":
    sys.exit(main())
