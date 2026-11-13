"""Speech in and speech out.

STT : faster-whisper, fully local. No key, nothing leaves the machine.
TTS : Qwen3-TTS-Flash over DashScope (default), or ElevenLabs.

The microphone and whisper work at 16 kHz; Qwen returns 24 kHz. Each side is
played at its own rate, so no resampling and no ffmpeg is needed anywhere.

Qwen3-ASR-Flash is a *speech-to-text* model and cannot replace a TTS engine.
The matching TTS model is `qwen3-tts-flash`.
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import re
import time
import wave
from pathlib import Path

import numpy as np

SAMPLE_RATE = 16000          # microphone + whisper
QWEN_SAMPLE_RATE = 24000     # qwen3-tts-flash PCM

DASHSCOPE_BEIJING = "https://dashscope.aliyuncs.com/api/v1"
DASHSCOPE_SINGAPORE = "https://dashscope-intl.aliyuncs.com/api/v1"

DEFAULT_TTS_PROVIDER = "qwen"
DEFAULT_QWEN_TTS_MODEL = "qwen3-tts-flash"
DEFAULT_QWEN_VOICE = "Cherry"
DEFAULT_QWEN_LANGUAGE = "Auto"

ELEVEN_BASE = "https://api.elevenlabs.io/v1"
DEFAULT_ELEVEN_VOICE = "21m00Tcm4TlvDq8ikWAM"  # Rachel
DEFAULT_ELEVEN_MODEL = "eleven_flash_v2_5"

DEFAULT_STT_PROVIDER = "whisper"
DEFAULT_STT_MODEL = "small"
DEFAULT_QWEN_ASR_MODEL = "qwen3-asr-flash"

_MARKUP = re.compile(r"(\*\*|\*|__|`{1,3}|^#{1,6}\s)", re.MULTILINE)


# ------------------------------------------------------------------ config ----

def tts_provider() -> str:
    """`qwen` (default) or `elevenlabs`."""
    return (os.environ.get("TTS_PROVIDER", "").strip() or DEFAULT_TTS_PROVIDER).lower()


def dashscope_base() -> str:
    region = (os.environ.get("DASHSCOPE_REGION", "").strip() or "beijing").lower()
    if region in {"singapore", "intl", "international", "ap-southeast-1"}:
        return DASHSCOPE_SINGAPORE
    return DASHSCOPE_BEIJING


def dashscope_key() -> str:
    key = os.environ.get("DASHSCOPE_API_KEY", "").strip()
    if not key:
        raise RuntimeError(
            "DASHSCOPE_API_KEY is not set.\n"
            '  PowerShell (persist):  setx DASHSCOPE_API_KEY "sk-..."   # reopen terminal\n'
            "  Get a key:             https://bailian.console.aliyun.com -> API key"
        )
    return key


def qwen_voice() -> str:
    return os.environ.get("QWEN_TTS_VOICE", "").strip() or DEFAULT_QWEN_VOICE


def qwen_tts_model() -> str:
    return os.environ.get("QWEN_TTS_MODEL", "").strip() or DEFAULT_QWEN_TTS_MODEL


def qwen_language() -> str:
    return os.environ.get("QWEN_TTS_LANGUAGE", "").strip() or DEFAULT_QWEN_LANGUAGE


def eleven_key() -> str:
    key = os.environ.get("ELEVENLABS_API_KEY", "").strip()
    if not key:
        raise RuntimeError(
            "ELEVENLABS_API_KEY is not set.\n"
            '  PowerShell (persist):  setx ELEVENLABS_API_KEY "..."   # reopen terminal\n'
            "  Get a key:             https://elevenlabs.io/app/settings/api-keys"
        )
    return key


def eleven_voice_id() -> str:
    return os.environ.get("ELEVENLABS_VOICE_ID", "").strip() or DEFAULT_ELEVEN_VOICE


def eleven_model() -> str:
    return os.environ.get("ELEVENLABS_MODEL", "").strip() or DEFAULT_ELEVEN_MODEL


def stt_model() -> str:
    return os.environ.get("WHISPER_MODEL", "").strip() or DEFAULT_STT_MODEL


def stt_provider() -> str:
    """`whisper` (default, local) or `qwen` (qwen3-asr-flash over DashScope)."""
    return (os.environ.get("STT_PROVIDER", "").strip() or DEFAULT_STT_PROVIDER).lower()


def qwen_asr_model() -> str:
    return os.environ.get("QWEN_ASR_MODEL", "").strip() or DEFAULT_QWEN_ASR_MODEL


def stt_description() -> str:
    """One line for logs: which recogniser is in use."""
    if stt_provider() == "qwen":
        return f"Qwen '{qwen_asr_model()}'"
    return f"faster-whisper '{stt_model()}'"


def tts_description() -> str:
    """One line for logs: which engine, model and voice are in use."""
    if tts_provider() == "elevenlabs":
        return f"ElevenLabs '{eleven_model()}' voice {eleven_voice_id()}"
    return f"Qwen '{qwen_tts_model()}' voice {qwen_voice()} ({qwen_language()})"


def for_speech(text: str) -> str:
    """Strip markdown so the voice does not read asterisks and backticks aloud."""
    clean = _MARKUP.sub("", text or "")
    clean = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", clean)  # links -> label
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean


# --------------------------------------------------------------------- TTS ----

def write_wav(pcm: bytes, path: Path, rate: int = SAMPLE_RATE) -> Path:
    """Wrap raw mono int16 PCM in a WAV header."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(pcm)
    return path


