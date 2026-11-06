import unittest
from datetime import UTC, datetime

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.agent.service import DigestEntry, GeneratedDigest
from app.config import Settings
from app.database.models import Article, Base, Digest, Source
from app.digest.run import run_daily_digest


def settings() -> Settings:
    return Settings(
        database_url="sqlite://",
        deepseek_api_key="test-key",
        deepseek_base_url="https://api.deepseek.com",
        deepseek_model="test-model",
        smtp_host="smtp.example.com",
        smtp_port=587,
        smtp_username="user",
        smtp_password="password",
        email_sender="digest@example.com",
        email_recipient="reader@example.com",
    )


def generate(content, *, allowed_urls, settings):
    return GeneratedDigest(
        subject="Daily digest",
        entries=tuple(
            DigestEntry(title="Video", summary="Summary", url=url)
            for url in allowed_urls
        ),
    )


class DailyDigestRunTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.session = Session(self.engine)
        source = Source(
            kind="youtube",
            name="Example",
            channel_id="UC_x5XG1OV2P6uZZ5FSM9Ttw",
            feed_url="https://youtube.com/feed",
        )
        self.session.add(source)
        self.session.flush()
        self.session.add(
            Article(
                source_id=source.id,
                video_id="abcdefghijk",
                title="Example video",
                url="https://youtu.be/abcdefghijk",
                description="RSS description",
                published_at=datetime(2026, 11, 6, 10, tzinfo=UTC),
            )
        )
        self.session.commit()
        self.now = datetime(2026, 11, 6, 12, tzinfo=UTC)
        self.sent = []

    def tearDown(self) -> None:
        self.session.close()
        self.engine.dispose()

    def send(self, subject, rendered, *, settings):
        self.sent.append((subject, rendered))

    def test_records_success_and_skips_duplicate_normal_run(self) -> None:
        first = run_daily_digest(
            self.session,
            now=self.now,
            settings=settings(),
            generator=generate,
            email_sender=self.send,
        )
        second = run_daily_digest(
            self.session,
            now=self.now,
            settings=settings(),
            generator=generate,
            email_sender=self.send,
        )
        digests = self.session.scalars(select(Digest)).all()

        self.assertEqual(first.status, "sent")
        self.assertFalse(first.skipped)
        self.assertEqual(second.digest_id, first.digest_id)
        self.assertTrue(second.skipped)
        self.assertEqual(len(self.sent), 1)
        self.assertEqual(len(digests), 1)
        self.assertEqual(digests[0].status, "sent")
        self.assertIsNotNone(digests[0].sent_at)

    def test_force_records_another_successful_attempt(self) -> None:
        for force in (False, True):
            run_daily_digest(
                self.session,
                now=self.now,
                force=force,
                settings=settings(),
                generator=generate,
                email_sender=self.send,
            )

        self.assertEqual(len(self.session.scalars(select(Digest)).all()), 2)
        self.assertEqual(len(self.sent), 2)

    def test_empty_run_is_recorded_without_generation_or_email(self) -> None:
        article = self.session.scalar(select(Article))
        article.published_at = datetime(2026, 11, 4, tzinfo=UTC)
        self.session.commit()

        def unexpected_generator(*args, **kwargs):
            raise AssertionError("generator should not run")

        result = run_daily_digest(
            self.session,
            now=self.now,
            settings=settings(),
            generator=unexpected_generator,
            email_sender=self.send,
        )

        self.assertEqual(result.status, "empty")
        self.assertEqual(self.sent, [])
        self.assertEqual(
            self.session.scalar(select(Digest.status)),
            "empty",
        )

    def test_failed_generation_is_recorded_and_can_be_retried(self) -> None:
        def failing_generator(*args, **kwargs):
            raise RuntimeError("model unavailable")

        with self.assertRaisesRegex(RuntimeError, "model unavailable"):
            run_daily_digest(
                self.session,
                now=self.now,
                settings=settings(),
                generator=failing_generator,
                email_sender=self.send,
            )
        failed = self.session.scalar(select(Digest))
        self.assertEqual(failed.status, "failed")

        retry = run_daily_digest(
            self.session,
            now=self.now,
            settings=settings(),
            generator=generate,
            email_sender=self.send,
        )
        self.assertEqual(retry.status, "sent")
        self.assertEqual(
            [digest.status for digest in self.session.scalars(select(Digest)).all()],
            ["failed", "sent"],
        )

    def test_failed_delivery_is_recorded_and_can_be_retried(self) -> None:
        def failing_sender(*args, **kwargs):
            raise OSError("SMTP unavailable")

        with self.assertRaisesRegex(OSError, "SMTP unavailable"):
            run_daily_digest(
                self.session,
                now=self.now,
                settings=settings(),
                generator=generate,
                email_sender=failing_sender,
            )
        self.assertEqual(self.session.scalar(select(Digest.status)), "failed")

        result = run_daily_digest(
            self.session,
            now=self.now,
            settings=settings(),
            generator=generate,
            email_sender=self.send,
        )
        self.assertEqual(result.status, "sent")


if __name__ == "__main__":
    unittest.main()
