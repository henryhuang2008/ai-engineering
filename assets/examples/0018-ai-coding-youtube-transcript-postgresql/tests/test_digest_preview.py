import unittest
from datetime import UTC, datetime
import json

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.agent.service import DigestEntry, GeneratedDigest
from app.database.models import Article, Base, Digest, Source
from app.digest.preview import preview_daily_digest, saved_articles_json


class DigestPreviewTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.session = Session(self.engine)
        source = Source(
            kind="youtube",
            name="Example channel",
            channel_id="UC_x5XG1OV2P6uZZ5FSM9Ttw",
            feed_url="https://youtube.com/feed",
        )
        self.session.add(source)
        self.session.flush()
        self.session.add(
            Article(
                source_id=source.id,
                video_id="abcdefghijk",
                title="Saved video",
                url="https://youtu.be/abcdefghijk",
                description="Saved description",
                published_at=datetime(2026, 11, 6, 10, tzinfo=UTC),
            )
        )
        self.session.commit()
        self.now = datetime(2026, 11, 6, 12, tzinfo=UTC)

    def tearDown(self) -> None:
        self.session.close()
        self.engine.dispose()

    def test_builds_preview_from_database_without_persisting_or_sending(self) -> None:
        generated_calls = []

        def generator(content, *, allowed_urls, settings):
            generated_calls.append((content, allowed_urls))
            return GeneratedDigest(
                subject="Digest preview subject",
                entries=(
                    DigestEntry(
                        title="Saved video",
                        summary="Generated summary",
                        url=allowed_urls[0],
                    ),
                ),
            )

        preview = preview_daily_digest(
            self.session,
            now=self.now,
            generator=generator,
        )

        self.assertEqual(preview.status, "preview")
        self.assertEqual(preview.article_count, 1)
        self.assertIn("Digest preview subject", preview.text_body)
        self.assertIn("Generated summary", preview.text_body)
        self.assertIn("Saved description", generated_calls[0][0])
        self.assertEqual(
            generated_calls[0][1],
            ("https://youtu.be/abcdefghijk",),
        )
        self.assertEqual(self.session.scalars(select(Digest)).all(), [])

    def test_empty_preview_does_not_call_generator_or_persist(self) -> None:
        article = self.session.scalar(select(Article))
        article.published_at = datetime(2026, 11, 4, tzinfo=UTC)
        self.session.commit()

        def unexpected_generator(*args, **kwargs):
            raise AssertionError("generator should not run")

        preview = preview_daily_digest(
            self.session,
            now=self.now,
            generator=unexpected_generator,
        )

        self.assertEqual(preview.status, "empty")
        self.assertIn("No videos", preview.text_body)
        self.assertEqual(self.session.scalars(select(Digest)).all(), [])

    def test_raw_json_contains_saved_fields_without_generating_content(self) -> None:
        article = self.session.scalar(select(Article))
        article.transcript = "Transcript saved in database."
        article.transcript_language = "en"
        article.transcript_is_generated = False
        self.session.commit()

        records = json.loads(saved_articles_json(self.session, now=self.now))

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["title"], "Saved video")
        self.assertEqual(records[0]["description"], "Saved description")
        self.assertEqual(records[0]["transcript"], "Transcript saved in database.")
        self.assertEqual(records[0]["transcript_language"], "en")
        self.assertFalse(records[0]["transcript_is_generated"])
        self.assertEqual(records[0]["source_name"], "Example channel")
        self.assertEqual(self.session.scalars(select(Digest)).all(), [])

    def test_raw_json_is_empty_array_when_no_saved_article_in_window(self) -> None:
        article = self.session.scalar(select(Article))
        article.published_at = datetime(2026, 11, 4, tzinfo=UTC)
        self.session.commit()

        self.assertEqual(saved_articles_json(self.session, now=self.now), "[]")


if __name__ == "__main__":
    unittest.main()
