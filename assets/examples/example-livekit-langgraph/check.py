"""Is this machine ready? One command, no audio, no API calls.

    uv run python check.py

It checks packages, keys, the database, the MCP server and the LiveKit server,
and prints the command that fixes anything missing.
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


def check_python() -> None:
    print("\npython")
    row("interpreter", f"{platform.python_version()} ({platform.system()} {platform.release()})",
        OK if sys.version_info >= (3, 12) else NO)
    if sys.version_info < (3, 12):
        problems.append("use Python 3.12 or newer")

    try:
        import importlib.metadata as meta

        for package in (
            "livekit",
            "livekit-agents",
            "livekit-plugins-silero",
            "langgraph",
            "langchain-deepseek",
            "langchain-mcp-adapters",
            "mcp",
            "sqlalchemy",
            "psycopg",
        ):
            try:
                row(package, meta.version(package), OK)
            except meta.PackageNotFoundError:
                row(package, "not installed", NO)
                problems.append(f"uv sync  (missing {package})")
    except Exception as exc:  # pragma: no cover - defensive
        row("packages", str(exc), NO)


def check_keys() -> None:
    print("\nkeys")
    deepseek = os.environ.get("DEEPSEEK_API_KEY", "")
    row("DEEPSEEK_API_KEY", mask(deepseek), OK if deepseek else NO)
    if not deepseek:
        problems.append("set DEEPSEEK_API_KEY (https://platform.deepseek.com/api_keys)")

    dashscope = os.environ.get("DASHSCOPE_API_KEY", "")
    row("DASHSCOPE_API_KEY", mask(dashscope), OK if dashscope else NO)
    if not dashscope:
        problems.append("set DASHSCOPE_API_KEY (https://bailian.console.aliyun.com)")

    row("DASHSCOPE_REGION", os.environ.get("DASHSCOPE_REGION") or "beijing")
    row("QWEN_ASR_MODEL", os.environ.get("QWEN_ASR_MODEL") or "qwen3-asr-flash")
    row("QWEN_TTS_MODEL", os.environ.get("QWEN_TTS_MODEL") or "qwen3-tts-flash")
    row("QWEN_TTS_VOICE", os.environ.get("QWEN_TTS_VOICE") or "Cherry")
    row("DEEPSEEK_MODEL", os.environ.get("DEEPSEEK_MODEL") or "deepseek-flash")


def check_livekit() -> None:
    print("\nlivekit")
    url = os.environ.get("LIVEKIT_URL", "") or "ws://127.0.0.1:7880"
    key = os.environ.get("LIVEKIT_API_KEY", "")
    secret = os.environ.get("LIVEKIT_API_SECRET", "")
    row("LIVEKIT_URL", url, OK)
    row("LIVEKIT_API_KEY", key or "(not set)", OK if key else NO)
    row("LIVEKIT_API_SECRET", "set" if secret else "(not set)", OK if secret else NO)
    if not key or not secret:
        problems.append("set LIVEKIT_API_KEY / LIVEKIT_API_SECRET (defaults match docker-compose.yml)")

    http_url = url.replace("wss://", "https://").replace("ws://", "http://")
    try:
        import httpx

        response = httpx.get(http_url, timeout=5.0)
        row("server", f"reachable ({response.status_code})", OK)
    except Exception as exc:
        row("server", f"not reachable: {type(exc).__name__}", NO)
        problems.append("start the server: docker compose up -d  (then check docker compose ps)")


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
        row("customer", os.environ.get("CUSTOMER_ID") or "(CUSTOMER_ID not set)",
            OK if os.environ.get("CUSTOMER_ID") else WARN)
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


def check_plugins() -> None:
    print("\nplugins")
    try:
        from livekit_tts import QwenTTS

        tts = QwenTTS()
        row("tts", f"{tts.provider} {tts.model} @ {tts.sample_rate} Hz", OK)
    except Exception as exc:
        row("tts", f"{type(exc).__name__}: {str(exc)[:60]}", NO)
        problems.append("the TTS plugin did not build - see the traceback above")

    try:
        from livekit_stt import QwenSTT

        stt = QwenSTT()
        row("stt", f"{stt.provider} {stt.model}", OK)
    except Exception as exc:
        row("stt", f"{type(exc).__name__}: {str(exc)[:60]}", NO)
        problems.append("the STT plugin did not build - see the traceback above")


def main() -> int:
    reconfigure_console()
    print(f"livekit voice agent check - {ROOT}")

    check_python()
    check_keys()
    check_livekit()
    check_database()
    asyncio.run(check_mcp())
    check_plugins()

    print()
    if problems:
        print(f"{len(problems)} thing(s) to fix:")
        for index, problem in enumerate(problems, 1):
            print(f"  {index}. {problem}")
        return 1

    print("Everything is ready. Next:")
    print("  docker compose up -d          # LiveKit server")
    print("  uv run python agent.py dev    # the worker")
    print("  uv run python make_token.py   # paste into client/index.html")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
