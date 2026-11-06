from __future__ import annotations

from collections.abc import Sequence

from app.database.models import Article

MAX_ARTICLE_CONTENT_CHARS = 12_000
MAX_DIGEST_INPUT_CHARS = 48_000
TRUNCATION_MARKER = "\n[Content truncated.]"


def build_digest_input(articles: Sequence[Article]) -> str:
    content, _ = build_digest_input_with_articles(articles)
    return content


def build_digest_input_with_articles(
    articles: Sequence[Article],
) -> tuple[str, tuple[Article, ...]]:
    parts: list[str] = []
    included_articles: list[Article] = []
    input_length = 0

    for article in articles:
        transcript = (article.transcript or "").strip()
        description = article.description.strip()
        if transcript:
            content = transcript
            content_source = "transcript"
        elif description:
            content = description
            content_source = "description"
        else:
            content = "[No transcript or description available.]"
            content_source = "unavailable"

        source_name = article.source.name if article.source else "Unknown"
        published_at = (
            article.published_at.isoformat()
            if article.published_at
            else "Unknown"
        )
        separator = "\n\n" if parts else ""
        prefix = (
            f"{separator}## Video: {article.title}\n"
            f"Channel: {source_name}\n"
            f"Published: {published_at}\n"
            f"URL: {article.url}\n"
            f"Content source: {content_source}\n"
            "Content:\n"
        )

        remaining = MAX_DIGEST_INPUT_CHARS - input_length
        content_space = remaining - len(prefix)
        if content_space <= 0:
            break

        content_limit = min(len(content), MAX_ARTICLE_CONTENT_CHARS, content_space)
        truncated = content_limit < len(content)
        total_limit_reached = content_space < min(
            len(content),
            MAX_ARTICLE_CONTENT_CHARS,
        )
        if truncated:
            if content_space <= len(TRUNCATION_MARKER):
                break
            content_limit = min(
                content_limit,
                content_space - len(TRUNCATION_MARKER),
            )
            block = prefix + content[:content_limit] + TRUNCATION_MARKER
        else:
            block = prefix + content[:content_limit]

        parts.append(block)
        included_articles.append(article)
        input_length += len(block)
        if total_limit_reached:
            break
        if input_length >= MAX_DIGEST_INPUT_CHARS:
            break

    return "".join(parts), tuple(included_articles)
