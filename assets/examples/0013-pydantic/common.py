"""One ChatDeepSeek builder for the live structured-output script.

`basics.py` needs no key. Only `structured.py` does:

  PowerShell (this session):  $env:DEEPSEEK_API_KEY = "sk-..."
  .env (this folder):         DEEPSEEK_API_KEY=sk-...

Get a key at https://platform.deepseek.com/api_keys. No key -> a clear message
and exit 1, never a guess.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv
from langchain_deepseek import ChatDeepSeek

load_dotenv()

MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-flash")
BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")


def missing_key_message() -> str:
    return (
        "DEEPSEEK_API_KEY is not set.\n"
        '  PowerShell (this session):  $env:DEEPSEEK_API_KEY = "sk-..."\n'
        "  .env (this folder):         DEEPSEEK_API_KEY=sk-...\n"
        "  Get a key:                  https://platform.deepseek.com/api_keys"
    )


def build_model() -> ChatDeepSeek:
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
        extra_body={"thinking": {"type": "disabled"}},
    )
