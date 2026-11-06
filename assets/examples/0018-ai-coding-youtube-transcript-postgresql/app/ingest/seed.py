from __future__ import annotations

import argparse
import sys

from app.database.session import SessionLocal
from app.ingest.sync import (
    fetch_dummy_channel_feed,
    ingest_channels,
    load_channels,
)
from app.ingest.youtube import fetch_channel_feed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Fetch YouTube RSS feeds and upsert channels and videos."
    )
    parser.add_argument(
        "--dummy-data",
        action="store_true",
        help="Use app/data/dummy_youtube_feed.xml instead of requesting YouTube.",
    )
    args = parser.parse_args(argv)
    feed_fetcher = fetch_dummy_channel_feed if args.dummy_data else fetch_channel_feed

    try:
        channels = load_channels()
        with SessionLocal() as session:
            report = ingest_channels(
                session,
                channels,
                feed_fetcher=feed_fetcher,
            )
    except (OSError, ValueError, RuntimeError) as error:
        print(f"YouTube ingestion failed: {error}", file=sys.stderr)
        return 1

    if args.dummy_data:
        print("Used dummy RSS data; no YouTube RSS requests were made.")
    print(
        f"Synced {report.channels_synced} channels; "
        f"{report.feeds_succeeded} feeds succeeded; "
        f"{report.videos_upserted} videos upserted."
    )
    for failure in report.failures:
        print(
            f"Feed failed for {failure.channel_name} "
            f"({failure.channel_id}): {failure.error}",
            file=sys.stderr,
        )
    return 1 if report.failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
