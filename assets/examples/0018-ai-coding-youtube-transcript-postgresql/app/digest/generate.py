from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.agent.service import GeneratedDigest, generate_digest_content
from app.config import Settings
from app.database.models import Article
from app.digest.input import build_digest_input_with_articles

DIGEST_WINDOW = timedelta(hours=24)


def get_digest_window(now: datetime | None = None) -> tuple[datetime, datetime]:
    window_end = now or datetime.now(UTC)
    if window_end.tzinfo is None or window_end.utcoffset() is None:
        raise ValueError("Digest window end must be timezone-aware")
    window_end = window_end.astimezone(UTC)
    return window_end - DIGEST_WINDOW, window_end


def select_digest_articles(
    session: Session,
    *,
    window_start: datetime,
    window_end: datetime,
) -> tuple[Article, ...]:
    statement = (
        select(Article)
        .options(selectinload(Article.source))
        .where(
            Article.published_at.is_not(None),
            Article.published_at >= window_start,
            Article.published_at <= window_end,
        )
        .order_by(Article.published_at, Article.id)
    )
    return tuple(session.scalars(statement).all())


def generate_digest_for_articles(
    articles: tuple[Article, ...],
    *,
    settings: Settings | None = None,
    generator: Callable[..., GeneratedDigest] = generate_digest_content,
) -> GeneratedDigest | None:
    if not articles:
        return None
    content, included_articles = build_digest_input_with_articles(articles)
    if not content:
        raise ValueError("Selected articles produced empty digest input")
    return generator(
        content,
        allowed_urls=tuple(article.url for article in included_articles),
        settings=settings,
    )
