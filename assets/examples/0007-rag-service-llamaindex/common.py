"""Shared paths, constants and key checks for the LlamaIndex variant.

The corpus is reused from the main lesson 7 lab, so both examples answer over
exactly the same three documents.
"""

from __future__ import annotations

import os
from pathlib import Path

HERE = Path(__file__).resolve().parent
DOCS_DIR = HERE.parent / "0007-rag-service" / "docs"
INDEX_DIR = HERE / "index"
DB_DIR = INDEX_DIR / "lancedb"
TABLE_NAME = "chunks_llamaindex"

EMBED_MODEL = "text-embedding-v4"
EMBED_DIM = 1024
EMBED_BATCH = 10
MAX_CHUNK_TOKENS = 512
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
    if not DOCS_DIR.exists():
        raise SystemExit(
            f"corpus not found: {DOCS_DIR}\n"
            "This variant reuses the documents from 0007-rag-service/docs."
        )
    return sorted(
        path
        for path in DOCS_DIR.rglob("*")
        if path.is_file() and path.suffix.lower() in SUPPORTED_SUFFIXES
    )
