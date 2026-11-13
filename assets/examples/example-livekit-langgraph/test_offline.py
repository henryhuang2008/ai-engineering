"""Offline checks: no network, no keys, no database, no LiveKit server.

    uv run python test_offline.py

The live path (Qwen, DeepSeek, the room) is exercised by `smoke.py`.
"""

from __future__ import annotations

import asyncio
import inspect
import os
import sys
import tempfile
import wave
from pathlib import Path

from langchain_core.messages import AIMessageChunk
from livekit import rtc
from livekit.agents import llm

import categories
import mcp_tools
import qwen
from assistant_graph import stream_reply, to_langchain
from livekit_stt import QwenSTT, wav_bytes
from livekit_tts import QwenTTS

results: list[tuple[bool, str, str]] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    results.append((bool(condition), name, detail))


def test_categories() -> None:
    values = [c.value for c in categories.ExpenseCategory]
    check("9 categories", len(values) == 9, str(values))
    check("other is a category", "other" in values)
    check("meals is a category", "meals" in values)


def test_markdown_cleanup() -> None:
    raw = "**Done** — logged `Team lunch` for [fifteen dollars](https://x.test)."
    clean = qwen.for_speech(raw)
    check("for_speech drops ** and backticks", "*" not in clean and "`" not in clean, clean)
    check("for_speech keeps the link label", "fifteen dollars" in clean, clean)
    check("for_speech survives empty input", qwen.for_speech("") == "")


def test_mcp_config() -> None:
    connections = mcp_tools.connections()
    check("one server configured", len(connections) == 1, str(list(connections)))
    spec = next(iter(connections.values()))
    check("command is this interpreter", spec["command"] == sys.executable)
    check("args are absolute", all(os.path.isabs(arg) for arg in spec["args"]))
    check("args point at db.py", any(arg.endswith("db.py") for arg in spec["args"]))
    check("transport is stdio", spec.get("transport") == "stdio", str(spec.get("transport")))


def test_tts_plugin() -> None:
    tts = QwenTTS()
    check("tts sample rate is 24 kHz", tts.sample_rate == qwen.QWEN_SAMPLE_RATE, str(tts.sample_rate))
    check("tts is mono", tts.num_channels == 1)
    check("tts is not streaming", tts.capabilities.streaming is False)
    check("tts provider is qwen", tts.provider == "qwen")


def test_stt_plugin() -> None:
    stt = QwenSTT()
    check("stt provider is qwen", stt.provider == "qwen")
    check("stt is batch", stt.capabilities.streaming is False)
    check("stt model default", stt.model == "qwen3-asr-flash", stt.model)


def test_wav_bytes() -> None:
    rate = 48000
    frame = rtc.AudioFrame.create(rate, 1, rate // 2)      # 0.5 s of silence at 48 kHz
    data = wav_bytes([frame])

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "x.wav"
        path.write_bytes(data)
        with wave.open(str(path), "rb") as handle:
            check("wav is 16 kHz", handle.getframerate() == qwen.ASR_SAMPLE_RATE,
                  str(handle.getframerate()))
            check("wav is mono", handle.getnchannels() == 1)
            check("wav is 16-bit", handle.getsampwidth() == 2)
            seconds = handle.getnframes() / handle.getframerate()
    check("wav keeps the duration", abs(seconds - 0.5) < 0.05, f"{seconds:.3f}s")


def test_chat_context_conversion() -> None:
    ctx = llm.ChatContext()
    ctx.add_message(role="system", content="ignored")
    ctx.add_message(role="user", content="log a coffee for four dollars")
    ctx.add_message(role="assistant", content="Logged it.")
    ctx.add_message(role="user", content="   ")

    messages = to_langchain(ctx)
    check("drops the system message", len(messages) == 2, str(len(messages)))
    check("keeps the human turn", messages[0].type == "human", messages[0].type)
    check("keeps the reply", messages[1].type == "ai", messages[1].type)
    check("drops the empty turn", all(bool(m.content.strip()) for m in messages))


class FakeGraph:
    """Stands in for the compiled graph so the streaming filter can be tested."""

    def __init__(self, chunks):
        self._chunks = chunks

    def astream(self, state, stream_mode=None):
        async def gen():
            for chunk in self._chunks:
                yield chunk, {}

        return gen()


def test_stream_filter() -> None:
    tool_call = AIMessageChunk(
        content="",
        tool_call_chunks=[{"name": "create_expense", "args": "{}", "id": "c1", "index": 0}],
    )
    answer = AIMessageChunk(content="Logged the taxi for thirty dollars.")

    async def collect(chunks):
        ctx = llm.ChatContext()
        ctx.add_message(role="user", content="taxi, thirty dollars")
        return "".join([piece async for piece in stream_reply(FakeGraph(chunks), ctx, "cust")])

    text = asyncio.run(collect([tool_call, answer]))
    check("hides the tool call", "create_expense" not in text, text)
    check("keeps the answer", text == "Logged the taxi for thirty dollars.", text)

    empty = asyncio.run(collect([]))
    check("empty context returns nothing", empty == "", empty)


def test_token_helper() -> None:
    import make_token

    check("make_token does not shadow stdlib token", Path(make_token.__file__).name == "make_token.py")


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    try:
        test_categories()
        test_markdown_cleanup()
        test_mcp_config()
        test_tts_plugin()
        test_stt_plugin()
        test_wav_bytes()
        test_chat_context_conversion()
        test_stream_filter()
        test_token_helper()
    except Exception as exc:
        results.append((False, "unexpected error", f"{type(exc).__name__}: {exc}"))

    failed = 0
    for ok, name, detail in results:
        if not ok:
            failed += 1
        print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"   [{detail}]" if detail and not ok else ""))

    print(f"\n{len(results) - failed}/{len(results)} checks passed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