def write_pcm_wav(pcm: bytes, path: Path) -> Path:
    """16 kHz variant, used by the microphone side."""
    return write_wav(pcm, path, SAMPLE_RATE)


def _explain_elevenlabs(status: int, body: str) -> str:
    """Turn an ElevenLabs error code into an instruction the reader can follow."""
    try:
        detail = json.loads(body).get("detail", {})
    except Exception:  # noqa: BLE001 - a non-JSON body is still worth showing
        detail = {}
    if not isinstance(detail, dict):
        detail = {}
    code = detail.get("code", "")
    message = detail.get("message", "") or body[:300]

    hints = {
        "quota_exceeded": (
            "the API key has its own character quota, and it is 0.\n"
            "      ElevenLabs -> API keys -> this key -> Character limit -> 10000 -> save"
        ),
        "paid_plan_required": (
            "this voice belongs to the voice library, which a free plan cannot use\n"
            "      over the API. Set ELEVENLABS_VOICE_ID to a voice in your own account,\n"
            "      or upgrade the plan."
        ),
        "missing_permissions": (
            "the key is valid but lacks the Text to Speech permission.\n"
            "      ElevenLabs -> API keys -> this key -> enable Text to Speech -> save"
        ),
    }
    hint = hints.get(code)
    text = f"ElevenLabs returned {status}: {message}"
    return f"{text}\n      -> {hint}" if hint else text


def _explain_qwen(status: int, body: str, service: str = "Qwen TTS") -> str:
    """DashScope errors are small JSON objects with a code and a message."""
    try:
        payload = json.loads(body)
    except Exception:  # noqa: BLE001
        payload = {}
    code = payload.get("code", "") or ""
    message = payload.get("message", "") or body[:300]

    hints = {
        "InvalidApiKey": (
            "the key does not belong to this region. Beijing and Singapore keys are\n"
            "      different; set DASHSCOPE_REGION=singapore only for a Singapore key."
        ),
        "Arrearage": "the DashScope account has an unpaid balance or an expired free quota.",
        "Throttling": "rate limited - wait a moment and retry.",
        "ModelNotFound": (
            "that model is not available to this account; check the model name in .env."
        ),
    }
    hint = hints.get(code)
    text = f"{service} returned {status}: {message}"
    if not hint and code:
        text = f"{service} returned {status} [{code}]: {message}"
    return f"{text}\n      -> {hint}" if hint else text


