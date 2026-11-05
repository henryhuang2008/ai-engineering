"""0004-streaming-chat - FastAPI + LangChain + DeepSeek, streamed to the browser.

One endpoint, three jobs:

  1. validate the conversation          pydantic models, roles as a Literal
  2. stream the model's reply           ChatDeepSeek.astream() -> AIMessageChunk
  3. frame each delta as SSE            `data: {"delta": "..."}` + a final done

The framing is JSON on purpose: a delta often contains a newline, and a raw
`data: <text>` frame would split one token into two events.

This lab talks to the live DeepSeek API. Set DEEPSEEK_API_KEY first:

  PowerShell (this session):  $env:DEEPSEEK_API_KEY = "sk-..."
  PowerShell (persist):       setx DEEPSEEK_API_KEY "sk-..."   # reopen the terminal

Get a key at https://platform.deepseek.com/api_keys. No key -> startup fails with
these instructions, never a guess.
"""

from __future__ import annotations

import json
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator, Literal

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, StreamingResponse
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from pydantic import BaseModel, Field

MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-flash")
BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
HERE = Path(__file__).resolve().parent

SYSTEM = "You are a concise support assistant. Answer in two or three sentences."


# --- request contract -------------------------------------------------------


class Message(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str = Field(min_length=1)


class ChatIn(BaseModel):
    messages: list[Message] = Field(min_length=1)


LC_MESSAGES = {"system": SystemMessage, "user": HumanMessage, "assistant": AIMessage}


def to_lc(message: Message) -> BaseMessage:
    """Pydantic message -> LangChain message. That is the whole adapter."""
    return LC_MESSAGES[message.role](content=message.content)


# --- model wiring -----------------------------------------------------------


def missing_key_message() -> str:
    return (
        "DEEPSEEK_API_KEY is not set.\n"
        '  PowerShell (this session):  $env:DEEPSEEK_API_KEY = "sk-..."\n'
        '  PowerShell (persist):       setx DEEPSEEK_API_KEY "sk-..."   # reopen terminal\n'
        "  Get a key:                  https://platform.deepseek.com/api_keys"
    )


def build_model() -> Any:
    """Return a live ChatDeepSeek handle, or explain exactly what is missing."""
    if not os.getenv("DEEPSEEK_API_KEY"):
        raise RuntimeError(missing_key_message())

    from langchain_deepseek import ChatDeepSeek

    return ChatDeepSeek(
        model=os.getenv("DEEPSEEK_MODEL", MODEL),
        api_key=os.getenv("DEEPSEEK_API_KEY"),
        api_base=os.getenv("DEEPSEEK_BASE_URL", BASE_URL),
        temperature=0.3,
        max_retries=2,
        timeout=60,
        # Thinking mode would stream reasoning_content first; this lab is about
        # the SSE seam, so keep the wire simple and the first token honest.
        extra_body={"thinking": {"type": "disabled"}},
    )


# --- SSE framing ------------------------------------------------------------


def sse(payload: dict[str, Any]) -> str:
    """One SSE event. JSON, so newlines and quotes inside a delta stay intact."""
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def text_of(chunk: Any) -> str:
    """AIMessageChunk.content is a str, or a list of content blocks."""
    content = getattr(chunk, "content", "")
    if isinstance(content, str):
        return content
    parts: list[str] = []
    for block in content or []:
        if isinstance(block, str):
            parts.append(block)
        elif isinstance(block, dict) and block.get("type") == "text":
            parts.append(str(block.get("text", "")))
    return "".join(parts)


async def stream_reply(payload: ChatIn) -> AsyncIterator[str]:
    """Call the model once, yield one SSE event per delta, then close the stream."""
    model = build_model()
    messages = [SystemMessage(content=SYSTEM), *(to_lc(message) for message in payload.messages)]

    try:
        async for chunk in model.astream(messages):
            delta = text_of(chunk)
            if delta:
                yield sse({"delta": delta})
    except Exception as error:  # noqa: BLE001 - the client must see why the stream died
        yield sse({"error": f"{type(error).__name__}: {error}"})
    finally:
        yield sse({"done": True})


# --- app --------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Fail at startup, not on the first message, when the key is missing."""
    if not os.getenv("DEEPSEEK_API_KEY"):
        raise RuntimeError(missing_key_message())
    yield


app = FastAPI(title="0004 streaming chat", lifespan=lifespan)


@app.get("/", response_class=HTMLResponse)
async def index() -> str:
    """The bare test client: proves the Python side streams before Next.js exists."""
    return (HERE / "test-client.html").read_text(encoding="utf-8")


@app.get("/health")
async def health() -> dict[str, Any]:
    return {"ok": True, "model": MODEL, "key": bool(os.getenv("DEEPSEEK_API_KEY"))}


@app.post("/chat-stream")
async def chat_stream(payload: ChatIn) -> StreamingResponse:
    return StreamingResponse(
        stream_reply(payload),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            # Proxies love to buffer SSE; this header turns that off for most.
            "X-Accel-Buffering": "no",
        },
    )


def main() -> int:
    try:
        build_model()
    except RuntimeError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print(f"ok: {MODEL} reachable config; start the server with:")
    print("  uv run uvicorn main:app --reload")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
