"""Call the server over Streamable HTTP - one endpoint, both directions.

This is the transport to use for new HTTP integrations; SSE is the older one.
The client yields three values: read stream, write stream, and a session-id
getter (unused here).

Unlike stdio, HTTP does not launch the server for you. Two terminals:

Terminal 1:  uv run python server.py streamable-http
Terminal 2:  uv run python client-streamable-http.py
"""

from __future__ import annotations

import asyncio
import os
import socket
import sys
from urllib.parse import urlsplit

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

URL = "http://127.0.0.1:8050/mcp"
SERVER_COMMAND = "uv run python server.py streamable-http"


def allow_localhost_direct() -> None:
    """Keep a system HTTP proxy from intercepting 127.0.0.1.

    httpx honours HTTP_PROXY/ALL_PROXY from the environment. On machines behind
    a corporate proxy, a request to localhost can come back as a 502 from the
    proxy instead of reaching the server. NO_PROXY exempts loopback.
    """
    hosts = {"127.0.0.1", "localhost", "::1"}
    for name in ("NO_PROXY", "no_proxy"):
        current = {
            host.strip() for host in os.environ.get(name, "").split(",") if host.strip()
        }
        os.environ[name] = ",".join(sorted(current | hosts))


def diagnose() -> str:
    """Say whether the port is empty or occupied by the wrong process."""
    parts = urlsplit(URL)
    host = parts.hostname or "127.0.0.1"
    port = parts.port or 80
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        listening = sock.connect_ex((host, port)) == 0
    if listening:
        return (
            f"something is listening on {host}:{port} but did not answer as MCP - "
            "stop that process or change the port"
        )
    return (
        f"nothing is listening on {host}:{port} - start the server in another "
        f"terminal:  {SERVER_COMMAND}"
    )


async def main() -> None:
    async with streamablehttp_client(URL) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools = await session.list_tools()
            print(f"connected to {URL}")
            print(f"tools: {', '.join(tool.name for tool in tools.tools)}")

            result = await session.call_tool("add", arguments={"a": 2, "b": 3})
            print(f"2 + 3 = {result.content[0].text}")


if __name__ == "__main__":
    allow_localhost_direct()
    try:
        asyncio.run(main())
    except (BaseExceptionGroup, OSError) as exc:
        detail = (
            exc.exceptions[0]
            if isinstance(exc, BaseExceptionGroup) and exc.exceptions
            else exc
        )
        print(f"could not reach {URL}\n  {type(detail).__name__}: {detail}", file=sys.stderr)
        print(diagnose(), file=sys.stderr)
        raise SystemExit(1) from None
