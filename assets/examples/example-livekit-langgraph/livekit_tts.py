"""qwen3-tts-flash as a LiveKit TTS plugin.

DashScope streams base64 PCM over SSE. LiveKit's `ChunkedStream` is the right
shape for that: `_run()` pushes bytes into an `AudioEmitter` as they arrive, so
the room hears the first sentence while the rest is still being synthesized.
"""

from __future__ import annotations

from livekit.agents import DEFAULT_API_CONNECT_OPTIONS, tts, utils

import qwen


class QwenTTS(tts.TTS):
    def __init__(self) -> None:
        super().__init__(
            capabilities=tts.TTSCapabilities(streaming=False),
            sample_rate=qwen.QWEN_SAMPLE_RATE,
            num_channels=1,
        )

    @property
    def model(self) -> str:
        return qwen.tts_model()

    @property
    def provider(self) -> str:
        return "qwen"

    def synthesize(
        self,
        text: str,
        *,
        conn_options=DEFAULT_API_CONNECT_OPTIONS,
    ) -> tts.ChunkedStream:
        return QwenChunkedStream(tts=self, input_text=text, conn_options=conn_options)


class QwenChunkedStream(tts.ChunkedStream):
    async def _run(self, output_emitter: tts.AudioEmitter) -> None:
        output_emitter.initialize(
            request_id=utils.shortuuid("qwen_tts_"),
            sample_rate=qwen.QWEN_SAMPLE_RATE,
            num_channels=1,
            mime_type="audio/pcm",
        )
        async for chunk in qwen.speak_pcm(self._input_text):
            output_emitter.push(chunk)
        output_emitter.flush()
