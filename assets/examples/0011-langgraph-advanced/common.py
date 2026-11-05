"""Shared model wiring for the research agent.

The model calls are live DeepSeek. Put the key in the environment or in `.env`
next to this script (copy `.env.example` first):

  PowerShell (this session):  $env:DEEPSEEK_API_KEY = "sk-..."
  PowerShell (persist):       setx DEEPSEEK_API_KEY "sk-..."   # reopen the terminal
  .env:                       DEEPSEEK_API_KEY=sk-...

Get a key at https://platform.deepseek.com/api_keys. No key -> the script prints
these instructions and exits 1, never a guess.
"""

from __future__ import annotations

import os

import settings  # noqa: F401  (loads .env before anything reads os.environ)
from langchain_deepseek import ChatDeepSeek

MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-flash")
BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")


def missing_key_message() -> str:
    return (
        "DEEPSEEK_API_KEY is not set.\n"
        '  PowerShell (this session):  $env:DEEPSEEK_API_KEY = "sk-..."\n'
        '  PowerShell (persist):       setx DEEPSEEK_API_KEY "sk-..."   # reopen terminal\n'
        "  .env (this folder):         DEEPSEEK_API_KEY=sk-...\n"
        "  Get a key:                  https://platform.deepseek.com/api_keys"
    )


def build_model() -> ChatDeepSeek:
    """Return a live ChatDeepSeek handle, or explain exactly what is missing."""
    key = os.getenv("DEEPSEEK_API_KEY")
    if not key:
        raise RuntimeError(missing_key_message())

    return ChatDeepSeek(
        model=MODEL,
        api_key=key,
        api_base=BASE_URL,
        temperature=0,
        max_retries=2,
        timeout=90,
        # Graph wiring, not reasoning traces: keep the six calls short and cheap.
        extra_body={"thinking": {"type": "disabled"}},
    )
