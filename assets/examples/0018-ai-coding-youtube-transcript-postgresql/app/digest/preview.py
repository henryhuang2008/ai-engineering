from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from app.agent.service import GeneratedDigest, generate_digest_content
from app.config import Settings
from app.digest.generate import (
    generate_digest_for_articles,
    get_digest_window,
    select_digest_articles,
)
from app.emailer.smtp import render_digest_email


@dataclass(frozen=True)
class DigestPreview:
    status: str
    article_count: int
    subject: str
    text_body: str


def preview_daily_digest(
    session: Session,
    *,
    now: datetime | None = None,
    settings: Settings | None = None,
    generator: Callable[..., GeneratedDigest] = generate_digest_content,
) -> DigestPreview:
    window_start, window_end = get_digest_window(now)
    articles = select_digest_articles(
        session,
        window_start=window_start,
        window_end=window_end,
    )
    if not articles:
        return DigestPreview(
            status="empty",
            article_count=0,
            subject=f"Daily YouTube Digest - {window_end.date().isoformat()}",
            text_body="No videos were published in the last 24 hours.",
        )

    generated = generate_digest_for_articles(
        articles,
        settings=settings,
        generator=generator,
    )
    if generated is None:
        raise RuntimeError("Digest generation unexpectedly returned no content")
    rendered = render_digest_email(generated)
    return DigestPreview(
        status="preview",
        article_count=len(articles),
        subject=generated.subject,
        text_body=rendered.text_body,
    )
