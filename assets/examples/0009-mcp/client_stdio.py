"""Call the MCP server with no LLM in the loop.

This is the protocol as it actually is: the client launches the server as a
subprocess, initializes a session, then lists and calls capabilities. An LLM is
just another client that decides which tool to call.

    uv run python client_stdio.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

HERE = Path(__file__).resolve().parent
SERVER = HERE / "server.py"


def text_of(result) -> str:
    parts = [block.text for block in result.content if getattr(block, "text", None)]
    return "\n".join(parts) or "(no text content)"


async def main() -> None:
    params = StdioServerParameters(command=sys.executable, args=[str(SERVER)])

    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools = await session.list_tools()
            print(f"tools ({len(tools.tools)}):")
            for tool in tools.tools:
                arguments = ", ".join(tool.inputSchema.get("properties", {}))
                print(f"  {tool.name}({arguments})")

            resources = await session.list_resources()
            print(f"\nresources ({len(resources.resources)}):")
            for resource in resources.resources:
                print(f"  {resource.uri} - {resource.name}")

            prompts = await session.list_prompts()
            print(f"\nprompts ({len(prompts.prompts)}):")
            for prompt in prompts.prompts:
                print(f"  {prompt.name}")

            print("\ncall add(a=2, b=3)")
            result = await session.call_tool("add", arguments={"a": 2, "b": 3})
            print(text_of(result))

            print("\ncall search_kb(query='refund window')")
            result = await session.call_tool(
                "search_kb", arguments={"query": "refund window"}
            )
            print(text_of(result))


if __name__ == "__main__":
    asyncio.run(main())
