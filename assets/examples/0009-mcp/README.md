# 0009 — MCP: write the tool once, call it from any client

An MCP server and two clients: one that speaks the protocol directly, one where
DeepSeek decides which tool to call. Same server, same tools, no rewriting for
each client.

The server exposes the three MCP primitives on purpose:

| primitive | what it is | here |
|---|---|---|
| **tool** | model-controlled function | `add`, `search_kb` |
| **resource** | application-controlled data | `kb://nimbusdesk/all` |
| **prompt** | user-controlled template | `answer_from_kb` |

## Run

```powershell
cd assets\examples\0009-mcp
uv sync

uv run python client_stdio.py          # no API key: list, call, print
$env:DEEPSEEK_API_KEY = "sk-..."       # only the model-client step needs this
uv run python chat.py "How long is the refund window?"
```

`chat.py` with no question asks about the refund window. Under stdio, the server
is launched as a subprocess by both clients — you never start it in a second
terminal. The HTTP transports are the opposite: start the server, then connect.

```powershell
# SSE (older HTTP transport)
uv run python server.py sse
uv run python client-sse.py

# Streamable HTTP (new HTTP integrations)
uv run python server.py streamable-http
uv run python client-streamable-http.py
```

Both HTTP servers bind `127.0.0.1:8050`. Stop one before starting the other,
or the second bind fails with `WinError 10048`.

