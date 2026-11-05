"""Self-tests for 0004-streaming-chat.

No fake model: the lab talks to live DeepSeek. Everything here runs offline -
the pydantic request contract, the message adapter, SSE framing (including the
newline case that breaks naive `data: <text>` streams), the chunk-to-text
reader, model wiring, the missing-key instructions, the uv project - plus one
live stream when a key is set.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import subprocess
import sys
import tomllib
from pathlib import Path

from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage, SystemMessage
from pydantic import ValidationError

import main as lab

HERE = Path(__file__).resolve().parent
PY = sys.executable
CHECKS: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    if not condition:
        raise AssertionError(f"{name}: {detail}" if detail else name)
    CHECKS.append(name)


def clean_env() -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith("DEEPSEEK_")}
    env.pop("OPENAI_API_KEY", None)
    env.pop("PY_BACKEND", None)
    return env


def with_env(values: dict[str, str]):
    """Temporarily set env vars, then restore exactly."""

    class _Ctx:
        def __enter__(self):
            self.old = os.environ.copy()
            os.environ.update(values)

        def __exit__(self, *args):
            os.environ.clear()
            os.environ.update(self.old)

    return _Ctx()


# --- request contract -------------------------------------------------------


def test_message_contract() -> None:
    good = lab.Message(role="user", content="hello")
    check("valid message accepted", good.role == "user" and good.content == "hello")

    for role in ("system", "user", "assistant"):
        check(f"role {role} allowed", lab.Message(role=role, content="x").role == role)

    try:
        lab.Message(role="tool", content="x")
    except ValidationError:
        CHECKS.append("role tool rejected")
    else:
        raise AssertionError("role tool should be rejected")

    try:
        lab.Message(role="user", content="")
    except ValidationError:
        CHECKS.append("empty content rejected")
    else:
        raise AssertionError("empty content should be rejected")

    lab.ChatIn(messages=[good])
    CHECKS.append("chat with one message accepted")

    try:
        lab.ChatIn(messages=[])
    except ValidationError:
        CHECKS.append("empty history rejected")
    else:
        raise AssertionError("empty history should be rejected")


def test_adapter() -> None:
    pairs = [
        ("system", SystemMessage),
        ("user", HumanMessage),
        ("assistant", AIMessage),
    ]
    for role, expected in pairs:
        built = lab.to_lc(lab.Message(role=role, content="hello there"))
        check(f"{role} maps to {expected.__name__}", isinstance(built, expected), type(built).__name__)
        check(f"{role} keeps the text", built.content == "hello there", str(built.content))
    check(
        "adapter covers every allowed role",
        set(lab.LC_MESSAGES) == {"system", "user", "assistant"},
        str(sorted(lab.LC_MESSAGES)),
    )


# --- wire format ------------------------------------------------------------


def test_sse_framing() -> None:
    frame = lab.sse({"delta": "hi"})
    check("frame starts with data: ", frame.startswith("data: "), repr(frame))
    check("frame ends with a blank line", frame.endswith("\n\n"), repr(frame))
    body = frame[len("data: ") : -2]
    check("body is JSON", json.loads(body) == {"delta": "hi"}, body)

    tricky = lab.sse({"delta": "line one\nline two"})
    check("one event per delta, even with a newline", tricky.count("data: ") == 1, repr(tricky))
    check("newline survives the round trip", json.loads(tricky[6:-2])["delta"] == "line one\nline two")

    unicode_frame = lab.sse({"delta": "café → naïve"})
    check("unicode is not escaped", "café → naïve" in unicode_frame, unicode_frame)
    check("unicode parses back", json.loads(unicode_frame[6:-2])["delta"] == "café → naïve")

    done = lab.sse({"done": True})
    check("done frame is JSON", json.loads(done[6:-2]) == {"done": True}, done)

    error = lab.sse({"error": "boom"})
    check("error frame is JSON", json.loads(error[6:-2]) == {"error": "boom"}, error)


def test_chunk_text() -> None:
    check("string content passes through", lab.text_of(AIMessageChunk(content="abc")) == "abc")

    blocks = AIMessageChunk(
        content=[
            {"type": "text", "text": "ab"},
            {"type": "reasoning", "text": "thinking"},
            {"type": "text", "text": "cd"},
        ]
    )
    check("text blocks are joined", lab.text_of(blocks) == "abcd", lab.text_of(blocks))
    check("non-text blocks are dropped", "thinking" not in lab.text_of(blocks))

    empty = AIMessageChunk(content=[])
    check("empty content is empty text", lab.text_of(empty) == "", repr(lab.text_of(empty)))
    check("missing content is tolerated", lab.text_of(object()) == "")


def test_stream_contract() -> None:
    """stream_reply is an async generator that closes with a done frame."""
    source = (HERE / "main.py").read_text(encoding="utf-8")
    check("stream_reply is async", "async def stream_reply" in source)
    check("uses astream", ".astream(" in source)
    check("yields a done frame", 'sse({"done": True})' in source)
    check(
        "returns an event-stream response",
        'media_type="text/event-stream"' in source,
        "media type missing",
    )
    check("disables proxy buffering", "X-Accel-Buffering" in source)
    check("serves the bare test client", "test-client.html" in source)
    check("fails at startup without a key", "async def lifespan" in source)


# --- model wiring -----------------------------------------------------------


def test_model_config() -> None:
    with with_env({"DEEPSEEK_API_KEY": "test-key"}):
        model = lab.build_model()
    check("live model class", type(model).__name__ == "ChatDeepSeek", type(model).__name__)
    check("default model name", model.model_name == "deepseek-flash", model.model_name)
    check(
        "default base url",
        str(model.root_client.base_url).rstrip("/") == "https://api.deepseek.com",
        str(model.root_client.base_url),
    )
    check("temperature is product-tuned, not zero", model.temperature == 0.3, str(model.temperature))
    check(
        "thinking disabled for the stream",
        model.extra_body == {"thinking": {"type": "disabled"}},
        str(model.extra_body),
    )


def test_model_overrides() -> None:
    with with_env(
        {
            "DEEPSEEK_API_KEY": "test-key",
            "DEEPSEEK_MODEL": "deepseek-v4-pro",
            "DEEPSEEK_BASE_URL": "https://example.test",
        }
    ):
        model = lab.build_model()
    check("model override", model.model_name == "deepseek-v4-pro", model.model_name)
    check(
        "base url override",
        str(model.root_client.base_url).rstrip("/") == "https://example.test",
        str(model.root_client.base_url),
    )


def test_missing_key() -> None:
    message = lab.missing_key_message()
    check("message names the session command", '$env:DEEPSEEK_API_KEY = "sk-..."' in message)
    check("message names setx", "setx DEEPSEEK_API_KEY" in message)
    check("message links the key page", "platform.deepseek.com/api_keys" in message)

    with with_env({}):
        os.environ.pop("DEEPSEEK_API_KEY", None)

        try:
            lab.build_model()
        except RuntimeError as error:
            check("build_model refuses without a key", "DEEPSEEK_API_KEY" in str(error), str(error))
        else:
            raise AssertionError("build_model should refuse without a key")

        try:
            asyncio.run(_open_lifespan())
        except RuntimeError as error:
            check("startup refuses without a key", "DEEPSEEK_API_KEY" in str(error), str(error))
        else:
            raise AssertionError("lifespan should refuse without a key")

    result = subprocess.run(
        [PY, "main.py"],
        cwd=HERE,
        env=clean_env(),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
    )
    check("cli exits 1 without a key", result.returncode == 1, str(result.returncode))
    check("cli prints the instructions", "DEEPSEEK_API_KEY" in result.stderr, result.stderr)


async def _open_lifespan() -> None:
    async with lab.lifespan(lab.app):
        pass


# --- repo hygiene -----------------------------------------------------------


def test_stack() -> None:
    root = HERE.parent
    source = (HERE / "main.py").read_text(encoding="utf-8")
    check("no OpenAI SDK in the backend", "from openai" not in source)
    check("no gpt-4o model name", "gpt-4o" not in source)
    check("langchain-deepseek is the provider", "langchain_deepseek" in source)
    check("pydantic validates requests", "BaseModel" in source)
    check("FastAPI serves it", "FastAPI(" in source)

    page = (root / "frontend" / "app" / "page.tsx").read_text(encoding="utf-8")
    check("frontend uses useChat", "useChat" in page)
    check("frontend uses the shadcn prompt input", "InputGroupTextarea" in page)
    check("frontend sends text only", 'sendMessage({ text: value })' in page)
    check("page translates a 404 HTML body into a hint", "<!DOCTYPE html" in page, "no 404 hint")

    route = (
        root / "frontend" / "app" / "api" / "chat" / "route.ts"
    ).read_text(encoding="utf-8")
    check("route parses SSE events", 'indexOf("\\n\\n")' in route)
    check("route writes text deltas", '"text-delta"' in route)
    check("route propagates aborts upstream", "signal: req.signal" in route)
    check("route answers failures as plain text", "text/plain; charset=utf-8" in route)
    check("route names the unreachable backend", "python backend unreachable" in route)
    check("route ignores the abort as an error", "req.signal.aborted" in route)

    readme = (root / "README.md").read_text(encoding="utf-8")
    check("readme documents the 405-vs-404 check", "405 Method Not Allowed" in readme)
    check("readme names the exact route folder", r"app\api\chat\route.ts" in readme)


def test_uv_project() -> None:
    pyproject = HERE / "pyproject.toml"
    check("pyproject.toml exists", pyproject.exists())
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    declared = {
        re.split(r"[<>=!~ ]", dep, maxsplit=1)[0] for dep in data["project"]["dependencies"]
    }
    check(
        "declares fastapi, uvicorn, langchain, langchain-deepseek, pydantic",
        {"fastapi", "uvicorn", "langchain", "langchain-deepseek", "pydantic"} <= declared,
        str(sorted(declared)),
    )


# --- live ---------------------------------------------------------------


async def _live_stream() -> list[str]:
    model = lab.build_model()
    deltas: list[str] = []
    async for chunk in model.astream(
        [SystemMessage(content=lab.SYSTEM), HumanMessage(content="Say hello in one short sentence.")]
    ):
        text = lab.text_of(chunk)
        if text:
            deltas.append(text)
    return deltas


def test_live_smoke() -> tuple[bool, str]:
    if not os.getenv("DEEPSEEK_API_KEY"):
        return False, "skipped (no DEEPSEEK_API_KEY)"
    deltas = asyncio.run(_live_stream())
    check("live stream yield at least one delta", len(deltas) >= 1, str(len(deltas)))
    check("live deltas concatenate to text", bool("".join(deltas).strip()), "".join(deltas)[:80])
    check("live stream is chunked", len(deltas) >= 2, str(len(deltas)))
    return True, f"streamed {len(deltas)} deltas"


TESTS = [
    ("message contract", test_message_contract),
    ("message adapter", test_adapter),
    ("sse framing", test_sse_framing),
    ("chunk text", test_chunk_text),
    ("stream contract", test_stream_contract),
    ("model config", test_model_config),
    ("model overrides", test_model_overrides),
    ("missing key", test_missing_key),
    ("stack", test_stack),
    ("uv project", test_uv_project),
]


def main() -> int:
    failures = 0
    for index, (name, test) in enumerate(TESTS, start=1):
        try:
            test()
            print(f"ok {index:02d} {name}")
        except Exception as error:  # noqa: BLE001 - a test runner reports everything
            failures += 1
            print(f"FAIL {index:02d} {name}: {error}")

    try:
        ran, note = test_live_smoke()
    except Exception as error:  # noqa: BLE001
        failures += 1
        print(f"FAIL 11 live smoke: {error}")
    else:
        print(f"ok 11 live smoke: {note}")
        if not ran:
            print("     set DEEPSEEK_API_KEY to include the live stream")

    total = len(CHECKS)
    print(f"\n{total} checks passed, {failures} failed")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
