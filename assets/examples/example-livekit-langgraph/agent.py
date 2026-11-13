"""A LiveKit voice agent whose brain is a LangGraph graph.

    uv run python agent.py dev

LiveKit owns the hard part of a voice loop: the room, microphone capture, VAD,
turn detection, interruptions, playback and the client UI. This file only wires
the three stages together:

    QwenSTT  ->  LangGraph (DeepSeek + MCP expense tools)  ->  QwenTTS

The graph streams its answer token by token, so speech starts before the model
has finished writing.
"""

from __future__ import annotations

import os
import sys

from dotenv import load_dotenv
from livekit.agents import (
    DEFAULT_API_CONNECT_OPTIONS,
    Agent,
    AgentSession,
    JobContext,
    WorkerOptions,
    cli,
    llm,
    stt,
)
from livekit.plugins import silero

from assistant_graph import build_graph, stream_reply
from livekit_stt import QwenSTT
from livekit_tts import QwenTTS
from mcp_tools import load_tools

GREETING = "Hi, I'm Luna, your expense manager. What would you like to log?"


class GraphSlot(llm.LLM):
    """A placeholder so the pipeline does not skip the turn.

    LiveKit's voice activity only runs the LLM stage when an LLM is configured.
    The real generation happens in `ExpenseAgent.llm_node`, which never calls
    this object; if it ever does, that is a bug worth failing loudly on.
    """

    @property
    def model(self) -> str:
        return "langgraph"

    @property
    def provider(self) -> str:
        return "langgraph"

    def chat(self, *, chat_ctx, tools=None, conn_options=DEFAULT_API_CONNECT_OPTIONS,
             parallel_tool_calls=None, tool_choice=None, extra_kwargs=None):
        raise NotImplementedError("the LangGraph agent supplies llm_node")


class ExpenseAgent(Agent):
    def __init__(self, graph, customer_id: str) -> None:
        super().__init__(
            instructions=(
                "You are Luna, a concise expense manager. Replies are spoken aloud."
            )
        )
        self._graph = graph
        self._customer_id = customer_id

    async def llm_node(self, chat_ctx, tools, model_settings):
        async for piece in stream_reply(self._graph, chat_ctx, self._customer_id):
            yield piece


async def entrypoint(ctx: JobContext) -> None:
    customer_id = os.environ.get("CUSTOMER_ID", "").strip()
    if not customer_id:
        raise RuntimeError("CUSTOMER_ID is not set - run `uv run python seed.py` first")

    await ctx.connect()

    tools = await load_tools()
    graph = build_graph(tools)

    vad = silero.VAD.load()
    session = AgentSession(
        vad=vad,
        # Qwen ASR is a request/response API, so VAD decides when to send it.
        stt=stt.StreamAdapter(stt=QwenSTT(), vad=vad),
        tts=QwenTTS(),
        llm=GraphSlot(),
        turn_handling={
            # "vad" keeps turn detection local. The default would call LiveKit
            # Cloud for the semantic turn detector, which needs credentials and
            # adds a round trip.
            "turn_detection": "vad",
            "endpointing": {"min_delay": 0.5, "max_delay": 3.0},
            "interruption": {"enabled": True, "mode": "vad"},
        },
    )

    await session.start(room=ctx.room, agent=ExpenseAgent(graph, customer_id))
    await session.say(GREETING)


def main() -> None:
    load_dotenv(".env")
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint))


if __name__ == "__main__":
    main()
