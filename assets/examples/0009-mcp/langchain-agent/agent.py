"""LangChain calls an MCP server with MCPAdapter.

This follows the quickstart at
https://docs.langchain.com/oss/python/langchain/mcp
The adapter launches server.py over stdio, lists its tools, and hands them to
create_agent. One ainvoke() runs the whole model -> tool -> model loop.

    $env:DEEPSEEK_API_KEY = "sk-..."
    uv run python agent.py "What is 2 + 3?"

SSE or Streamable HTTP: start the server first, then point --url at it.

    uv run python server.py sse
    uv run python agent.py --url http://127.0.0.1:8050/sse "What is 2 + 3?"

    uv run python server.py http
    uv run python agent.py --url http://127.0.0.1:8050/mcp "What is 2 + 3?"
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

from langchain.agents import create_agent
from langchain.mcp import MCPAdapter
from langchain_core.messages import BaseMessage, HumanMessage
from langchain_deepseek import ChatDeepSeek
HERE = Path(__file__).resolve().parent
SERVER = HERE / "server.py"
MODEL = "deepseek-flash"


def missing_key() -> str:
    return (
        "DEEPSEEK_API_KEY is not set - the model needs it to choose a tool.\n"
        '  PowerShell (this session):  $env:DEEPSEEK_API_KEY = "sk-..."\n'
        '  PowerShell (persist):       setx DEEPSEEK_API_KEY "sk-..."   # reopen terminal\n'
        "  Get a key:                  https://platform.deepseek.com/api_keys"
    )


def build_model() -> ChatDeepSeek:
    return ChatDeepSeek(
        model=MODEL,
        temperature=0,
        extra_body={"thinking": {"type": "disabled"}},
    )


def describe(message: BaseMessage) -> str:
    if message.type == "ai" and message.tool_calls:
        calls = ", ".join(
            f"{call['name']}({json.dumps(call['args'])})" for call in message.tool_calls
        )
        return f"ai     -> {calls}"
    if message.type == "tool":
        return f"tool   -> {text_of(message.content)}"
    content = str(message.content).replace("\n", " ")
    return f"{message.type:<6} -> {content[:100]}"


def text_of(result: Any) -> str:
    if isinstance(result, str):
        return result
    if isinstance(result, list):
        parts = [
            block.get("text", "")
            for block in result
            if isinstance(block, dict) and block.get("text")
        ]
        return "\n".join(parts) or "(no text content)"
    return str(result)


async def run() -> int:
    if not os.environ.get("DEEPSEEK_API_KEY"):
        print(missing_key(), file=sys.stderr)
        return 1

    parser = argparse.ArgumentParser(
        description="LangChain MCPAdapter demo. Default: launch server.py over stdio."
    )
    parser.add_argument("question", nargs="*", help="question for the agent")
    parser.add_argument(
        "--url",
        help="connect to a running HTTP server instead; /sse selects SSE, /mcp selects Streamable HTTP",
    )
    args = parser.parse_args()

    question = " ".join(args.question).strip() or "What is 2 + 3?"
    target = args.url or SERVER

    async with MCPAdapter(target) as adapter:
        tools = await adapter.list_tools()
        print(f"tools: {', '.join(tool.name for tool in tools)}")
        print(f"question: {question}")

        agent = create_agent(build_model(), tools)
        result = await agent.ainvoke({"messages": [HumanMessage(question)]})

    for index, message in enumerate(result["messages"], start=1):
        print(f"  {index} {describe(message)}")
    print(f"answer: {result['messages'][-1].content}")
    return 0


def main() -> int:
    try:
        return asyncio.run(run())
    except Exception as error:  # noqa: BLE001 - surface the provider error, keep exit codes
        print(f"error: {type(error).__name__}: {error}", file=sys.stderr)
        print(
            "check DEEPSEEK_API_KEY, account balance, and network access.",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
