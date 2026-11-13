"""Offline checks: no network, no API keys, no database.

    uv run python test_offline.py

Everything here is deterministic. The live path (Qwen TTS, DeepSeek) is
exercised by `smoke.py` instead.
"""

from __future__ import annotations

import os
import sys
import tempfile
import wave
from pathlib import Path

import categories
import mcp_tools
import voice_utils
from assistant_graph import last_ai_text
from langchain_core.messages import AIMessage, HumanMessage

results: list[tuple[bool, str, str]] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    results.append((bool(condition), name, detail))


def test_markdown_cleanup() -> None:
    raw = "**Done** — I logged `Team lunch` for [fifteen dollars](https://x.test)."
    clean = voice_utils.for_speech(raw)
    check("for_speech drops ** and backticks", "*" not in clean and "`" not in clean, clean)
    check("for_speech keeps the link label", "fifteen dollars" in clean, clean)
    check("for_speech keeps the words", "logged" in clean and "Team lunch" in clean, clean)
    check("for_speech survives empty input", voice_utils.for_speech("") == "", "")


def test_wav_roundtrip() -> None:
    pcm = b"\x00\x00" * (voice_utils.SAMPLE_RATE * 2)  # 2.0 s of silence
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "nested" / "x.wav"
        voice_utils.write_pcm_wav(pcm, path)
        with wave.open(str(path), "rb") as handle:
            check("wav is mono", handle.getnchannels() == 1)
            check("wav is 16-bit", handle.getsampwidth() == 2)
            check("wav is 16 kHz", handle.getframerate() == voice_utils.SAMPLE_RATE)
            seconds = handle.getnframes() / handle.getframerate()
        check("wav duration is 2.0 s", abs(seconds - 2.0) < 0.01, f"{seconds:.3f}s")
        check("wav_seconds agrees", abs(voice_utils.wav_seconds(path) - 2.0) < 0.01)

        # Qwen speaks at 24 kHz; the header has to carry that rate, not 16 kHz.
        pcm24 = b"\x00\x00" * voice_utils.QWEN_SAMPLE_RATE
        path24 = voice_utils.write_wav(pcm24, Path(tmp) / "qwen.wav", voice_utils.QWEN_SAMPLE_RATE)
        with wave.open(str(path24), "rb") as handle:
            check("qwen wav keeps 24 kHz", handle.getframerate() == voice_utils.QWEN_SAMPLE_RATE)
            seconds24 = handle.getnframes() / handle.getframerate()
        check("qwen wav duration is 1.0 s", abs(seconds24 - 1.0) < 0.01, f"{seconds24:.3f}s")


def test_tts_config() -> None:
    keys = (
        "TTS_PROVIDER",
        "DASHSCOPE_REGION",
        "QWEN_TTS_MODEL",
        "QWEN_TTS_VOICE",
        "QWEN_TTS_LANGUAGE",
        "STT_PROVIDER",
        "QWEN_ASR_MODEL",
    )
    saved = {key: os.environ.get(key) for key in keys}
    try:
        for key in keys:
            os.environ.pop(key, None)

        check("default provider is qwen", voice_utils.tts_provider() == "qwen")
        check("default qwen model", voice_utils.qwen_tts_model() == "qwen3-tts-flash")
        check("default qwen voice", voice_utils.qwen_voice() == "Cherry")
        check("default qwen base is Beijing", "dashscope.aliyuncs.com" in voice_utils.dashscope_base())
        check("description names the engine", "Qwen" in voice_utils.tts_description())

        check("default STT is local whisper", voice_utils.stt_provider() == "whisper")
        check("STT description names whisper", "whisper" in voice_utils.stt_description().lower())
        check("default ASR model", voice_utils.qwen_asr_model() == "qwen3-asr-flash")

        os.environ["TTS_PROVIDER"] = "elevenlabs"
        check("provider switches to elevenlabs", voice_utils.tts_provider() == "elevenlabs")
        check("description follows the switch", "ElevenLabs" in voice_utils.tts_description())

        os.environ["STT_PROVIDER"] = "qwen"
        check("STT switches to qwen", voice_utils.stt_provider() == "qwen")
        check("STT description follows", "Qwen" in voice_utils.stt_description())

        os.environ["DASHSCOPE_REGION"] = "singapore"
        check(
            "singapore uses the intl host",
            "dashscope-intl" in voice_utils.dashscope_base(),
            voice_utils.dashscope_base(),
        )
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def test_transcribe_silence() -> None:
    """Real faster-whisper run, local only: silence in, nothing out."""
    saved = os.environ.get("STT_PROVIDER")
    os.environ["STT_PROVIDER"] = "whisper"      # this check is about the local model
    try:
        pcm = b"\x00\x00" * voice_utils.SAMPLE_RATE * 2
        with tempfile.TemporaryDirectory() as tmp:
            path = voice_utils.write_pcm_wav(pcm, Path(tmp) / "silence.wav")
            text, info = voice_utils.transcribe(path)
            check("silence transcribes to empty", text.strip() == "", repr(text))
            check("stt reports audio length", info["audio_seconds"] > 0, str(info["audio_seconds"]))
            check("stt used the configured model", info["model"] == voice_utils.stt_model(), info["model"])
    finally:
        if saved is None:
            os.environ.pop("STT_PROVIDER", None)
        else:
            os.environ["STT_PROVIDER"] = saved


