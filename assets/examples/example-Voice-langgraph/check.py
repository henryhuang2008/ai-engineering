"""Is this machine ready? One command, no audio, no API calls.

    uv run python check.py

It checks keys, the database, the MCP server and the local STT model, and tells
you exactly which command fixes anything that is missing.
"""

from __future__ import annotations

import asyncio
import os
import platform
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")

OK = "OK  "
NO = "MISS"
WARN = "WARN"

problems: list[str] = []


def reconfigure_console() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def row(label: str, value: str, status: str = "") -> None:
    print(f"  {status:<4} {label:<22} {value}")


def mask(value: str) -> str:
    if not value:
        return "(not set)"
    return value[:4] + "..." + value[-4:] if len(value) > 10 else "set"


def check_keys() -> None:
    print("\nkeys")
    deepseek = os.environ.get("DEEPSEEK_API_KEY", "")
    row("DEEPSEEK_API_KEY", mask(deepseek), OK if deepseek else NO)
    if not deepseek:
        problems.append('set DEEPSEEK_API_KEY (https://platform.deepseek.com/api_keys)')

    provider = (os.environ.get("TTS_PROVIDER", "").strip() or "qwen").lower()
    valid = provider in {"qwen", "elevenlabs"}
    row("TTS_PROVIDER", provider, OK if valid else NO)
    if not valid:
        problems.append("TTS_PROVIDER must be 'qwen' or 'elevenlabs'")

    if provider == "elevenlabs":
        eleven = os.environ.get("ELEVENLABS_API_KEY", "")
        row("ELEVENLABS_API_KEY", mask(eleven), OK if eleven else NO)
        if not eleven:
            problems.append('set ELEVENLABS_API_KEY (https://elevenlabs.io/app/settings/api-keys)')
        row("ELEVENLABS_VOICE_ID", os.environ.get("ELEVENLABS_VOICE_ID") or "(default: Rachel)")
        row("ELEVENLABS_MODEL", os.environ.get("ELEVENLABS_MODEL") or "eleven_flash_v2_5")
    else:
        dashscope = os.environ.get("DASHSCOPE_API_KEY", "")
        row("DASHSCOPE_API_KEY", mask(dashscope), OK if dashscope else NO)
        if not dashscope:
            problems.append("set DASHSCOPE_API_KEY (https://bailian.console.aliyun.com)")
        row("DASHSCOPE_REGION", os.environ.get("DASHSCOPE_REGION") or "beijing")
        row("QWEN_TTS_MODEL", os.environ.get("QWEN_TTS_MODEL") or "qwen3-tts-flash")
        row("QWEN_TTS_VOICE", os.environ.get("QWEN_TTS_VOICE") or "Cherry")
        row("QWEN_TTS_LANGUAGE", os.environ.get("QWEN_TTS_LANGUAGE") or "Auto")

    row("DEEPSEEK_MODEL", os.environ.get("DEEPSEEK_MODEL") or "deepseek-flash")
    row("WHISPER_MODEL", os.environ.get("WHISPER_MODEL") or "small")


def check_python() -> None:
    print("\npython")
    row("interpreter", f"{platform.python_version()} ({platform.system()} {platform.release()})",
        OK if sys.version_info >= (3, 12) else NO)
    if sys.version_info < (3, 12):
        problems.append("use Python 3.12 or newer")

    try:
        import importlib.metadata as meta

        for package in (
            "langgraph",
            "langchain-deepseek",
            "langchain-mcp-adapters",
            "mcp",
            "faster-whisper",
            "sqlalchemy",
            "psycopg",
            "sounddevice",
        ):
            try:
                row(package, meta.version(package), OK)
            except meta.PackageNotFoundError:
                row(package, "not installed", NO)
                problems.append(f"uv sync  (missing {package})")
    except Exception as exc:  # pragma: no cover - defensive
        row("packages", str(exc), NO)


