"""Shared paths, constants and key checks for the lesson 7 lab.

One place decides where the corpus lives, where the index lives, which
embedding model is used and how wide its vectors are. Everything else imports
from here, so changing the embedder is a one-file change - which is exactly
what lesson 6 warns you about.
"""

from __future__ import annotations

import os
from pathlib import Path

HERE = Path(__file__).resolve().parent
DOCS_DIR = HERE / "docs"
INDEX_DIR = HERE / "index"
DB_DIR = INDEX_DIR / "lancedb"
TABLE_NAME = "chunks"

# Qwen text-embedding-v4. The dimension is fixed when the index is built:
# changing it means rebuilding the table, not migrating it.
EMBED_MODEL = "text-embedding-v4"
EMBED_DIM = 1024
EMBED_BATCH = 10  # DashScope accepts at most 10 texts per request
MAX_CHUNK_TOKENS = 512

# Copy the region-specific base URL from your DashScope console if this one
# returns 401. Keys are region-specific.
DEFAULT_BASE_URL = "https://dashscope.aliyuncs.com/api/v1"

SUPPORTED_SUFFIXES = {".pdf", ".docx", ".pptx", ".xlsx", ".html", ".md"}

KEY_HELP = {
    "DASHSCOPE_API_KEY": (
        "indexing and search need Qwen text-embedding-v4",
        "https://bailian.console.alibabacloud.com/",
    ),
    "DEEPSEEK_API_KEY": (
        "the answer step needs DeepSeek",
        "https://platform.deepseek.com/api_keys",
    ),
}


class MissingKey(RuntimeError):
    """Raised with copy-pasteable setup instructions, never a stack trace."""


def missing_keys_message(names: list[str]) -> str:
    lines: list[str] = []
    for name in names:
        what, where = KEY_HELP[name]
        lines.append(f"{name} is not set - {what}.")
        lines.append(f'  PowerShell (this session):  $env:{name} = "sk-..."')
        lines.append(
            f'  PowerShell (persist):        setx {name} "sk-..."   # reopen the terminal'
        )
        lines.append(f"  Get a key:                  {where}")
        lines.append("")
    lines.append(
        "Optional, region-specific endpoint (if the default returns 401):\n"
        '  $env:DASHSCOPE_BASE_URL = "https://<your-region-host>/api/v1"'
    )
    return "\n".join(lines)


def require_keys(names: list[str]) -> None:
    missing = [name for name in names if not os.environ.get(name)]
    if missing:
        raise MissingKey(missing_keys_message(missing))


def docs() -> list[Path]:
    """Every supported document under docs/, in a stable order."""
    if not DOCS_DIR.exists():
        raise SystemExit(f"corpus not found: {DOCS_DIR}")
    return sorted(
        path
        for path in DOCS_DIR.rglob("*")
        if path.is_file() and path.suffix.lower() in SUPPORTED_SUFFIXES
    )