def test_mcp_config_resolution() -> None:
    resolved = mcp_tools.connections()
    check("one server configured", len(resolved) == 1, str(list(resolved)))
    db = resolved["db"]
    check("command is this interpreter", Path(db["command"]).name.startswith("python"), db["command"])
    check("args are absolute", Path(db["args"][0]).is_absolute(), db["args"][0])
    check("args point at db.py", db["args"][0].endswith("db.py"), db["args"][0])
    check("transport is stdio", db["transport"] == "stdio", db.get("transport", ""))


def test_categories() -> None:
    check("9 categories", len(list(categories.ExpenseCategory)) == 9)
    check("other is a category", categories.ExpenseCategory("other") is categories.ExpenseCategory.OTHER)
    check("prompt string is not empty", bool(categories.CATEGORY_NAMES))


def test_last_ai_text() -> None:
    messages = [
        HumanMessage("log lunch"),
        AIMessage(content="", tool_calls=[{"name": "create_expense", "args": {}, "id": "call_1"}]),
        AIMessage(content="Logged it for fifteen dollars."),
    ]
    check("picks the final answer", last_ai_text(messages) == "Logged it for fifteen dollars.")
    check("skips the tool-call message", "create_expense" not in last_ai_text(messages))
    check("empty history returns empty", last_ai_text([]) == "")


def test_exit_detection() -> None:
    """The stop words, plus phrases that a real session actually produced."""
    from main import wants_to_stop

    for phrase in ("exit", "Exit.", "quit", "Quit!", "bye", "goodbye"):
        check(f"stops on {phrase!r}", wants_to_stop(phrase), phrase)

    # Recorded in a real session, transcribed by qwen3-asr-flash: the user asked
    # to close the program instead of saying "exit".
    closing = [
        "No need. Just close the program, right now.",
        "I want to exit.",
        "Okay, exit now please.",
        "That's all, thank you.",
        "Shut down the assistant.",
    ]
    for phrase in closing:
        check(f"stops on {phrase!r}", wants_to_stop(phrase), phrase)

    keeping = [
        "How much I spend on meal.",
        "Changed lunch to $20 .",
        "Can you delete the last expense? Thank you.",
        "Change the latest one. Thank you.",
        "It says.",
        ".",
        "",
    ]
    for phrase in keeping:
        check(f"keeps listening on {phrase!r}", not wants_to_stop(phrase), phrase)


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    try:
        test_markdown_cleanup()
        test_wav_roundtrip()
        test_tts_config()
        test_mcp_config_resolution()
        test_categories()
        test_last_ai_text()
        test_exit_detection()
        test_transcribe_silence()
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
