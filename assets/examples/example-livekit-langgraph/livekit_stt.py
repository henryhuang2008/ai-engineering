"""qwen3-asr-flash as a LiveKit STT plugin.

LiveKit's STT interface is streaming-first. DashScope's recogniser is a
request/response call, so this is a batch STT and is wrapped at the call site:

    stt=stt.StreamAdapter(stt=QwenSTT(), vad=vad)

`StreamAdapter` uses VAD to cut the microphone stream into utterances, then
calls `recognize()` once per utterance. That is exactly what the terminal
example did by hand, with the press-Enter keypress replaced by silence.
"""

from __future__ import annotations

import io
import wave

from livekit import rtc
from livekit.agents import DEFAULT_API_CONNECT_OPTIONS, NOT_GIVEN, NotGivenOr, stt
from livekit.agents.utils import AudioBuffer

import qwen


def wav_bytes(frames: AudioBuffer, rate: int = qwen.ASR_SAMPLE_RATE) -> bytes:
    """Join LiveKit audio frames into one 16 kHz mono WAV."""
    if isinstance(frames, rtc.AudioFrame):
        frames = [frames]

    pcm = bytearray()
    for frame in frames:
        if frame.sample_rate == rate and frame.num_channels == 1:
            pieces = [frame]
        else:
            resampler = rtc.AudioResampler(
                input_rate=frame.sample_rate,
                output_rate=rate,
                num_channels=1,
            )
            pieces = resampler.push(frame) + resampler.flush()
        for piece in pieces:
            pcm.extend(bytes(piece.data))

    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(bytes(pcm))
    return buffer.getvalue()


class QwenSTT(stt.STT):
    """Batch speech-to-text over DashScope, one call per finished utterance."""

    def __init__(self, language: str | None = None) -> None:
        super().__init__(
            capabilities=stt.STTCapabilities(streaming=False, interim_results=False)
        )
        self._language = language

    @property
    def model(self) -> str:
        return qwen.asr_model()

    @property
    def provider(self) -> str:
        return "qwen"

    async def _recognize_impl(
        self,
        buffer: AudioBuffer,
        *,
        language: NotGivenOr[str] = NOT_GIVEN,
        conn_options=DEFAULT_API_CONNECT_OPTIONS,
    ) -> stt.SpeechEvent:
        wav = wav_bytes(buffer)
        chosen = language if language is not NOT_GIVEN else (self._language or "en")

        # DashScope is a blocking HTTP call; keep the event loop free.
        text = await qwen.transcribe_wav_async(wav)

        return stt.SpeechEvent(
            type=stt.SpeechEventType.FINAL_TRANSCRIPT,
            alternatives=[
                stt.SpeechData(language=chosen or "en", text=text, confidence=1.0)
            ],
        )
