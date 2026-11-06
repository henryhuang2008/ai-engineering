from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Sequence

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.database.models import Article, Source
from app.ingest.youtube import (
    CHANNEL_ID_PATTERN,
    YOUTUBE_FEED_URL,
    YouTubeChannelFeed,
    fetch_channel_feed,
    parse_channel_feed,
)

DATA_DIRECTORY = Path(__file__).resolve().parents[1] / "data"
CHANNELS_FILE = DATA_DIRECTORY / "channels.json"
DUMMY_FEED_FILE = DATA_DIRECTORY / "dummy_youtube_feed.xml"


@dataclass(frozen=True)
class ChannelConfig:
    name: str
    channel_id: str

    @property
    def feed_url(self) -> str:
        return f"{YOUTUBE_FEED_URL}?channel_id={self.channel_id}"


@dataclass(frozen=True)
class FeedFailure:
    channel_id: str
    channel_name: str
    error: str


@dataclass(frozen=True)
class IngestionReport:
    channels_synced: int
    feeds_succeeded: int
    videos_upserted: int
    failures: tuple[FeedFailure, ...]


def load_channels(path: Path = CHANNELS_FILE) -> tuple[ChannelConfig, ...]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"Could not load channel configuration {path}: {error}") from error

    if not isinstance(data, list):
        raise ValueError("Channel configuration must be a JSON array")

    channels: list[ChannelConfig] = []
    seen_ids: set[str] = set()
    for index, item in enumerate(data):
        if not isinstance(item, dict):
            raise ValueError(f"Channel entry {index} must be a JSON object")
        name = item.get("name")
        channel_id = item.get("channel_id")
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"Channel entry {index} must have a non-empty name")
        if not isinstance(channel_id, str) or not CHANNEL_ID_PATTERN.fullmatch(
            channel_id
        ):
            raise ValueError(f"Channel entry {index} has an invalid channel_id")
        if channel_id in seen_ids:
            raise ValueError(f"Duplicate channel_id in configuration: {channel_id}")
        seen_ids.add(channel_id)
        channels.append(ChannelConfig(name=name.strip(), channel_id=channel_id))

    if not channels:
        raise ValueError("Channel configuration must contain at least one channel")
    return tuple(channels)


def fetch_dummy_channel_feed(
    channel_id: str,
    *,
    path: Path = DUMMY_FEED_FILE,
) -> YouTubeChannelFeed:
    try:
        content = path.read_bytes()
    except OSError as error:
        raise OSError(f"Could not read dummy YouTube feed {path}: {error}") from error
    return parse_channel_feed(channel_id, content)


def _insert_for_dialect(session: Session, model: type[Source] | type[Article]):
    dialect_name = session.get_bind().dialect.name
    if dialect_name == "postgresql":
        return postgresql_insert(model)
    if dialect_name == "sqlite":
        return sqlite_insert(model)
    raise RuntimeError(f"Unsupported database dialect for ingestion: {dialect_name}")


def _fetch_feeds(
    channels: Sequence[ChannelConfig],
    feed_fetcher: Callable[[str], YouTubeChannelFeed],
) -> tuple[list[tuple[ChannelConfig, YouTubeChannelFeed]], list[FeedFailure]]:
    feeds: list[tuple[ChannelConfig, YouTubeChannelFeed]] = []
    failures: list[FeedFailure] = []
    for channel in channels:
        try:
            feed = feed_fetcher(channel.channel_id)
            if feed.channel_id != channel.channel_id:
                raise ValueError(
                    f"Feed channel ID {feed.channel_id!r} did not match "
                    f"configured ID {channel.channel_id!r}"
                )
        except (OSError, ValueError) as error:
            failures.append(
                FeedFailure(
                    channel_id=channel.channel_id,
                    channel_name=channel.name,
                    error=f"{type(error).__name__}: {error}",
                )
            )
        else:
            feeds.append((channel, feed))
    return feeds, failures


def ingest_channels(
    session: Session,
    channels: Sequence[ChannelConfig],
    *,
    feed_fetcher: Callable[[str], YouTubeChannelFeed] = fetch_channel_feed,
) -> IngestionReport:
    if not channels:
        raise ValueError("At least one channel is required for ingestion")
    channel_ids = [channel.channel_id for channel in channels]
    if len(channel_ids) != len(set(channel_ids)):
        raise ValueError("Channel configuration contains duplicate channel IDs")

    feeds, failures = _fetch_feeds(channels, feed_fetcher)
    with session.begin():
        for channel in channels:
            source_insert = _insert_for_dialect(session, Source).values(
                kind="youtube",
                name=channel.name,
                channel_id=channel.channel_id,
                feed_url=channel.feed_url,
                active=True,
            )
            session.execute(
                source_insert.on_conflict_do_update(
                    index_elements=[Source.channel_id],
                    set_={
                        "kind": source_insert.excluded.kind,
                        "name": source_insert.excluded.name,
                        "feed_url": source_insert.excluded.feed_url,
                        "active": True,
                    },
                )
            )

        session.execute(
            update(Source)
            .where(Source.channel_id.not_in(channel_ids))
            .values(active=False)
        )

        source_ids = dict(
            session.execute(
                select(Source.channel_id, Source.id).where(
                    Source.channel_id.in_(channel_ids)
                )
            ).all()
        )
        videos_upserted = 0
        seen_video_ids: set[str] = set()
        for channel, feed in feeds:
            for video in feed.videos:
                if video.video_id in seen_video_ids:
                    continue
                seen_video_ids.add(video.video_id)
                article_insert = _insert_for_dialect(session, Article).values(
                    source_id=source_ids[channel.channel_id],
                    video_id=video.video_id,
                    title=video.title,
                    url=video.url,
                    description=video.description,
                    published_at=video.published_at,
                    fetched_at=func.now(),
                )
                session.execute(
                    article_insert.on_conflict_do_update(
                        index_elements=[Article.video_id],
                        set_={
                            "source_id": article_insert.excluded.source_id,
                            "title": article_insert.excluded.title,
                            "url": article_insert.excluded.url,
                            "description": article_insert.excluded.description,
                            "published_at": article_insert.excluded.published_at,
                            "fetched_at": func.now(),
                        },
                    )
                )
                videos_upserted += 1

    return IngestionReport(
        channels_synced=len(channels),
        feeds_succeeded=len(feeds),
        videos_upserted=videos_upserted,
        failures=tuple(failures),
    )
