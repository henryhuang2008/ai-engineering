"""A minimal MCP server with one tool, add.

    uv run python server.py          # stdio: launched by a client
    uv run python server.py sse      # SSE on http://127.0.0.1:8050/sse
    uv run python server.py http     # Streamable HTTP on /mcp
"""

from __future__ import annotations

import sys

from fastmcp import FastMCP

mcp = FastMCP("Calc")


@mcp.tool()
def add(a: int, b: int) -> int:
    """Add two numbers together."""
    return a + b


if __name__ == "__main__":
    transport = sys.argv[1] if len(sys.argv) > 1 else "stdio"
    if transport not in {"stdio", "sse", "http", "streamable-http"}:
        raise SystemExit(
            f"unknown transport: {transport} (use stdio, sse, or http)"
        )

    if transport == "stdio":
        mcp.run(transport="stdio", show_banner=False)
    else:
        print(
            f"serving over {transport} at http://127.0.0.1:8050 "
            "(sse path: /sse; http path: /mcp)",
            file=sys.stderr,
            flush=True,
        )
        mcp.run(
            transport=transport,
            show_banner=False,
            host="127.0.0.1",
            port=8050,
        )
