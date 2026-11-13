"""Print a join token for the local LiveKit server.

    uv run python token.py                     # room "expenses", identity "you"
    uv run python token.py expenses alice

Paste the token into client/index.html, or into the LiveKit Agents Playground.
"""

from __future__ import annotations

import os
import sys

from dotenv import load_dotenv
from livekit import api


def main() -> int:
    load_dotenv()

    room = sys.argv[1] if len(sys.argv) > 1 else "expenses"
    identity = sys.argv[2] if len(sys.argv) > 2 else "you"

    key = os.environ.get("LIVEKIT_API_KEY", "devkey")
    secret = os.environ.get("LIVEKIT_API_SECRET", "secret")

    token = (
        api.AccessToken(key, secret)
        .with_identity(identity)
        .with_name(identity)
        .with_grants(api.VideoGrants(room_join=True, room=room))
        .to_jwt()
    )
    print(token)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