def check_database() -> None:
    print("\ndatabase")
    uri = os.environ.get("SUPABASE_URI", "") or os.environ.get("DATABASE_URL", "")
    if not uri:
        row("SUPABASE_URI", "(not set)", NO)
        problems.append("set SUPABASE_URI in .env (Project settings -> Database -> Connection string)")
        return

    shown = uri.split("@")[-1] if "@" in uri else uri
    row("SUPABASE_URI", f"...@{shown}", OK)

    try:
        from sqlalchemy import text

        sys.path.insert(0, str(ROOT))
        from mcps.local_servers.db import engine

        with engine.connect() as connection:
            connection.execute(text("select 1"))
            tables = [
                r[0]
                for r in connection.execute(
                    text("select tablename from pg_tables where schemaname = 'public'")
                )
            ]
            row("tables", ", ".join(sorted(tables)) or "(none)", OK if tables else NO)
            if "customers" in tables and "expenses" in tables:
                customers = connection.execute(text("select count(*) from customers")).scalar()
                expenses = connection.execute(text("select count(*) from expenses")).scalar()
                row("rows", f"{customers} customers, {expenses} expenses", OK)
                if not customers:
                    problems.append("run `uv run python seed.py` to create a customer")
            else:
                problems.append("run `uv run python seed.py` (or generate_tables.sql in Supabase)")
        row("customer", os.environ.get("CUSTOMER_ID") or "(CUSTOMER_ID not set)", OK if os.environ.get("CUSTOMER_ID") else WARN)
        if not os.environ.get("CUSTOMER_ID"):
            problems.append("run `uv run python seed.py` and copy CUSTOMER_ID into .env")
    except Exception as exc:
        row("connect", f"{type(exc).__name__}: {str(exc)[:90]}", NO)
        problems.append("the database is not reachable - check SUPABASE_URI / network")


async def check_mcp() -> None:
    print("\nmcp server")
    try:
        from mcp_tools import load_tools

        tools = await load_tools()
        row("tools", ", ".join(tool.name for tool in tools) or "(none)", OK if tools else NO)
        if not tools:
            problems.append("the MCP server returned no tools - check mcps/local_servers/db.py")
    except Exception as exc:
        row("start", f"{type(exc).__name__}: {str(exc)[:90]}", NO)
        problems.append("the MCP server did not start - see the traceback above")


def check_stt_model() -> None:
    print("\nspeech to text")
    provider = (os.environ.get("STT_PROVIDER", "").strip() or "whisper").lower()
    valid = provider in {"whisper", "qwen"}
    row("STT_PROVIDER", provider, OK if valid else NO)
    if not valid:
        problems.append("STT_PROVIDER must be 'whisper' or 'qwen'")
        return

    if provider == "qwen":
        row("QWEN_ASR_MODEL", os.environ.get("QWEN_ASR_MODEL") or "qwen3-asr-flash")
        key = os.environ.get("DASHSCOPE_API_KEY", "")
        row("DASHSCOPE_API_KEY", mask(key), OK if key else NO)
        if not key:
            problems.append("STT_PROVIDER=qwen needs DASHSCOPE_API_KEY")
        row("device", "cloud (DashScope)", OK)
        return

    name = os.environ.get("WHISPER_MODEL") or "small"
    try:
        from huggingface_hub import constants

        hub = Path(constants.HF_HUB_CACHE) / f"models--Systran--faster-whisper-{name}"
        cached = (hub / "snapshots").is_dir()
    except Exception:
        cached = False
    row(f"faster-whisper {name}", "cached locally" if cached else "will download on first run",
        OK if cached else WARN)
    row("device", "CPU int8 (no CUDA)" if not _has_cuda() else "CUDA float16", OK)


def _has_cuda() -> bool:
    try:
        import ctranslate2

        return ctranslate2.get_cuda_device_count() > 0
    except Exception:
        return False


def main() -> int:
    reconfigure_console()
    print(f"voice agent check - {ROOT}")

    check_python()
    check_keys()
    check_database()
    asyncio.run(check_mcp())
    check_stt_model()

    print()
    if problems:
        print(f"{len(problems)} thing(s) to fix:")
        for index, problem in enumerate(problems, 1):
            print(f"  {index}. {problem}")
        return 1

    print("Everything is ready. Next:")
    print("  uv run python smoke.py        # one turn, no microphone")
    print("  uv run python main.py         # talk to it")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
