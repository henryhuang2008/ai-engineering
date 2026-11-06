import unittest
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from urllib.error import URLError

from app.database.models import Article, Base, Source
from app.ingest.sync import (
    ChannelConfig,
    fetch_dummy_channel_feed,
    ingest_channels,
    load_channels,
)
from app.ingest.youtube import YouTubeChannelFeed, YouTubeVideo

CHANNEL_ID = "UC_x5XG1OV2P6uZZ5FSM9Ttw"
OTHER_CHANNEL_ID = "UCn8ujwUInbJkBhffxqAPBVQ"


class LoadChannelsTests(unittest.TestCase):
    def test_loads_valid_channel_entries(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "channels.json"
            path.write_text(
                f'[{{"name":" Example ","channel_id":"{CHANNEL_ID}"}}]',
                encoding="utf-8",
            )

            channels = load_channels(path)

        self.assertEqual(channels, (ChannelConfig("Example", CHANNEL_ID),))
        self.assertEqual(
            channels[0].feed_url,
            f"https://www.youtube.com/feeds/videos.xml?channel_id={CHANNEL_ID}",
        )

    def test_rejects_missing_names_and_duplicate_channel_ids(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "channels.json"
            path.write_text(f'[{{"channel_id":"{CHANNEL_ID}"}}]', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "non-empty name"):
                load_channels(path)

            path.write_text(
                f'[{{"name":"A","channel_id":"{CHANNEL_ID}"}},'
                f'{{"name":"B","channel_id":"{CHANNEL_ID}"}}]',
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "Duplicate channel_id"):
                load_channels(path)


class DummyFeedTests(unittest.TestCase):
    def test_loads_dummy_feed_without_network(self) -> None:
        feed = fetch_dummy_channel_feed(OTHER_CHANNEL_ID)

        self.assertEqual(feed.channel_id, OTHER_CHANNEL_ID)
        self.assertEqual(feed.title, "Sample YouTube Channel (Dummy Data)")
        self.assertEqual(len(feed.videos), 2)

    def test_rejects_dummy_feed_for_unconfigured_channel(self) -> None:
        with self.assertRaisesRegex(ValueError, "does not match"):
            fetch_dummy_channel_feed(CHANNEL_ID)


class IngestChannelsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.session = Session(self.engine)

    def tearDown(self) -> None:
        self.session.close()
        self.engine.dispose()

    def test_ingests_dummy_feed_and_reads_inserted_records(self) -> None:
        channel = load_channels()[0]
        report = ingest_channels(
            self.session,
            [channel],
            feed_fetcher=fetch_dummy_channel_feed,
        )

        source = self.session.scalar(
            select(Source).where(Source.channel_id == channel.channel_id)
        )
        articles = self.session.scalars(
            select(Article).order_by(Article.video_id)
        ).all()

        self.assertEqual(report.channels_synced, 1)
        self.assertEqual(report.feeds_succeeded, 1)
        self.assertEqual(report.videos_upserted, 2)
        self.assertEqual(source.name, channel.name)
        self.assertEqual(source.kind, "youtube")
        self.assertTrue(source.active)
        self.assertEqual(len(articles), 2)
        self.assertEqual(
            {article.video_id for article in articles},
            {"mz73sVy6-X8", "E8zpgNPx8jE"},
        )
        self.assertIn(
            "Sample video for offline testing",
            {article.title for article in articles},
        )
        self.assertTrue(
            all(article.source_id == source.id for article in articles)
        )

    def test_upserts_sources_and_articles_without_overwriting_transcript(self) -> None:
        channel = ChannelConfig("Example", CHANNEL_ID)
        published_at = datetime(2026, 11, 6, 10, tzinfo=UTC)
        feeds = {
            CHANNEL_ID: YouTubeChannelFeed(
                channel_id=CHANNEL_ID,
                title="RSS title",
                videos=(
                    YouTubeVideo(
                        video_id="video123",
                        title="First title",
                        url="https://youtu.be/video123",
                        description="First description",
                        published_at=published_at,
                    ),
                ),
            )
        }

        first_report = ingest_channels(
            self.session, [channel], feed_fetcher=feeds.__getitem__
        )
        article = self.session.scalar(select(Article))
        article.transcript = "Saved transcript"
        article.transcript_language = "en"
        article.transcript_is_generated = True
        self.session.commit()

        feeds[CHANNEL_ID] = YouTubeChannelFeed(
            channel_id=CHANNEL_ID,
            title="RSS title",
            videos=(
                YouTubeVideo(
                    video_id="video123",
                    title="Updated title",
                    url="https://youtu.be/video123",
                    description="Updated description",
                    published_at=published_at,
                ),
            ),
        )
        updated_channel = ChannelConfig("Renamed channel", CHANNEL_ID)
        second_report = ingest_channels(
            self.session, [updated_channel], feed_fetcher=feeds.__getitem__
        )

        self.session.expire_all()
        source = self.session.scalar(select(Source))
        articles = self.session.scalars(select(Article)).all()
        self.assertEqual(first_report.videos_upserted, 1)
        self.assertEqual(second_report.videos_upserted, 1)
        self.assertEqual(source.name, "Renamed channel")
        self.assertTrue(source.active)
        self.assertEqual(len(articles), 1)
        self.assertEqual(articles[0].title, "Updated title")
        self.assertEqual(articles[0].description, "Updated description")
        self.assertEqual(articles[0].transcript, "Saved transcript")
        self.assertEqual(articles[0].transcript_language, "en")
        self.assertTrue(articles[0].transcript_is_generated)

    def test_deactivates_removed_channels_and_reports_feed_failure(self) -> None:
        channel_a = ChannelConfig("Available", CHANNEL_ID)
        channel_b = ChannelConfig("Unavailable", OTHER_CHANNEL_ID)

        def fetcher(channel_id: str) -> YouTubeChannelFeed:
            if channel_id == OTHER_CHANNEL_ID:
                raise URLError("temporary network issue")
            return YouTubeChannelFeed(channel_id, "Available", ())

        report = ingest_channels(self.session, [channel_a, channel_b], feed_fetcher=fetcher)
        self.assertEqual(report.feeds_succeeded, 1)
        self.assertEqual(len(report.failures), 1)
        self.assertIn("temporary network issue", report.failures[0].error)

        next_report = ingest_channels(
            self.session,
            [channel_a],
            feed_fetcher=lambda channel_id: YouTubeChannelFeed(
                channel_id, "Available", ()
            ),
        )
        self.session.expire_all()
        sources = {
            source.channel_id: source
            for source in self.session.scalars(select(Source)).all()
        }
        self.assertEqual(next_report.failures, ())
        self.assertTrue(sources[CHANNEL_ID].active)
        self.assertFalse(sources[OTHER_CHANNEL_ID].active)


if __name__ == "__main__":
    unittest.main()
