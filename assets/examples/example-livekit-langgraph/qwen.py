"""DashScope HTTP calls: qwen3-tts-flash (speech) and qwen3-asr-flash (text).

This module knows nothing about LiveKit. It takes text or WAV bytes and returns
text or PCM bytes, so the two adapters in `livekit_stt.py` and `livekit_tts.py`
stay small and this part can be tested on its own.
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import re
from collections.abc import AsyncIterator

import httpx

QWEN_SAMPLE_RATE = 24000     # qwen3-tts-flash returns 24 kHz mono int16 PCM
ASR_SAMPLE_RATE = 16000      # we hand the recogniser 16 kHz mono WAV

BEIJING = "https://dashscope.aliyuncs.com/api/v1"
SINGAPORE = "https://dashscope-intl.aliyuncs.com/api/v1"

DEFAULT_TTS_MODEL = "qwen3-tts-flash"
DEFAULT_VOICE = "Cherry"
DEFAULT_LANGUAGE = "Auto"
DEFAULT_ASR_MODEL = "qwen3-asr-flash"

_MARKUP = re.compile(r"(\*\*|\*|__|`{1,3}|^#{1,6}\s)", re.MULTILINE)


# ------------------------------------------------------------------ config ----

def base_url() -> str:
    region = (os.environ.get("DASHSCOPE_REGION", "") or "beijing").lower()
    if region in {"singapore", "intl", "international", "ap-southeast-1"}:
        return SINGAPORE
    return BEIJING


def api_key() -> str:
    key = os.environ.get("DASHSCOPE_API_KEY", "").strip()
    if not key:
        raise RuntimeError(
            "DASHSCOPE_API_KEY is not set.\n"
            '  PowerShell (persist):  setx DASHSCOPE_API_KEY "sk-..."   # reopen the terminal\n'
            "  Get a key:             https://bailian.console.aliyun.com -> API key"
        )
    return key


def tts_model() -> str:
    return os.environ.get("QWEN_TTS_MODEL", "").strip() or DEFAULT_TTS_MODEL


def tts_voice() -> str:
    return os.environ.get("QWEN_TTS_VOICE", "").strip() or DEFAULT_VOICE


def tts_language() -> str:
    return os.environ.get("QWEN_TTS_LANGUAGE", "").strip() or DEFAULT_LANGUAGE


def asr_model() -> str:
    return os.environ.get("QWEN_ASR_MODEL", "").strip() or DEFAULT_ASR_MODEL


def asr_language() -> str:
    return os.environ.get("QWEN_ASR_LANGUAGE", "").strip().lower()


def for_speech(text: str) -> str:
    """Strip markdown so the voice does not read asterisks and backticks aloud."""
    clean = _MARKUP.sub("", text or "")
    clean = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", clean)
    return re.sub(r"\s+", " ", clean).strip()


def explain(status: int, body: str, service: str) -> str:
    try:
        payload = json.loads(body)
    except Exception:  # noqa: BLE001 - a non-JSON body is still worth showing
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
        "ModelNotFound": "that model is not available to this account; check the model name.",
    }
    hint = hints.get(code)
    text = f"{service} returned {status}: {message}"
    if not hint and code:
        text = f"{service} returned {status} [{code}]: {message}"
    return f"{text}\n      -> {hint}" if hint else text


# --------------------------------------------------------------------- TTS ----

async def speak_pcm(text: str) -> AsyncIterator[bytes]:
    """Yield raw 24 kHz mono int16 PCM chunks as DashScope produces them."""
    clean = for_speech(text)
    if not clean:
        return

    payload = {
        "model": tts_model(),
        "input": {
            "text": clean,
            "voice": tts_voice(),
            "language_type": tts_language(),
        },
    }

    async with httpx.AsyncClient(timeout=120.0) as client:
        async with client.stream(
            "POST",
            f"{base_url()}/services/aigc/multimodal-generation/generation",
            headers={
                "Authorization": f"Bearer {api_key()}",
                "Content-Type": "application/json",
                "X-DashScope-SSE": "enable",
            },
            json=payload,
        ) as response:
            if response.status_code != 200:
                body = (await response.aread()).decode("utf-8", "replace")
                raise RuntimeError(explain(response.status_code, body, "Qwen TTS"))

            async for line in response.aiter_lines():
                if not line.startswith("data:"):
                    continue
                body = json.loads(line[5:].strip())
                audio = ((body.get("output") or {}).get("audio") or {})
                data = audio.get("data") or ""
                if data:
                    yield base64.b64decode(data)
                elif body.get("code"):
                    raise RuntimeError(explain(200, json.dumps(body), "Qwen TTS"))


# --------------------------------------------------------------------- ASR ----

def transcribe_wav(wav: bytes, mime: str = "audio/wav") -> str:
    """qwen3-asr-flash: WAV bytes in, transcript out. Blocking."""
    encoded = base64.b64encode(wav).decode()
    options: dict = {"enable_itn": True}
    if asr_language() and asr_language() != "auto":
        options["language"] = asr_language()

    payload = {
        "model": asr_model(),
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
        f"{base_url()}/services/aigc/multimodal-generation/generation",
        headers={
            "Authorization": f"Bearer {api_key()}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=180.0,
    )
    if response.status_code != 200:
        raise RuntimeError(explain(response.status_code, response.text, "Qwen ASR"))

    body = response.json()
    choice = ((body.get("output") or {}).get("choices") or [{}])[0]
    message = choice.get("message") or {}
    parts = message.get("content") or []
    if isinstance(parts, str):
        return parts.strip()
    return " ".join(
        part.get("text", "").strip() for part in parts if isinstance(part, dict)
    ).strip()


async def transcribe_wav_async(wav: bytes) -> str:
    return await asyncio.to_thread(transcribe_wav, wav)
