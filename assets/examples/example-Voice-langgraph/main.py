"""Talk to the agent out loud.

    uv run python main.py

The microphone records until you press Enter, so speak first and press Enter
when you finish. Say "exit", "quit", "close the program" or "that's all" (then
Enter) to end the session; Ctrl+C also works. Every turn is written to `out/` as
WAV so you can listen again later.

No microphone? Use `smoke.py`, which takes an audio file instead.
"""

from __future__ import annotations

import asyncio
import os
import re
import sys
from pathlib import Path

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage

from assistant_graph import Agent, intro_message, last_ai_text, stream_graph_response
from mcp_tools import load_tools
from voice_utils import (
    load_stt,
    record_audio_until_stop,
    speak,
    stt_model,
    stt_provider,
    transcribe,
    tts_provider,
)

load_dotenv(Path(__file__).resolve().parent / ".env")

OUT = Path(__file__).resolve().parent / "out"

# People rarely say the word "exit" to a voice assistant. "Close the program" and
# "that's all" are just as final, so match the intent, not one keyword.
EXIT_ALONE = {"exit", "quit", "bye", "goodbye", "stop", "done", "close"}
EXIT_PHRASE = re.compile(
    r"\b(?:exit|quit)\b"
    r"|\b(?:close|shut|end|stop|terminate|kill)\b(?:\W+\w+){0,4}\W+"
    r"(?:program|app|application|session|conversation|chat|assistant|everything)\b"
    r"|\b(?:that'?s all|that is all|i'?m done|we'?re done|no more|good ?bye)\b",
    re.IGNORECASE,
)


def reconfigure_console() -> None:
    """Windows consoles default to a legacy code page; force UTF-8."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def spoken_words(text: str) -> str:
    """Lowercase words only: 'Exit.' and 'exit!' both become 'exit'."""
    words = re.sub(r"[^\w\s']", " ", text or "").split()
    return " ".join(words).lower()


def wants_to_stop(text: str) -> bool:
    normalized = spoken_words(text)
    if not normalized:
        return False
    if normalized in EXIT_ALONE:
        return True
    return bool(EXIT_PHRASE.search(normalized))


async def run_turn(graph, config: dict, message, turn: int, play: bool = True) -> str:
    """Send one message, print the streamed reply, speak it, return the text."""
    print(f"\n---- {graph.name} ----\n")
    async for piece in stream_graph_response(
        {"messages": [message], "customer_id": os.environ.get("CUSTOMER_ID", "")},
        graph,
        config,
    ):
        print(piece, end="", flush=True)
    print()

    state = graph.get_state(config)
    reply = last_ai_text(state.values.get("messages", []))

    if reply:
        try:
            report = await speak(reply, out_path=OUT / f"turn-{turn:02d}-reply.wav", play=play)
            print(
                f"      [voice {report['seconds']}s audio, {report['latency']}s latency]",
                flush=True,
            )
        except Exception as exc:
            print(f"\n[text to speech failed: {exc}]", flush=True)
            key = "ELEVENLABS_API_KEY" if tts_provider() == "elevenlabs" else "DASHSCOPE_API_KEY"
            print(f"      The conversation continues; fix {key} to hear replies.", flush=True)
    return reply


def missing_key() -> str:
    """The key the configured providers need, or "" when everything is present."""
    if tts_provider() == "elevenlabs" and not os.environ.get("ELEVENLABS_API_KEY"):
        return "ELEVENLABS_API_KEY"
    if "qwen" in {tts_provider(), stt_provider()} and not os.environ.get("DASHSCOPE_API_KEY"):
        return "DASHSCOPE_API_KEY"
    return ""


async def main() -> int:
    reconfigure_console()
    OUT.mkdir(exist_ok=True)

    missing = missing_key()
    if missing:
        print(
            f"{missing} is not set - run `uv run python check.py`.",
            file=sys.stderr,
        )
        return 1

    print("Connecting to the MCP server...", flush=True)
    tools = await load_tools()
    print(f"Tools: {', '.join(tool.name for tool in tools)}\n", flush=True)

    if stt_provider() == "whisper":
        # Loading the model is the slowest part of the first turn (seconds to a
        # minute on a cold disk), so do it before the user starts talking.
        print(f"Loading faster-whisper '{stt_model()}'...", flush=True)
        await asyncio.to_thread(load_stt)
        print("Recogniser ready.\n", flush=True)

    agent = Agent(tools=tools)
    graph = agent.graph
    config = {"configurable": {"thread_id": "voice-1"}}

    await run_turn(graph, config, intro_message(), turn=0)

    turn = 1
    while True:
        print(
            "\nSpeak now, then press Enter as soon as you finish.\n"
            "To finish the session, say \"exit\" (or \"close the program\") and press Enter.",
            flush=True,
        )
        audio = await record_audio_until_stop(OUT / f"turn-{turn:02d}-question.wav")
        text, info = await asyncio.to_thread(transcribe, audio)
        print(f"\n---- You ({info['transcribe_seconds']}s STT) ----\n\n{text}\n", flush=True)

        if not spoken_words(text):
            print("(heard nothing - speak first, then press Enter)", flush=True)
            continue
        if wants_to_stop(text):
            await speak("Goodbye.", out_path=OUT / "goodbye.wav")
            print("\nExit command received. Ending the conversation.")
            break

        reply = await run_turn(graph, config, HumanMessage(text), turn)
        if wants_to_stop(reply):
            print("\nThe agent said goodbye. Ending the conversation.")
            break
        turn += 1

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(main()))
    except KeyboardInterrupt:
        print("\nInterrupted.")
        raise SystemExit(130)