async def _speak_qwen(clean: str, out_path: Path | None, play: bool, started: float) -> dict:
    """Qwen3-TTS-Flash over DashScope SSE: base64 PCM chunks, played as they land."""
    import httpx

    url = f"{dashscope_base()}/services/aigc/multimodal-generation/generation"
    payload = {
        "model": qwen_tts_model(),
        "input": {
            "text": clean,
            "voice": qwen_voice(),
            "language_type": qwen_language(),
        },
    }

    pcm = bytearray()
    first_audio: float | None = None
    failure = ""

    stream = None
    if play:
        import sounddevice as sd

        stream = sd.RawOutputStream(samplerate=QWEN_SAMPLE_RATE, channels=1, dtype="int16")
        stream.start()

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream(
                "POST",
                url,
                headers={
                    "Authorization": f"Bearer {dashscope_key()}",
                    "Content-Type": "application/json",
                    "X-DashScope-SSE": "enable",
                },
                json=payload,
            ) as response:
                if response.status_code != 200:
                    body = (await response.aread()).decode("utf-8", "replace")
                    raise RuntimeError(_explain_qwen(response.status_code, body))

                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    body = json.loads(line[5:].strip())
                    audio = ((body.get("output") or {}).get("audio") or {})
                    data = audio.get("data") or ""
                    if not data:
                        if body.get("code"):
                            failure = json.dumps(body)
                        continue

                    chunk = base64.b64decode(data)
                    if first_audio is None:
                        first_audio = time.perf_counter() - started
                    pcm.extend(chunk)
                    if stream is not None:
                        await asyncio.to_thread(stream.write, chunk)
    finally:
        if stream is not None:
            stream.stop()
            stream.close()

    if not pcm:
        raise RuntimeError(
            _explain_qwen(200, failure)
            if failure
            else "Qwen TTS returned no audio. Check QWEN_TTS_MODEL and QWEN_TTS_VOICE."
        )

    seconds = len(pcm) / (QWEN_SAMPLE_RATE * 2)
    if out_path is not None:
        write_wav(bytes(pcm), out_path, QWEN_SAMPLE_RATE)
        out_path = Path(out_path)

    return {
        "seconds": round(seconds, 2),
        "bytes": len(pcm),
        "latency": round(time.perf_counter() - started, 2),
        "first_audio": round(first_audio, 2) if first_audio is not None else None,
        "voice": qwen_voice(),
        "model": qwen_tts_model(),
        "provider": "qwen",
        "path": str(out_path) if out_path else None,
        "text": clean,
    }


async def _speak_elevenlabs(clean: str, out_path: Path | None, play: bool, started: float) -> dict:
    """ElevenLabs PCM stream: 16 kHz, exactly the rate the microphone uses."""
    import httpx

    voice, model = eleven_voice_id(), eleven_model()
    url = f"{ELEVEN_BASE}/text-to-speech/{voice}/stream"
    payload = {
        "text": clean,
        "model_id": model,
        "voice_settings": {"stability": 0.5, "similarity_boost": 0.75},
    }

    pcm = bytearray()
    stream = None
    if play:
        import sounddevice as sd

        stream = sd.RawOutputStream(samplerate=SAMPLE_RATE, channels=1, dtype="int16")
        stream.start()

    first_audio: float | None = None
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream(
                "POST",
                url,
                params={"output_format": "pcm_16000"},
                headers={"xi-api-key": eleven_key(), "Accept": "audio/pcm"},
                json=payload,
            ) as response:
                if response.status_code != 200:
                    body = (await response.aread()).decode("utf-8", "replace")
                    raise RuntimeError(_explain_elevenlabs(response.status_code, body))
                async for chunk in response.aiter_bytes():
                    if not chunk:
                        continue
                    if first_audio is None:
                        first_audio = time.perf_counter() - started
                    pcm.extend(chunk)
                    if stream is not None:
                        await asyncio.to_thread(stream.write, chunk)
    finally:
        if stream is not None:
            stream.stop()
            stream.close()

    seconds = len(pcm) / (SAMPLE_RATE * 2)
    if out_path is not None:
        write_pcm_wav(bytes(pcm), out_path)
        out_path = Path(out_path)

    return {
        "seconds": round(seconds, 2),
        "bytes": len(pcm),
        "latency": round(time.perf_counter() - started, 2),
        "first_audio": round(first_audio, 2) if first_audio is not None else None,
        "voice": voice,
        "model": model,
        "provider": "elevenlabs",
        "path": str(out_path) if out_path else None,
        "text": clean,
    }


