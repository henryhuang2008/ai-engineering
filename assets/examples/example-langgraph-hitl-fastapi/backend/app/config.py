"""Backend settings: where .env lives, which model to call.

Importing this module loads `backend/.env` (if it exists) before anything reads
`DEEPSEEK_API_KEY`. It is imported by `app.graph` and `app.mcp_agent`, so the
API, the notebooks and the MCP agent all see the same environment regardless of
which one is imported first.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BACKEND_DIR / ".env")

# `deepseek-flash` also supports tool calls, which the MCP agent needs.
MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-flash")
