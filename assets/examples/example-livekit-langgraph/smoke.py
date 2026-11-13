"""One full turn without a microphone.

    uv run python smoke.py

It joins a fresh room, speaks a synthesized question into it, records whatever
the agent says, and prints the transcripts with timings. This is the same path a
browser takes, minus the human: QwenTTS -> your track -> agent -> QwenSTT ->
LangGraph -> QwenTTS -> the agent's track.
"""

from __future__ import annotations

import asyncio
import os
import time
import uuid
import wave
from pathlib import Path

from dotenv import load_dotenv
from livekit import api, rtc

import qwen

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "out"

QUESTION = "Create an expense for a taxi to the airport, thirty dollars."


def join_token(room: str, identity: str) -> str:
    key = os.environ.get("LIVEKIT_API_KEY", "devkey")
    secret = os.environ.get("LIVEKIT_API_SECRET", "secret")
    return (
        api.AccessToken(key, secret)
        .with_identity(identity)
        .with_grants(api.VideoGrants(room_join=True, room=room))
        .to_jwt()
    )


def frames_from_wav(path: Path, chunk_ms: int = 100) -> list[rtc.AudioFrame]:
    with wave.open(str(path), "rb") as handle:
        rate, channels = handle.getframerate(), handle.getnchannels()
        pcm = handle.readframes(handle.getnframes())
    step = int(rate * chunk_ms / 1000) * 2 * channels
    frames = []
    for start in range(0, len(pcm), step):
        block = pcm[start:start + step]
        frame = rtc.AudioFrame.create(rate, channels, len(block) // (2 * channels))
        frame.data.cast("B")[:] = block
        frames.append(frame)
    return frames


def write_wav(path: Path, frames: list[rtc.AudioFrame], rate: int, channels: int) -> float:
    pcm = bytearray()
    for frame in frames:
        pcm.extend(bytes(frame.data))
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(channels)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(bytes(pcm))
    return len(pcm) / (rate * channels * 2)


async def wait_for(predicate, timeout: float, step: float = 0.1) -> bool:
    deadline = time.perf_counter() + timeout
    while time.perf_counter() < deadline:
        if predicate():
            return True
        await asyncio.sleep(step)
    return False


async def main() -> int:
    load_dotenv(ROOT / ".env")
    OUT.mkdir(exist_ok=True)

    url = os.environ.get("LIVEKIT_URL", "ws://127.0.0.1:7880")
    room_name = f"smoke-{uuid.uuid4().hex[:8]}"

    # 1. synthesize the question with Qwen so the test stays hands-free
    print(f"[1/4] speaking the question with qwen3-tts-flash ...", flush=True)
    started = time.perf_counter()
    pcm = bytearray()
    async for chunk in qwen.speak_pcm(QUESTION):
        pcm.extend(chunk)
    question_path = OUT / "smoke-question.wav"
    with wave.open(str(question_path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(qwen.QWEN_SAMPLE_RATE)
        handle.writeframes(bytes(pcm))
    print(f"      {len(pcm) / (qwen.QWEN_SAMPLE_RATE * 2):.2f}s of speech in {time.perf_counter() - started:.2f}s")

    # 2. join the room and publish that speech as the microphone
    room = rtc.Room()
    transcripts: list[tuple[str, str]] = []
    agent_audio: list[rtc.AudioFrame] = []
    subscribed = asyncio.Event()

    room.on(
        "transcription_received",
        lambda segments, participant, _pub: transcripts.extend(
            (participant.identity, segment.text) for segment in segments if segment.final
        ),
    )

    def on_track(track, _publication, _participant):
        if track.kind != rtc.TrackKind.KIND_AUDIO:
            return

        async def record():
            stream = rtc.AudioStream(track, sample_rate=qwen.QWEN_SAMPLE_RATE)
            subscribed.set()
            async for event in stream:
                agent_audio.append(event.frame)

        asyncio.create_task(record())

    room.on("track_subscribed", on_track)

    print(f"[2/4] joining {room_name} ...", flush=True)
    await room.connect(url, join_token(room_name, "smoke"))
    source = rtc.AudioSource(qwen.QWEN_SAMPLE_RATE, 1)
    track = rtc.LocalAudioTrack.create_audio_track("question", source)
    options = rtc.TrackPublishOptions()
    options.source = rtc.TrackSource.SOURCE_MICROPHONE
    await room.local_participant.publish_track(track, options)

    # 3. the agent greets on its own; let it finish before we talk
    if not await wait_for(lambda: subscribed.is_set(), timeout=70):
        print("      the agent never published audio - is `uv run python agent.py dev` running?")
        return 1
    print("[3/4] agent joined; waiting for the greeting", flush=True)
    await asyncio.sleep(4.5)

    # 4. speak, in real time, the way a microphone would
    print("[4/4] sending the question", flush=True)
    spoken = time.perf_counter()
    for frame in frames_from_wav(question_path):
        await source.capture_frame(frame)
        await asyncio.sleep(0.1)

    # wait for the answer, then a moment for trailing audio
    before = len(transcripts)
    await wait_for(
        lambda: any(identity.startswith("agent") for identity, _ in transcripts[before:]),
        timeout=60,
    )
    await asyncio.sleep(3.0)

    seconds = write_wav(OUT / "smoke-agent.wav", agent_audio, qwen.QWEN_SAMPLE_RATE, 1)
    await room.disconnect()

    print("\n-- transcripts --")
    for identity, text in transcripts:
        speaker = "Luna" if identity.startswith("agent") else identity
        print(f"  {speaker:8} {text}")

    print("\n-- measured --")
    print(f"  question      {len(pcm) / (qwen.QWEN_SAMPLE_RATE * 2):.2f}s")
    print(f"  agent audio   {seconds:.2f}s captured while speaking")
    print(f"  round trip    {time.perf_counter() - spoken:.2f}s (question playback included)")
    print(f"  saved         {OUT / 'smoke-agent.wav'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