async def speak(text: str, out_path: Path | None = None, play: bool | None = None) -> dict:
    """Speak `text` with the configured provider and stream it to the speakers.

    TTS_PROVIDER=qwen (default)   -> Qwen3-TTS-Flash, 24 kHz PCM over SSE
    TTS_PROVIDER=elevenlabs       -> ElevenLabs, 16 kHz raw PCM

    Returns a small report: seconds of audio, bytes, latency, time to first audio.
    Writing `out_path` is optional but makes the output inspectable.
    """
    clean = for_speech(text)
    if not clean:
        raise ValueError("nothing to speak: the reply was empty after cleanup")

    if play is None:
        play = os.environ.get("VOICE_PLAY", "1") != "0"

    provider = tts_provider()
    started = time.perf_counter()
    if provider == "qwen":
        return await _speak_qwen(clean, out_path, play, started)
    if provider == "elevenlabs":
        return await _speak_elevenlabs(clean, out_path, play, started)
    raise ValueError(f"unknown TTS_PROVIDER={provider!r}; use 'qwen' or 'elevenlabs'")


# --------------------------------------------------------------------- STT ----

_MODELS: dict[str, object] = {}


def _device() -> tuple[str, str]:
    """Ask CTranslate2 what it can actually use; no CUDA here, so CPU int8."""
    try:
        import ctranslate2

        if ctranslate2.get_cuda_device_count() > 0:
            return "cuda", "float16"
    except Exception:
        pass
    return "cpu", "int8"


def _hf_mirror() -> None:
    """huggingface.co is blocked on some networks; hf-mirror.com is not."""
    if os.environ.get("HF_ENDPOINT"):
        return
    import socket

    try:
        socket.create_connection(("huggingface.co", 443), timeout=1.5).close()
        return
    except OSError:
        pass
    try:
        socket.create_connection(("hf-mirror.com", 443), timeout=1.5).close()
        os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
    except OSError:
        pass


def load_stt(name: str | None = None):
    """Load (and cache) a faster-whisper model. Blocking: call it in a thread."""
    from faster_whisper import WhisperModel

    name = name or stt_model()
    if name not in _MODELS:
        device, compute_type = _device()
        _hf_mirror()
        os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
        _MODELS[name] = WhisperModel(
            name,
            device=device,
            compute_type=compute_type,
            cpu_threads=os.cpu_count() or 4,
        )
    return name, _MODELS[name]


def _transcribe_whisper(audio: Path, language: str | None = None) -> tuple[str, dict]:
    """Local faster-whisper. Blocking: call it with asyncio.to_thread."""
    audio = Path(audio)
    if not audio.is_file():
        raise FileNotFoundError(audio)

    started = time.perf_counter()
    name, model = load_stt()
    load_seconds = time.perf_counter() - started

    segments, info = model.transcribe(
        str(audio),
        language=language or os.environ.get("WHISPER_LANGUAGE") or None,
        beam_size=5,
        vad_filter=True,
        vad_parameters={"min_silence_duration_ms": 500},
        condition_on_previous_text=False,
    )
    text = " ".join(segment.text.strip() for segment in segments).strip()

    return text, {
        "provider": "whisper",
        "model": name,
        "language": info.language,
        "language_probability": round(info.language_probability, 2),
        "audio_seconds": round(info.duration, 2),
        "load_seconds": round(load_seconds, 2),
        "transcribe_seconds": round(time.perf_counter() - started - load_seconds, 2),
    }


