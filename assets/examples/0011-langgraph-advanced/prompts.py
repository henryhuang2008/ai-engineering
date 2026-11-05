"""Prompt builders: one analyzer for every source, one selector, one synthesis."""

from __future__ import annotations

import json

from langchain_core.messages import HumanMessage, SystemMessage

ANALYST = """You are a skeptical engineering analyst reading {source} results.
Report what the results actually claim, where they are specific, and what they
leave out. Do not add facts that are not in the results."""

SELECTOR = """You choose which Reddit threads are worth reading in full.
Return at most three URLs, and only URLs that appear in the supplied list."""

SYNTHESIS = """You are the final writer for a multi-source research run.
Write a direct recommendation, two or three reasons, and one caveat.
Name any source that was missing or empty. Keep it under 180 words."""


def analysis_messages(source: str, question: str, payload: object) -> list:
    return [
        SystemMessage(content=ANALYST.format(source=source)),
        HumanMessage(
            content=(
                f"Question: {question}\n\n"
                f"Results:\n{json.dumps(payload, indent=2, ensure_ascii=False)}\n\n"
                "Write 4-6 sentences. No headings, no preamble."
            )
        ),
    ]


def selector_messages(question: str, posts: list[dict]) -> list:
    listed = [
        {"title": post["title"], "url": post["url"], "snippet": post["snippet"]}
        for post in posts
    ]
    return [
        SystemMessage(content=SELECTOR),
        HumanMessage(
            content=(
                f"Question: {question}\n\n"
                f"Threads:\n{json.dumps(listed, indent=2, ensure_ascii=False)}"
            )
        ),
    ]


def synthesis_messages(question: str, analyses: dict[str, str]) -> list:
    blocks = "\n\n".join(
        f"### {source}\n{text}" for source, text in analyses.items()
    )
    return [
        SystemMessage(content=SYNTHESIS),
        HumanMessage(content=f"Question: {question}\n\n{blocks}"),
    ]
