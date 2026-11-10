# LangChain calling MCP

A minimal example of the official LangChain MCP adapter:

<https://docs.langchain.com/oss/python/langchain/mcp>

`server.py` is a FastMCP server with one `add(a, b)` tool. `agent.py` lets
`MCPAdapter` launch that server over stdio, converts the tool, and runs one
`create_agent` call.

This is a separate uv project because `langchain.mcp.MCPAdapter` requires MCP v2,
while the main Lesson 9 lab pins the v1 SDK for its server and raw clients.

## Run

```powershell
cd assets\examples\0009-mcp\langchain-agent
uv sync
$env:DEEPSEEK_API_KEY = "sk-..."
uv run python agent.py "What is 2 + 3?"
```

## SSE and Streamable HTTP

Stdio is the default: `MCPAdapter(SERVER)` launches `server.py` as a subprocess.
To use HTTP, start the server in one terminal and pass its URL with `--url`:

```powershell
# terminal 1 - pick one
uv run python server.py sse
uv run python server.py http

# terminal 2 - SSE
uv run python agent.py --url http://127.0.0.1:8050/sse "What is 2 + 3?"

# terminal 2 - Streamable HTTP
uv run python agent.py --url http://127.0.0.1:8050/mcp "What is 2 + 3?"
```

FastMCP infers the transport from the URL: a path ending in `/sse` selects SSE;
anything else is Streamable HTTP. Both print the same tools and the same answer
as the stdio run. Both bind `127.0.0.1:8050`, so stop one server before starting
the other. The `--url` value is passed straight to `MCPAdapter`, which accepts a
script path (stdio), an HTTP URL, or a FastMCP transport object.

## What you should see

```
tools: add
question: What is 2 + 3?
  1 human  -> What is 2 + 3?
  2 ai     -> add({"a": 2, "b": 3})
  3 tool   -> 5
  4 ai     -> 2 + 3 = **5**
answer: 2 + 3 = **5**
```

The import also prints a `LangChainBetaWarning`; the `langchain.mcp` namespace is
beta and its API may change.

## Files

| file | role |
|---|---|
| `server.py` | FastMCP v2 server with one `add` tool |
| `agent.py` | `MCPAdapter` + `create_agent`, one agent call |
| `pyproject.toml` | `langchain[mcp]` and `langchain-deepseek` |
