# Voice agent: LiveKit + LangGraph

The same expense assistant as `example-Voice-langgraph`, rebuilt around a
LiveKit room. You talk in a browser, LiveKit carries the audio, and the same
three stages do the work:

**Qwen3-ASR → LangGraph (DeepSeek + MCP tools) → Qwen3-TTS**

The point of the exercise: LiveKit removes the parts of a voice agent you should
not be writing by hand — microphone capture, voice activity detection, knowing
when the user finished speaking, barge-in, playback, and the client UI. What is
left is the part that is actually yours.

---

## 1. What LiveKit replaces

| Job | `example-Voice-langgraph` | this example |
|---|---|---|
| Microphone | `sounddevice` + "press Enter to stop" | LiveKit room audio |
| When did the user stop talking? | you press Enter | Silero VAD + endpointing |
| Interrupting the agent | not possible | VAD interruption, audio stopped |
| Playback | `sounddevice` + a WAV writer | LiveKit publishes the agent's track |
| Client | the terminal | browser (or any LiveKit client) |
| Turning speech into one turn | hand-written loop | `AgentSession` pipeline |
| Barge-in / half-duplex | none | on by default |
| Audio files | `out/*.wav` | optional, for inspection |

What stays: the DashScope calls, the LangGraph graph, the MCP tools, and the
database.

---

## 2. How it fits together

```
 browser (client/index.html)
   │  mic track                         agent track
   ▼                                       ▲
 ┌──────────────────── LiveKit room ──────┴──────────┐
 │  ws://127.0.0.1:7880   (signalling)               │
 │  udp://127.0.0.1:7882  (media)                    │
 └───────────────┬───────────────────────────────────┘
                 │
        agent.py worker (your machine)
                 │
   Silero VAD -> QwenSTT (qwen3-asr-flash)
                 │  text
                 ▼
        LangGraph: DeepSeek + MCP expense tools
                 │  tokens
                 ▼
        QwenTTS (qwen3-tts-flash, 24 kHz PCM)
                 │
                 └────────► back to the room
```

The worker joins the room as a participant, so it never touches a microphone or
a speaker itself. The browser is just a room client with a Connect button.

---

## 3. What you get

| Stage | Engine | Runs where | Key |
|---|---|---|---|
| Transport | LiveKit server `v1.13.11` | Docker, local | dev key |
| VAD | Silero (`livekit-plugins-silero`) | worker process | — |
| Speech to text | `qwen3-asr-flash` | Alibaba Model Studio | `DASHSCOPE_API_KEY` |
| Reasoning + tools | `deepseek-flash` via LangGraph | DeepSeek API | `DEEPSEEK_API_KEY` |
| Text to speech | `qwen3-tts-flash`, 24 kHz PCM | Alibaba Model Studio | `DASHSCOPE_API_KEY` |
| Expense storage | Supabase / PostgreSQL | your database | `SUPABASE_URI` |
| Tool transport | MCP over stdio | local subprocess | — |

---

## 4. Setup

### 4.1 LiveKit server (Docker)

```powershell
docker compose up -d
docker compose logs -f livekit      # Ctrl+C to stop watching, the container keeps running
```

`docker-compose.yml` runs `livekit/livekit-server:v1.13.11` with
`livekit.yaml` mounted at `/etc/livekit.yaml`, and publishes:

| Port | Protocol | Use |
|---|---|---|
| 7880 | TCP | HTTP + WebSocket signalling |
| 7881 | TCP | WebRTC over TCP (fallback) |
| 7882 | UDP | WebRTC media (single shared port) |

`livekit.yaml` is local-only: key `devkey`, a 36-character dev secret, and
`udp_port: 7882`. That last line matters — a `port_range_start/end` of one port
allocates a port *per participant*, so the second participant gets no UDP
candidate and the agent times out. `udp_port` is the shared-port ("mux") form.

Stop it with `docker compose down`. The server has no persistence; rooms vanish
with it.

### 4.2 Python

```powershell
uv sync
```

### 4.3 Keys

```powershell
setx DEEPSEEK_API_KEY "sk-..."
setx DASHSCOPE_API_KEY "sk-..."      # https://bailian.console.aliyun.com
```

`.env` (copy `.env.example`) holds the rest: model names, voice, database URI,
`CUSTOMER_ID`, and the LiveKit URL/keys, which already match `docker-compose.yml`.

```powershell
uv run python check.py
```

It checks packages, keys, the LiveKit server's HTTP endpoint, the database, the
MCP tools, and that both Qwen plugins build.

### 4.4 Database and customer

Same as the other example: put a Supabase URI in `SUPABASE_URI`, then

```powershell
uv run python seed.py        # creates tables and a customer, prints CUSTOMER_ID
```

---

## 5. Run

Two terminals.

```powershell
# 1. the worker (stays in the foreground)
uv run python agent.py dev
```

```powershell
# 2. a join token for the browser
uv run python make_token.py            # room "expenses", identity "you"
```

Serve the client (a `file://` page cannot use the microphone, `localhost` can):

```powershell
cd client
python -m http.server 8000
```

Open <http://localhost:8000>, paste the token, press **Connect**, allow the
microphone. Luna greets you, then answer out loud — no keypress needed, silence
ends your turn.

Without a browser or a microphone:

```powershell
uv run python smoke.py
```

It joins a fresh room, publishes a synthesized question as its microphone,
records the agent's track, and prints the transcripts. This is the path that was
used to verify the example.

---

## 6. Measured on this machine

Ryzen 7 PRO 5850U, 14.8 GB RAM, Windows 11, Python 3.12.10, Docker Desktop 29.0.1.

