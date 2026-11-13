"""Create the tables and one customer, then print the CUSTOMER_ID to use.

    uv run python seed.py
    uv run python seed.py --first-name Ada --last-name Lovelace --email ada@example.com

Safe to run twice: it only inserts a customer when the table is empty.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT))

from mcps.local_servers.db import (  # noqa: E402  (needs .env loaded first)
    Base,
    DBCustomer,
    SessionLocal,
    engine,
)


def reconfigure_console() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def main() -> int:
    reconfigure_console()

    parser = argparse.ArgumentParser(description="Create tables and a demo customer.")
    parser.add_argument("--first-name", default="Henry")
    parser.add_argument("--last-name", default="Huang")
    parser.add_argument("--email", default="henry@example.com")
    args = parser.parse_args()

    print(f"database: {engine.url.render_as_string(hide_password=True)}")
    Base.metadata.create_all(engine)
    print("tables  : customers, expenses (created if missing)")

    with SessionLocal() as session:
        existing = session.query(DBCustomer).first()
        if existing is not None:
            customer = existing
            print("customer: already exists, reusing it")
        else:
            customer = DBCustomer(
                first_name=args.first_name,
                last_name=args.last_name,
                email=args.email,
            )
            session.add(customer)
            session.commit()
            session.refresh(customer)
            print("customer: created")

    print(f"\nCUSTOMER_ID = {customer.id}\n")
    print("Put it in .env:")
    print(f"  CUSTOMER_ID={customer.id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