The server prints its own startup line (FastMCP runs on uvicorn, but
`log_level="ERROR"` hides uvicorn's banner):

```
serving over sse at http://127.0.0.1:8050/sse
press Ctrl+C to stop
```

## Inspector (optional)

`uv run mcp dev server.py` opens the MCP Inspector, a browser UI for listing and
calling tools. It needs Node.js and downloads `@modelcontextprotocol/inspector`
through npx on first run — minutes on a slow npm network. If that hangs, point
npm at a mirror first:

```powershell
npm config set registry https://registry.npmmirror.com
```

Then open the **exact URL printed in the terminal**, including the token:

```
http://127.0.0.1:6274?MCP_INSPECTOR_API_TOKEN=...
```

Opening bare `http://127.0.0.1:6274` shows an empty page because the token is
missing. The Python clients in this lab do not need the Inspector.

### Inspecting SSE or Streamable HTTP

`mcp dev` always wires the Inspector to a **stdio** server, which is why its UI
has no transport picker. To inspect an HTTP transport, start that server
yourself and launch the Inspector with matching flags:

```powershell
# terminal 1
uv run python server.py sse

# terminal 2
npx --yes @modelcontextprotocol/inspector --web `
  --transport sse --server-url http://127.0.0.1:8050/sse
```

For Streamable HTTP, use `--transport http --server-url http://127.0.0.1:8050/mcp`.
Open the token URL the Inspector prints. Without `--transport`/`--server-url`,
the UI shows its own connect form where the transport can be chosen manually.

## If it fails

- **`502 Bad Gateway` from `127.0.0.1`** — a system proxy is intercepting
  loopback. The HTTP clients add `127.0.0.1, localhost, ::1` to `NO_PROXY`
  before connecting, which fixes the usual case; if it persists, check
  `ALL_PROXY` and confirm the server is the process listening on 8050.
- **`ConnectError: All connection attempts failed`** — the server is not
  running. Start it in another terminal: `uv run python server.py sse`.
- **`WinError 10048`** — port 8050 is already in use. Stop the previous server
  (`Get-NetTCPConnection -LocalPort 8050` finds it).
- **`ImportError: cannot import name '_schema_generation_shared' from 'pydantic._internal'`**
  — a half-installed environment, usually a venv that was deleted or moved
  while uv was writing to it. Rebuild it:
  `Remove-Item -Recurse -Force .venv; uv sync`.
- **`VIRTUAL_ENV ... does not match the project environment path`** — you have
  another example's venv active (the prompt shows `(0007-rag-service)`). uv
  ignores it and uses this project's `.venv`, so the warning is harmless; run
  `deactivate` to silence it.

## What you should see

`client_stdio.py`:

```
tools (2):
  add(a, b)
  search_kb(query, limit)

resources (1):
  kb://nimbusdesk/all - whole_kb

prompts (1):
  answer_from_kb

call add(a=2, b=3)
5
```

`chat.py` (live DeepSeek, `temperature=0`):

```
tools: add, search_kb
question: What does E-311 mean?
  tool search_kb({"query": "E-311 error code"})
  -> Q: What does error E-311 mean?
answer: E-311 means the mailbox storage quota was exceeded. To fix it, archive
conversations or raise the seat storage limit.
```

Ask something the knowledge base does not cover — "What is the SLA for the
mobile app?" — and the model says it does not know. The tool result is the only
evidence it has.

## Files

| file | role |
|---|---|
| `server.py` | FastMCP server: 2 tools, 1 resource, 1 prompt; stdio, SSE or Streamable HTTP |
| `client_stdio.py` | raw client: initialize, list, call — no model |
| `client-sse.py` | same call over the older HTTP+SSE transport |
| `client-streamable-http.py` | same call over one `/mcp` endpoint |
| `chat.py` | DeepSeek + the same server, tools bound as functions |
| `data/kb.json` | the NimbusDesk Q&A the `search_kb` tool reads |

## How the LLM bridge works

There is no magic adapter here, and that is the point. MCP already publishes a
JSON schema for every tool (`inputSchema`), which is exactly what a chat model
wants for function calling:

```python
def as_function_tools(tools):
    return [
        {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.inputSchema,
            },
        }
        for tool in tools
    ]
```

After that it is the lesson-3 loop with one new step: instead of calling a local
function, the client calls `session.call_tool(...)` and feeds the text back as a
`ToolMessage`. Four turns maximum, then it stops.

## Transports

| transport | client | server command | use |
|---|---|---|---|
| **stdio** | `stdio_client(...)` | (launched by the client) | local; the client launches the server as a subprocess. Used by `chat.py`. |
| **SSE** | `sse_client(...)` | `server.py sse` | older HTTP transport; follow an existing tutorial |
| **Streamable HTTP** | `streamablehttp_client(...)` | `server.py streamable-http` | new HTTP integrations, one `/mcp` endpoint |

All three clients print the same tools and the same `2 + 3 = 5`; only the
connection line changes:

```
connected to http://127.0.0.1:8050/sse
tools: add, search_kb
2 + 3 = 5
```

Stdio has one hard rule: **stdout is the protocol**. A stray `print()` corrupts
the stream. Log to stderr, or set `log_level="ERROR"` as this server does.

## MCP vs plain function calling

| | plain function calling | MCP |
|---|---|---|
| tools live | in your process | in a server process |
| reuse across apps | copy the code | point another client at the server |
| language boundary | same runtime | any MCP client, any language |
| latency | a direct call | a protocol round trip |
| setup | one decorator | a server + a client + a transport |

Use MCP when the tool is shared, remote, or written by someone else. For one
app with three local functions, plain `@tool` is still the right answer.

## Lifecycle

Both clients use the same shape, and the context managers are the lifecycle:

```python
async with stdio_client(params) as (read, write):
    async with ClientSession(read, write) as session:
        await session.initialize()   # version negotiation
        ...                          # list / call
# session closed, subprocess terminated
```

`initialize()` is not optional: it negotiates the protocol version before any
request. For resources that live as long as the server — a database pool, a
loaded model — use FastMCP's `lifespan` instead of opening them per tool call.

## Security defaults

- HTTP transports bind to `127.0.0.1`; there is no authentication in this lab.
- Stdio servers inherit the client's permissions. Only launch servers you trust.
- Publishing a port does not add auth. A remote MCP server needs TLS, explicit
  trusted hosts/origins, and an auth layer.

## Notes

- **Two different FastMCPs.** This lab uses `mcp.server.fastmcp.FastMCP` — the v1 SDK's server class. The standalone `fastmcp` package (v2) is not a dependency. Clients use the SDK transports: `stdio_client`, `sse_client`, `streamablehttp_client`.
- `mcp[cli]` is pinned to the 1.x SDK (`>=1.30,<2`). The v2 SDK changes these APIs; do not swap the pin without reading the migration notes.
- The server also runs under `mcp dev server.py` (MCP Inspector, needs Node.js)
  and `mcp install server.py` (Claude Desktop). Neither is required here.
- `nest-asyncio` is not needed outside Jupyter, so this lab does not install it.
