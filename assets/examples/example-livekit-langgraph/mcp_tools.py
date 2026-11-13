"""Turn `mcps/mcp_config.json` into a live tool list for the agent.

The JSON file is the same shape Claude Desktop and other MCP hosts use. Two
things are fixed up here so it also works from a uv virtualenv:

  * `command` becomes this interpreter, not whatever `python` is on PATH
  * relative `args` become absolute paths

The child process also inherits our environment, so SUPABASE_URI from `.env`
reaches the server.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from langchain_mcp_adapters.client import MultiServerMCPClient

PROJECT_ROOT = Path(__file__).resolve().parent
CONFIG = PROJECT_ROOT / "mcps" / "mcp_config.json"


def connections() -> dict:
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    servers = config["mcpServers"]

    resolved: dict = {}
    for name, spec in servers.items():
        spec = dict(spec)
        spec["command"] = sys.executable
        spec["args"] = [str((PROJECT_ROOT / arg).resolve()) for arg in spec.get("args", [])]
        spec["env"] = dict(os.environ)
        resolved[name] = spec
    return resolved


async def load_tools():
    """Start each configured MCP server and convert its tools for LangChain."""
    client = MultiServerMCPClient(connections=connections())
    return await client.get_tools()
