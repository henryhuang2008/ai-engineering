"""Load `.env` once, before any module reads os.environ.

Copy `.env.example` to `.env` in this folder and fill in the keys you have.
Existing environment variables win over `.env` values.
"""

from __future__ import annotations

from dotenv import load_dotenv

load_dotenv()
