"""Shared model wiring for the two scripts in this lab.

Both scripts talk to the live DeepSeek API. Set DEEPSEEK_API_KEY first:

  PowerShell (this session):  $env:DEEPSEEK_API_KEY = "sk-..."
  PowerShell (persist):       setx DEEPSEEK_API_KEY "sk-..."   # reopen the terminal

Get a key at https://platform.deepseek.com/api_keys. No key -> the scripts print
these instructions and exit 1, never a guess.
"""

from __future__ import annotations

import os

from langchain_deepseek import ChatDeepSeek

MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-flash")
BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")


def missing_key_message() -> str:
    return (
        "DEEPSEEK_API_KEY is not set.\n"
        '  PowerShell (this session):  $env:DEEPSEEK_API_KEY = "sk-..."\n'
        '  PowerShell (persist):       setx DEEPSEEK_API_KEY "sk-..."   # reopen terminal\n'
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
        timeout=60,
        # This lab is about graph wiring, not reasoning traces: keep calls short.
        # Delete this line to watch the model think before it answers.
        extra_body={"thinking": {"type": "disabled"}},
    )