_MIME = {
    ".wav": "audio/wav",
    ".mp3": "audio/mpeg",
    ".m4a": "audio/mp4",
    ".flac": "audio/flac",
    ".ogg": "audio/ogg",
    ".opus": "audio/opus",
    ".webm": "audio/webm",
}


def _transcribe_qwen(audio: Path, language: str | None = None) -> tuple[str, dict]:
    """qwen3-asr-flash: audio as a base64 data URI, text back. Needs a key."""
    import httpx

    audio = Path(audio)
    if not audio.is_file():
        raise FileNotFoundError(audio)

    started = time.perf_counter()
    encoded = base64.b64encode(audio.read_bytes()).decode()
    mime = _MIME.get(audio.suffix.lower(), "audio/wav")

    options: dict = {"enable_itn": True}
    chosen = (language or os.environ.get("QWEN_ASR_LANGUAGE", "")).strip().lower()
    if chosen and chosen != "auto":
        options["language"] = chosen

    payload = {
        "model": qwen_asr_model(),
        "input": {
            "messages": [
                {
                    "role": "user",
                    "content": [{"audio": f"data:{mime};base64,{encoded}"}],
                }
            ]
        },
        "parameters": {"asr_options": options},
    }

    response = httpx.post(
        f"{dashscope_base()}/services/aigc/multimodal-generation/generation",
        headers={
            "Authorization": f"Bearer {dashscope_key()}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=180.0,
    )
    if response.status_code != 200:
        raise RuntimeError(_explain_qwen(response.status_code, response.text, "Qwen ASR"))

    body = response.json()
    choice = ((body.get("output") or {}).get("choices") or [{}])[0]
    message = choice.get("message") or {}
    parts = message.get("content") or []
    if isinstance(parts, str):
        text = parts.strip()
    else:
        text = " ".join(
            part.get("text", "").strip() for part in parts if isinstance(part, dict)
        ).strip()

    annotations = message.get("annotations") or []
    usage = body.get("usage") or {}

    return text, {
        "provider": "qwen",
        "model": qwen_asr_model(),
        "language": annotations[0].get("language", "") if annotations else "",
        "language_probability": None,
        "audio_seconds": usage.get("seconds", round(time.perf_counter() - started, 2)),
        "load_seconds": 0.0,
        "transcribe_seconds": round(time.perf_counter() - started, 2),
    }


def transcribe(audio: Path, language: str | None = None) -> tuple[str, dict]:
    """Speech file -> text with the configured backend. Blocking: use a thread."""
    provider = stt_provider()
    if provider == "qwen":
        return _transcribe_qwen(audio, language)
    if provider == "whisper":
        return _transcribe_whisper(audio, language)
    raise ValueError(f"unknown STT_PROVIDER={provider!r}; use 'whisper' or 'qwen'")


# --------------------------------------------------------------------- mic ----

async def record_audio_until_stop(out_path: Path) -> Path:
    """Record the microphone until Enter is pressed, then write a 16 kHz WAV."""
    import sounddevice as sd

    chunks: list[np.ndarray] = []
    recording = True

    def _record() -> None:
        nonlocal recording
        with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="int16") as stream:
            while recording:
                block, _ = stream.read(1024)
                chunks.append(block.copy())

    def _wait_for_enter() -> None:
        nonlocal recording
        try:
            input()
        except EOFError:
            pass
        recording = False

    loop = asyncio.get_running_loop()
    stop = loop.run_in_executor(None, _wait_for_enter)
    capture = loop.run_in_executor(None, _record)
    await stop
    await capture

    if not chunks:
        raise RuntimeError("no audio captured - is a microphone connected?")

    audio = np.concatenate(chunks, axis=0)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(out_path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(SAMPLE_RATE)
        handle.writeframes(audio.tobytes())
    return out_path


def wav_seconds(path: Path) -> float:
    with wave.open(str(path), "rb") as handle:
        return handle.getnframes() / float(handle.getframerate())
