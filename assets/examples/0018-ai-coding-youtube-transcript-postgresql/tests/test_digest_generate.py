import unittest
from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.agent.service import DigestEntry, GeneratedDigest
from app.database.models import Article, Base, Source
from app.digest.generate import (
    generate_digest_for_articles,
    get_digest_window,
    select_digest_articles,
)


class DigestGenerationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.session = Session(self.engine)
        self.source = Source(
            kind="youtube",
            name="Example channel",
            channel_id="UC_x5XG1OV2P6uZZ5FSM9Ttw",
            feed_url="https://youtube.com/feed",
        )
        self.session.add(self.source)
        self.session.flush()
        self.now = datetime(2026, 11, 6, 12, tzinfo=UTC)
        for offset, video_id in (
            (-24, "lower-bound"),
            (0, "upper-bound"),
            (-25, "too-old"),
            (1, "future"),
        ):
            self.session.add(
                Article(
                    source_id=self.source.id,
                    video_id=video_id,
                    title=video_id,
                    url=f"https://youtu.be/{video_id}",
                    description="description",
                    published_at=self.now + timedelta(hours=offset),
                )
            )
        self.session.add(
            Article(
                source_id=self.source.id,
                video_id="missing-time",
                title="missing time",
                url="https://youtu.be/missingtime",
                description="description",
            )
        )
        self.session.commit()

    def tearDown(self) -> None:
        self.session.close()
        self.engine.dispose()

    def test_selects_inclusive_utc_24_hour_window(self) -> None:
        start, end = get_digest_window(self.now)
        articles = select_digest_articles(
            self.session,
            window_start=start,
            window_end=end,
        )

        self.assertEqual(
            {article.video_id for article in articles},
            {"lower-bound", "upper-bound"},
        )

    def test_rejects_naive_window_time(self) -> None:
        with self.assertRaisesRegex(ValueError, "timezone-aware"):
            get_digest_window(datetime(2026, 11, 6, 12))

    def test_empty_articles_do_not_call_generator(self) -> None:
        def unexpected_generator(*args, **kwargs):
            raise AssertionError("generator should not be called")

        result = generate_digest_for_articles((), generator=unexpected_generator)

        self.assertIsNone(result)

    def test_calls_generator_with_bounded_content_and_allowed_urls(self) -> None:
        article = self.session.query(Article).filter_by(video_id="lower-bound").one()
        captured = {}

        def generator(content, *, allowed_urls, settings):
            captured["content"] = content
            captured["allowed_urls"] = allowed_urls
            return GeneratedDigest(
                subject="Subject",
                entries=(
                    DigestEntry(
                        title=article.title,
                        summary="Summary",
                        url=article.url,
                    ),
                ),
            )

        result = generate_digest_for_articles(
            (article,),
            generator=generator,
            settings=object(),
        )

        self.assertIn("Content:\ndescription", captured["content"])
        self.assertEqual(captured["allowed_urls"], (article.url,))
        self.assertEqual(result.subject, "Subject")

    def test_allowed_urls_match_only_articles_included_within_total_limit(self) -> None:
        articles = tuple(
            Article(
                source_id=self.source.id,
                video_id=f"video-{index}",
                title=f"Video {index}",
                url=f"https://youtu.be/video-{index}",
                description="x" * 12_000,
                published_at=self.now,
            )
            for index in range(5)
        )
        captured = {}

        def generator(content, *, allowed_urls, settings):
            captured["content"] = content
            captured["allowed_urls"] = allowed_urls
            return GeneratedDigest(
                subject="Subject",
                entries=(
                    DigestEntry(title="First", summary="Summary", url=allowed_urls[0]),
                ),
            )

        generate_digest_for_articles(articles, generator=generator)

        self.assertLessEqual(len(captured["content"]), 48_000)
        self.assertLess(len(captured["allowed_urls"]), len(articles))
        self.assertNotIn(articles[-1].url, captured["allowed_urls"])


if __name__ == "__main__":
    unittest.main()
