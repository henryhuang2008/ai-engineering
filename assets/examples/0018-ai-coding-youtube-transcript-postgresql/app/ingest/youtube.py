from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.request import Request, urlopen

import feedparser

YOUTUBE_FEED_URL = "https://www.youtube.com/feeds/videos.xml"
CHANNEL_ID_PATTERN = re.compile(r"UC[A-Za-z0-9_-]{22}")


@dataclass(frozen=True)
class YouTubeVideo:
    video_id: str
    title: str
    url: str
    description: str
    published_at: datetime | None


@dataclass(frozen=True)
class YouTubeChannelFeed:
    channel_id: str
    title: str
    videos: tuple[YouTubeVideo, ...]


def parse_channel_feed(channel_id: str, content: bytes) -> YouTubeChannelFeed:
    if not CHANNEL_ID_PATTERN.fullmatch(channel_id):
        raise ValueError(f"Invalid YouTube channel ID: {channel_id!r}")

    parsed = feedparser.parse(content)
    if parsed.bozo:
        raise ValueError("Could not parse YouTube RSS feed") from parsed.bozo_exception

    feed_channel_id = parsed.feed.get("yt_channelid")
    if feed_channel_id and feed_channel_id not in {
        channel_id,
        channel_id.removeprefix("UC"),
    }:
        raise ValueError(
            f"RSS feed channel ID {feed_channel_id!r} does not match {channel_id!r}"
        )

    videos = []
    for entry in parsed.entries:
        video_id = entry.get("yt_videoid")
        if not video_id:
            entry_id = entry.get("id", "")
            if entry_id.startswith("yt:video:"):
                video_id = entry_id.removeprefix("yt:video:")
        if not video_id:
            raise ValueError("YouTube RSS entry is missing its video ID")

        published = entry.get("published_parsed")
        published_at = (
            datetime(*published[:6], tzinfo=UTC)
            if published is not None
            else None
        )
        videos.append(
            YouTubeVideo(
                video_id=video_id,
                title=entry.get("title", ""),
                url=entry.get("link", ""),
                description=entry.get("summary", ""),
                published_at=published_at,
            )
        )

    return YouTubeChannelFeed(
        channel_id=channel_id,
        title=parsed.feed.get("title", ""),
        videos=tuple(videos),
    )


def fetch_channel_feed(channel_id: str, *, timeout: float = 20) -> YouTubeChannelFeed:
    if not CHANNEL_ID_PATTERN.fullmatch(channel_id):
        raise ValueError(f"Invalid YouTube channel ID: {channel_id!r}")

    request = Request(
        f"{YOUTUBE_FEED_URL}?channel_id={channel_id}",
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
            "Accept": "application/atom+xml,application/xml;q=0.9,*/*;q=0.8",
        },
    )
    with urlopen(request, timeout=timeout) as response:
        content = response.read()

    return parse_channel_feed(channel_id, content)
