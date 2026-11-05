"""DeepSeek chooses the tool; this client executes it over MCP.

The bridge is deliberately small: MCP's `inputSchema` is already a JSON schema,
which is exactly the shape a chat model expects for function calling. Convert,
bind, loop.

    $env:DEEPSEEK_API_KEY = "sk-..."
    uv run python chat.py "How long is the refund window?"
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langchain_deepseek import ChatDeepSeek
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

HERE = Path(__file__).resolve().parent
SERVER = HERE / "server.py"

SYSTEM = """You answer NimbusDesk support questions using the tools provided.

Use search_kb before answering a product question. If the knowledge base does
not cover the question, say so - do not guess. Keep the answer to two sentences."""


def missing_key() -> str:
    return (
        "DEEPSEEK_API_KEY is not set - the model needs it to choose a tool.\n"
        '  PowerShell (this session):  $env:DEEPSEEK_API_KEY = "sk-..."\n'
        '  PowerShell (persist):       setx DEEPSEEK_API_KEY "sk-..."   # reopen terminal\n'
        "  Get a key:                  https://platform.deepseek.com/api_keys"
    )


def text_of(result) -> str:
    parts = [block.text for block in result.content if getattr(block, "text", None)]
    return "\n".join(parts) or "(no text content)"


def as_function_tools(tools) -> list[dict]:
    """MCP tool -> the dict shape ChatDeepSeek.bind_tools accepts."""
    return [
        {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description or "",
                "parameters": tool.inputSchema,
            },
        }
        for tool in tools
    ]


async def main() -> int:
    if not os.environ.get("DEEPSEEK_API_KEY"):
        print(missing_key(), file=sys.stderr)
        return 1

    question = " ".join(sys.argv[1:]).strip() or "What is the refund window?"
    model = ChatDeepSeek(
        model="deepseek-flash",
        temperature=0,
        extra_body={"thinking": {"type": "disabled"}},
    )
    params = StdioServerParameters(command=sys.executable, args=[str(SERVER)])

    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            listed = await session.list_tools()
            print(f"tools: {', '.join(tool.name for tool in listed.tools)}")
            model_with_tools = model.bind_tools(as_function_tools(listed.tools))

            print(f"question: {question}")
            messages = [SystemMessage(content=SYSTEM), HumanMessage(content=question)]

            for _ in range(4):
                reply = await model_with_tools.ainvoke(messages)
                messages.append(reply)

                if not reply.tool_calls:
                    print(f"answer: {reply.content}")
                    return 0

                for call in reply.tool_calls:
                    print(f"  tool {call['name']}({json.dumps(call['args'])})")
                    result = await session.call_tool(
                        call["name"], arguments=call["args"]
                    )
                    content = text_of(result)
                    print(f"  -> {content.splitlines()[0][:100]}")
                    messages.append(
                        ToolMessage(content=content, tool_call_id=call["id"])
                    )

    print("stopped after 4 model turns", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
