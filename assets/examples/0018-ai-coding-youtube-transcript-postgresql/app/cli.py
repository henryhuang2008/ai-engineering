from __future__ import annotations

import argparse

from app.config import get_settings
from app.database.migrate import upgrade_to_head
from app.database.session import SessionLocal
from app.digest.preview import preview_daily_digest, saved_articles_json
from app.digest.run import run_daily_digest
from app.ingest.seed import main as seed_main


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the Daily YouTube Digest.")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("migrate", help="Apply database migrations.")

    seed_parser = commands.add_parser("seed", help="Ingest configured YouTube feeds.")
    seed_parser.add_argument("--dummy-data", action="store_true")

    run_parser = commands.add_parser(
        "run",
        help="Generate and print a digest preview from saved database records.",
    )
    run_parser.add_argument(
        "--send-email",
        action="store_true",
        help="Send the generated digest instead of printing a preview.",
    )
    run_parser.add_argument(
        "--raw",
        action="store_true",
        help="Print saved article records as JSON without calling DeepSeek.",
    )
    run_parser.add_argument("--force", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "migrate":
        upgrade_to_head()
        print("Database migrations are up to date.")
        return 0
    if args.command == "seed":
        seed_args = ["--dummy-data"] if args.dummy_data else []
        return seed_main(seed_args)

    if args.force and not args.send_email:
        parser.error("--force requires --send-email")
    if args.raw and args.send_email:
        parser.error("--raw cannot be combined with --send-email")

    settings = get_settings()
    with SessionLocal() as session:
        if args.raw:
            print(saved_articles_json(session))
            return 0
        if not args.send_email:
            preview = preview_daily_digest(session, settings=settings)
            print(f"Digest preview ({preview.article_count} videos):")
            print()
            print(preview.text_body)
            return 0

        result = run_daily_digest(session, force=args.force, settings=settings)

    if result.skipped:
        print(f"Digest {result.digest_id} was already sent today; skipped.")
    elif result.status == "sent":
        print(f"Digest {result.digest_id} sent successfully.")
    elif result.status == "empty":
        print(f"Digest {result.digest_id} recorded; no recent videos to send.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
