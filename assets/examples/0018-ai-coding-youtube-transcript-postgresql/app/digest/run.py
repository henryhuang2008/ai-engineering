from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent.service import GeneratedDigest, generate_digest_content
from app.config import Settings, get_settings
from app.database.models import Digest
from app.digest.generate import (
    generate_digest_for_articles,
    get_digest_window,
    select_digest_articles,
)
from app.emailer.smtp import render_digest_email, send_digest_email


@dataclass(frozen=True)
class DigestRunResult:
    status: str
    digest_id: int | None
    skipped: bool


def run_daily_digest(
    session: Session,
    *,
    now: datetime | None = None,
    force: bool = False,
    settings: Settings | None = None,
    generator: Callable[..., GeneratedDigest] = generate_digest_content,
    email_sender: Callable[..., None] = send_digest_email,
) -> DigestRunResult:
    active_settings = settings or get_settings()
    window_start, window_end = get_digest_window(now)
    run_date = window_end.date()

    if not force:
        existing_sent = session.scalar(
            select(Digest.id).where(
                Digest.run_date == run_date,
                Digest.status == "sent",
            )
        )
        if existing_sent is not None:
            return DigestRunResult("sent", existing_sent, skipped=True)

    articles = select_digest_articles(
        session,
        window_start=window_start,
        window_end=window_end,
    )
    attempt = Digest(
        run_date=run_date,
        window_start=window_start,
        window_end=window_end,
        subject="",
        text_body="",
        html_body="",
        model_name=active_settings.deepseek_model,
        article_count=len(articles),
        status="failed",
        recipient=active_settings.email_recipient or "",
    )
    session.add(attempt)
    session.commit()

    if not articles:
        attempt.status = "empty"
        attempt.subject = f"Daily YouTube Digest - {run_date.isoformat()}"
        attempt.text_body = "No videos were published in the last 24 hours."
        attempt.html_body = (
            "<!doctype html><html lang=\"en\"><body>"
            "<p>No videos were published in the last 24 hours.</p>"
            "</body></html>"
        )
        session.commit()
        return DigestRunResult("empty", attempt.id, skipped=False)

    try:
        active_settings.require_deepseek()
        active_settings.require_smtp()
        generated = generate_digest_for_articles(
            articles,
            settings=active_settings,
            generator=generator,
        )
        if generated is None:
            raise RuntimeError("Digest generation unexpectedly returned no content")
        rendered = render_digest_email(generated)
        attempt.subject = generated.subject
        attempt.text_body = rendered.text_body
        attempt.html_body = rendered.html_body
        session.commit()

        email_sender(
            generated.subject,
            rendered,
            settings=active_settings,
        )
    except Exception:
        attempt.status = "failed"
        session.commit()
        raise

    attempt.status = "sent"
    attempt.sent_at = datetime.now(UTC)
    session.commit()
    return DigestRunResult("sent", attempt.id, skipped=False)
