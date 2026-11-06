import unittest
from datetime import UTC, datetime

from app.ingest.youtube import parse_channel_feed

CHANNEL_ID = "UC_x5XG1OV2P6uZZ5FSM9Ttw"


class ParseChannelFeedTests(unittest.TestCase):
    def test_parses_channel_and_video_fields(self) -> None:
        content = f"""<?xml version="1.0" encoding="UTF-8"?>
        <feed xmlns="http://www.w3.org/2005/Atom"
              xmlns:yt="http://www.youtube.com/xml/schemas/2015">
          <title>Example Channel</title>
          <yt:channelId>{CHANNEL_ID}</yt:channelId>
          <entry>
            <id>yt:video:abc123</id>
            <yt:videoId>abc123</yt:videoId>
            <title>Example video</title>
            <link rel="alternate" href="https://www.youtube.com/watch?v=abc123"/>
            <published>2026-11-05T12:30:00+00:00</published>
            <media:group xmlns:media="http://search.yahoo.com/mrss/">
              <media:description>Example description</media:description>
            </media:group>
          </entry>
        </feed>
        """.encode()

        feed = parse_channel_feed(CHANNEL_ID, content)

        self.assertEqual(feed.title, "Example Channel")
        self.assertEqual(len(feed.videos), 1)
        video = feed.videos[0]
        self.assertEqual(video.video_id, "abc123")
        self.assertEqual(video.title, "Example video")
        self.assertEqual(video.url, "https://www.youtube.com/watch?v=abc123")
        self.assertEqual(video.description, "Example description")
        self.assertEqual(
            video.published_at, datetime(2026, 11, 5, 12, 30, tzinfo=UTC)
        )

    def test_rejects_mismatched_feed_channel_id(self) -> None:
        content = f"""<feed xmlns="http://www.w3.org/2005/Atom"
                            xmlns:yt="http://www.youtube.com/xml/schemas/2015">
          <yt:channelId>UC0000000000000000000000</yt:channelId>
        </feed>""".encode()

        with self.assertRaisesRegex(ValueError, "does not match"):
            parse_channel_feed(CHANNEL_ID, content)

    def test_accepts_feed_channel_id_without_uc_prefix(self) -> None:
        content = f"""<feed xmlns="http://www.w3.org/2005/Atom"
                            xmlns:yt="http://www.youtube.com/xml/schemas/2015">
          <title>Example Channel</title>
          <yt:channelId>{CHANNEL_ID.removeprefix("UC")}</yt:channelId>
        </feed>""".encode()

        feed = parse_channel_feed(CHANNEL_ID, content)

        self.assertEqual(feed.channel_id, CHANNEL_ID)
        self.assertEqual(feed.title, "Example Channel")


if __name__ == "__main__":
    unittest.main()
