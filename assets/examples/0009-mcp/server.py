"""NimbusDesk MCP server: two tools, one resource, one prompt.

Run it directly only to see it start; under stdio the client launches it as a
subprocess and talks to it over stdin/stdout:

    uv run python server.py

stdout carries protocol messages. Anything you print for humans must go to
stderr, or it corrupts the stream.
"""

from __future__ import annotations

import json
import re
import socket
import sys
from pathlib import Path

from mcp.server.fastmcp import FastMCP

HERE = Path(__file__).resolve().parent
KB_PATH = HERE / "data" / "kb.json"

mcp = FastMCP(
    "NimbusDesk",
    host="127.0.0.1",
    port=8050,
    # The SDK logs every request to stderr at INFO. That is useful while
    # debugging the server, noise while reading the client's output.
    log_level="ERROR",
)


def knowledge_base() -> list[dict]:
    payload = json.loads(KB_PATH.read_text(encoding="utf-8"))
    return payload["entries"]


@mcp.tool()
def add(a: int, b: int) -> int:
    """Add two numbers together."""
    return a + b


@mcp.tool()
def search_kb(query: str, limit: int = 3) -> str:
    """Search the NimbusDesk knowledge base and return the best matching entries.

    Args:
        query: Words from the customer's question, for example "refund window".
        limit: Maximum entries to return, 1-10.
    """
    terms = [term for term in re.findall(r"[a-z0-9-]+", query.lower()) if len(term) > 2]
    scored: list[tuple[int, dict]] = []
    for entry in knowledge_base():
        haystack = f"{entry['question']} {entry['answer']}".lower()
        score = sum(haystack.count(term) for term in terms)
        if score:
            scored.append((score, entry))

    scored.sort(key=lambda pair: -pair[0])
    top = scored[: max(1, min(limit, 10))]
    if not top:
        return "No matching entries."
    return "\n\n".join(
        f"Q: {entry['question']}\nA: {entry['answer']}" for _, entry in top
    )


@mcp.resource("kb://nimbusdesk/all")
def whole_kb() -> str:
    """The entire NimbusDesk knowledge base as JSON."""
    return KB_PATH.read_text(encoding="utf-8")


@mcp.prompt()
def answer_from_kb(question: str) -> str:
    """Template for answering a product question from the knowledge base."""
    return (
        "Answer the question using only the NimbusDesk knowledge base. "
        "If an entry does not cover it, say so instead of guessing.\n\n"
        f"Question: {question}"
    )


if __name__ == "__main__":
    transport = sys.argv[1] if len(sys.argv) > 1 else "stdio"
    if transport not in {"stdio", "sse", "streamable-http"}:
        raise SystemExit(
            f"unknown transport: {transport} "
            "(use stdio, sse, or streamable-http)"
        )

    # FastMCP runs on uvicorn, but log_level="ERROR" above hides its banner.
    # Check the port first, then print our own line, so a silent or misleading
    # terminal never looks like a successful start when it is not.
    if transport == "stdio":
        print("serving over stdio (stdout is the protocol)", file=sys.stderr)
    else:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.settimeout(0.3)
            in_use = probe.connect_ex(("127.0.0.1", 8050)) == 0
        if in_use:
            raise SystemExit(
                "port 8050 is already in use - stop the other server "
                "(sse and streamable-http share the port), then retry"
            )
        path = "/sse" if transport == "sse" else "/mcp"
        print(
            f"serving over {transport} at http://127.0.0.1:8050{path}",
            file=sys.stderr,
        )
        print("press Ctrl+C to stop", file=sys.stderr)

    mcp.run(transport=transport)
