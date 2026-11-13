"""One full turn without a microphone: speech file in, speech file out.

    uv run python smoke.py                          # speaks its own test question
    uv run python smoke.py --audio question.wav     # uses your recording
    uv run python smoke.py --question "Add $12 lunch" --no-play

This is the path to use in CI, on a server, or on a laptop with no microphone.
Every stage is timed, so the numbers in the README can be reproduced.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage

from assistant_graph import Agent, last_ai_text, stream_graph_response
from mcp_tools import load_tools
from voice_utils import for_speech, speak, stt_description, transcribe, tts_description

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "out"
DEFAULT_QUESTION = "Create an expense for the team lunch today. It cost fifteen dollars."

load_dotenv(ROOT / ".env")


def reconfigure_console() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


async def main() -> int:
    reconfigure_console()
    OUT.mkdir(exist_ok=True)

    parser = argparse.ArgumentParser(description="One measured voice turn, file based.")
    parser.add_argument("--audio", help="question audio (wav/mp3/m4a) instead of synthesizing one")
    parser.add_argument("--question", default=DEFAULT_QUESTION, help="text to synthesize as the question")
    parser.add_argument("--customer-id", default=os.environ.get("CUSTOMER_ID"), help="customer to act as")
    parser.add_argument("--no-play", action="store_true", help="write audio files but do not play them")
    args = parser.parse_args()

    if not args.customer_id:
        print("CUSTOMER_ID is not set. Run `uv run python seed.py` first.", file=sys.stderr)
        return 1
    play = not args.no_play

    timings: dict[str, float] = {}
    started = time.perf_counter()

    # 1 ---------------------------------------------------------- question ----
    if args.audio:
        question_audio = Path(args.audio).expanduser().resolve()
        if not question_audio.is_file():
            print(f"not found: {question_audio}", file=sys.stderr)
            return 1
        print(f"[1/4] question audio : {question_audio.name}")
    else:
        question_audio = OUT / "smoke-question.wav"
        print("[1/4] question audio : synthesizing with " + tts_description())
        try:
            report = await speak(args.question, out_path=question_audio, play=False)
            print(f"      {report['seconds']}s of speech, {report['latency']}s to generate")
        except Exception as exc:
            print(f"      FAILED: {exc}")
            print(
                "\n      Text to speech is not usable yet. You can still run the rest of\n"
                "      the pipeline with any audio file you already have:\n"
                "        uv run python smoke.py --audio your-recording.wav --no-play"
            )
            return 1

    # 2 --------------------------------------------------------------- STT ----
    print(f"\n[2/4] speech to text : {stt_description()}")
    text, info = await asyncio.to_thread(transcribe, question_audio)
    timings["stt"] = info["transcribe_seconds"]
    print(f"      heard: {text!r}")
    probability = info.get("language_probability")
    confidence = f" ({probability})" if probability is not None else ""
    print(
        f"      language={info['language']}{confidence}"
        f"  audio={info['audio_seconds']}s  stt={info['transcribe_seconds']}s"
    )

    if not text.strip():
        print("\nSpeech to text returned nothing - the audio may be silent.", file=sys.stderr)
        return 1

    # 3 ------------------------------------------------------------- agent ----
    print("\n[3/4] agent         : DeepSeek + MCP tools")
    tools = await load_tools()
    print(f"      tools: {', '.join(tool.name for tool in tools)}")

    graph = Agent(tools=tools).graph
    config = {"configurable": {"thread_id": "smoke-1"}}

    llm_started = time.perf_counter()
    print()
    async for piece in stream_graph_response(
        {"messages": [HumanMessage(text)], "customer_id": args.customer_id},
        graph,
        config,
    ):
        print(piece, end="", flush=True)
    print()
    timings["llm"] = round(time.perf_counter() - llm_started, 2)

    messages = graph.get_state(config).values.get("messages", [])
    reply = last_ai_text(messages)
    if not reply:
        print("\nThe model returned no text.", file=sys.stderr)
        return 1

    # 4 --------------------------------------------------------------- TTS ----
    print(f"\n[4/4] text to speech : {tts_description()}")
    tts_error = ""
    reply_seconds = 0.0
    try:
        report = await speak(reply, out_path=OUT / "smoke-reply.wav", play=play)
        timings["tts"] = report["latency"]
        reply_seconds = report["seconds"]
        first = report.get("first_audio")
        first_text = f", first audio after {first}s" if first is not None else ""
        print(f"      {reply_seconds}s of audio in {report['latency']}s{first_text}")
    except Exception as exc:
        timings["tts"] = 0.0
        tts_error = str(exc)
        print(f"      FAILED: {tts_error}")
        print("      The text answer above is still valid. Fix the key and re-run.")

    timings["total"] = round(time.perf_counter() - started, 2)

    print("\n-- measured --")
    print(f"  stt   {timings['stt']:6.2f}s   question {info['audio_seconds']}s")
    print(f"  llm   {timings['llm']:6.2f}s   {len(messages)} messages in the thread")
    if tts_error:
        print("  tts     n/a   failed (see above)")
    else:
        print(f"  tts   {timings['tts']:6.2f}s   reply {reply_seconds}s")
    print(f"  total {timings['total']:6.2f}s")
    print(f"\nfiles: {question_audio}  {OUT / 'smoke-reply.wav'}")
    return 1 if tts_error else 0


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(main()))
    except KeyboardInterrupt:
        print("\nInterrupted.")
        raise SystemExit(130)