| Stage | Measurement |
|---|---|
| `docker compose up -d` → server listening | ~2 s (image already pulled) |
| worker start → registered | ~3 s |
| room join → agent audio track | < 1 s (connection), then greeting |
| Qwen ASR, 4 s utterance | ~1.0 s |
| Qwen TTS, first audio chunk | 0.73–1.29 s (median 0.87 s) |
| Full turn, question playback included | ~25 s |
| Full turn without playback and tail wait | ~17 s, dominated by the DeepSeek tool turn (9–15 s) |
| Browser client → room → greeting transcript | verified: joins as `reviewer`, streams Luna's greeting |

The round trip is verified rather than assumed: the agent's track was recorded
and transcribed back.

```
Luna (from the recorded track)
  "Hi, I'm Luna, your expense manager. What would you like to log?
   Done. I logged the $30 for the taxi to the airport under travel."
```

Offline checks:

```powershell
uv run python test_offline.py      # 30 checks, no network
```

---

## 7. Files

| File | What it is |
|---|---|
| `agent.py` | worker entrypoint, `AgentSession`, `llm_node` |
| `assistant_graph.py` | the LangGraph graph and the token stream |
| `qwen.py` | DashScope HTTP: TTS over SSE, ASR as a data URI |
| `livekit_stt.py` | `stt.STT` adapter (batch, wrapped by `StreamAdapter`) |
| `livekit_tts.py` | `tts.TTS` adapter (`ChunkedStream` + `AudioEmitter`) |
| `make_token.py` | mints a join JWT for the client |
| `client/index.html` | browser client: connect, mic, live transcript |
| `docker-compose.yml` | the LiveKit server container |
| `livekit.yaml` | server config: ports, dev key, UDP mux |
| `mcp_tools.py` | MCP config → LangChain tools |
| `mcps/local_servers/db.py` | the FastMCP server: 5 expense tools |
| `categories.py` | the 9 expense categories |
| `seed.py` | tables + demo customer |
| `smoke.py` | one full turn with no microphone |
| `check.py` | readiness report |
| `test_offline.py` | 30 deterministic checks |

---

## 8. Is the code simpler?

Shorter, and organised around what you actually own:

| | terminal example | this example |
|---|---|---|
| App loop / entrypoint | `main.py` 175 lines | `agent.py` 119 lines |
| Audio plumbing | `voice_utils.py` 611 lines | `qwen.py` 194 + `livekit_stt.py` 88 + `livekit_tts.py` 50 |
| Total for audio + app | 786 lines | 451 lines |

The 611-line file mixed five concerns: DashScope, ElevenLabs, faster-whisper,
microphone recording, and WAV playback. LiveKit deletes the last two entirely
and provides the turn loop, so `agent.py` has no `while True`, no `input()`, no
`sounddevice`, and no exit-word detection.

The trade is real: you write two small plugin adapters (`stt.STT`, `tts.TTS`)
and run a media server. In exchange the agent gains barge-in, endpointing,
a browser client, and a path to telephony and multi-user rooms.

---

## 9. Troubleshooting

**The agent joins but there is no audio**
Check that only `udp_port` (not a one-port `port_range_start/end`) is configured.
With a single-port range the second participant silently falls back to TCP and
`wait_pc_connection` times out. `docker compose logs -f livekit` shows
`rtc.portUDP: {"Start":7882,"End":0}` when the mux form is active.

**`the agent never published audio` in `smoke.py`**
The worker is not running, or it cannot reach the server. Run
`uv run python check.py`; it probes `LIVEKIT_URL` over HTTP.

**The browser connects but the mic does nothing**
Serve the page over `http://localhost:8000`, not `file://`. Browsers only allow
`getUserMedia` in a secure context, and the page shows a yellow banner when it is
opened as a file.

If the banner is not shown and the status still says *microphone blocked*, the
permission was denied earlier: click the padlock in the address bar →
**Microphone → Allow**, then reload. On Windows 11 also check
**Settings → Privacy & security → Microphone → Let desktop apps access your
microphone**; Chrome inherits that block and reports only "Permission denied".

**The transcript appears but there is no sound**
The client attaches the agent's track on `RoomEvent.TrackSubscribed`. If the tab
was opened before that handler existed, hard-reload the page. Then check that the
tab is not muted and that the status line ends with *microphone on*. In DevTools,
`lunaRoom.canPlaybackAudio` should be `true`; if it is `false`, press
**Enable sound** (the browser blocked autoplay).

**`Qwen TTS returned 401: InvalidApiKey`**
Beijing and Singapore DashScope keys are different. Set
`DASHSCOPE_REGION=singapore` for an intl key.

**Everything answers in text but is silent in the room**
Watch the worker log: `tts_node` errors are printed there. The room stays open
even when TTS fails, which is deliberate.

---

## 10. Notes

* The dev key/secret in `livekit.yaml` and `.env.example` are for this machine
  only. Never reuse them on a network you do not control.
* `agent.py dev` is the Python CLI's hot-reload-free development mode; LiveKit
  now points at `lk agent dev` for the CLI workflow. The plain
  `uv run python agent.py start` runs a production-style worker.
* The LangGraph graph is compiled without a checkpointer: LiveKit's `ChatContext`
  is the conversation history, and the whole thread is passed in each turn.
* To use LiveKit Cloud instead of Docker, point `LIVEKIT_URL`,
  `LIVEKIT_API_KEY` and `LIVEKIT_API_SECRET` at the project and delete the
  compose file — nothing else changes.
