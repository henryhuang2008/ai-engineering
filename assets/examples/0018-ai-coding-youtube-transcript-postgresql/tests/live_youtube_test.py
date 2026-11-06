import os
import unittest
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from math import isfinite
from pathlib import Path
from urllib.error import HTTPError

from app.ingest.youtube import (
    YouTubeChannelFeed,
    fetch_video_content,
    fetch_channel_feed,
    parse_channel_feed,
)

CHANNEL_ID = "UCn8ujwUInbJkBhffxqAPBVQ"
LOOKBACK_HOURS = float(os.getenv("YOUTUBE_LOOKBACK_HOURS", "180"))
DUMMY_FEED_PATH = (
    Path(__file__).resolve().parents[1]
    / "app"
    / "data"
    / "dummy_youtube_feed.xml"
)


def load_dummy_feed(now: datetime, lookback_hours: float) -> YouTubeChannelFeed:
    feed = parse_channel_feed(CHANNEL_ID, DUMMY_FEED_PATH.read_bytes())
    sample_published_at = now - timedelta(hours=min(1, lookback_hours / 2))
    return replace(
        feed,
        videos=tuple(
            replace(video, published_at=sample_published_at)
            for video in feed.videos
        ),
    )


class LatestYouTubeVideosTests(unittest.TestCase):
    def test_prints_channel_videos_published_within_lookback_hours(self) -> None:
        if not isfinite(LOOKBACK_HOURS) or LOOKBACK_HOURS <= 0:
            self.fail("YOUTUBE_LOOKBACK_HOURS must be a positive finite number")

        now = datetime.now(UTC)
        try:
            feed = fetch_channel_feed(CHANNEL_ID)
        except HTTPError as error:
            if error.code != 404:
                raise
            feed = load_dummy_feed(now, LOOKBACK_HOURS)
            print("\nYouTube returned HTTP 404; using dummy fixture data for this test.")

        cutoff = now - timedelta(hours=LOOKBACK_HOURS)
        recent_videos = sorted(
            (
                video
                for video in feed.videos
                if video.published_at is not None
                and cutoff <= video.published_at <= now
            ),
            key=lambda video: video.published_at,
            reverse=True,
        )

        self.assertEqual(feed.channel_id, CHANNEL_ID)
        print(
            f"\nChannel: {feed.title} ({feed.channel_id})"
            f"\nLook-back: {LOOKBACK_HOURS:g} hours"
            f"\nMatching videos: {len(recent_videos)}"
        )
        for video in recent_videos:
            content = fetch_video_content(video)
            print(
                f"\n{video.title}"
                f"\n  Published: {video.published_at.isoformat()}"
                f"\n  Video ID:  {video.video_id}"
                f"\n  URL:       {video.url}"
                f"\n  Content source: {content.source}"
                f"\n  Content:   {content.text}"
            )
            if content.transcript:
                print(
                    f"  Transcript language: {content.transcript.language} "
                    f"({content.transcript.language_code})"
                    f"\n  Generated captions: {content.transcript.is_generated}"
                )


if __name__ == "__main__":
    unittest.main()
