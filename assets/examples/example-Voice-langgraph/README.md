# Voice agent: faster-whisper → LangGraph → Qwen3-TTS

A voice expense assistant. You speak, it hears you locally, reasons with
DeepSeek, calls database tools over MCP, and answers out loud in a Qwen voice.
ElevenLabs is supported as an alternative TTS engine, one env var away.

Adapted from [kenneth-liao/langgraph-voice-agent](https://github.com/kenneth-liao/langgraph-voice-agent),
which does the same thing with three OpenAI APIs. Here the three stages are
independent vendors, so you can see exactly what each one costs and where the
latency comes from.

> **qwen3-asr-flash is not a TTS model.** It is *speech recognition*
> (audio → text), so it cannot replace ElevenLabs. The matching model on the
> other side of the loop is **qwen3-tts-flash**, which is what this example
> uses by default. qwen3-asr-flash is available here as an optional replacement
> for faster-whisper (`STT_PROVIDER=qwen`), not for the voice.

---

## 1. What you get

| Stage | Engine | Runs where | Key needed |
|---|---|---|---|
| Speech to text | `faster-whisper` 1.2.1 (default, local) | your CPU, int8 | no |
| Speech to text (alt.) | `qwen3-asr-flash` over DashScope | Alibaba Model Studio | `DASHSCOPE_API_KEY` |
| Reasoning + tools | `deepseek-flash` via `langchain-deepseek` | DeepSeek API | `DEEPSEEK_API_KEY` |
| Text to speech | `qwen3-tts-flash` over DashScope (default) | Alibaba Model Studio | `DASHSCOPE_API_KEY` |
| Text to speech (alt.) | ElevenLabs `eleven_flash_v2_5` | ElevenLabs API | `ELEVENLABS_API_KEY` |
| Expense storage | PostgreSQL / Supabase, SQLAlchemy | your database | `SUPABASE_URI` |
| Tool transport | MCP over stdio (`mcp` 1.30, v1 SDK) | local subprocess | no |

Nothing about the audio leaves the machine until the transcript is sent to
DeepSeek. The reply leaves as text, and comes back as audio.

---

## 2. How it fits together

```
 microphone                            MCP (stdio)                PostgreSQL
     |                                      |                         |
  sounddevice -> 16 kHz WAV                 |                         |
     |                                      |                         |
  faster-whisper  ──text──>  LangGraph  ──tool call──>  db.py  ──SQL──>  expenses
  or qwen3-asr-flash            |  ^            (FastMCP)                 |
                              |  └──────────── tool result ────────────┘
                              |
                          reply text
                              |
              Qwen3-TTS-Flash (SSE, base64 PCM 24 kHz)
                    or ElevenLabs (PCM 16 kHz)
                              |
                    24 kHz PCM -> speakers + out/*.wav
```

Qwen streams audio in chunks, so playback starts on the first chunk instead of
waiting for the whole file. ElevenLabs streams raw PCM. Either way there is no
MP3 decoder and no ffmpeg in the project.

The graph is the reference project's shape, unchanged:

```
START -> assistant -> (tool calls?) -> tools -> assistant -> ... -> END
```

`assistant` is a DeepSeek call with the five MCP tools bound. `tools_condition`
routes to the `ToolNode` when the model asks for a tool, then back to
`assistant`. One `thread_id` in the checkpointer keeps the conversation.

---

## 3. Setup

```powershell
uv sync
```

That installs Python 3.12, faster-whisper 1.2.1, `av` 18.1.0 (pinned: PyAV 19
breaks faster-whisper 1.2.1), LangGraph, `langchain-mcp-adapters`, the MCP SDK,
SQLAlchemy and `psycopg` 3.

### 3.1 Keys

Two keys by default — DeepSeek for reasoning, DashScope for the voice:

```powershell
setx DEEPSEEK_API_KEY "sk-..."
setx DASHSCOPE_API_KEY "sk-..."    # https://bailian.console.aliyun.com -> API key
```

DashScope keys are **region-specific**: a Beijing key only works on
`dashscope.aliyuncs.com`, a Singapore key only on `dashscope-intl.aliyuncs.com`.
This example defaults to Beijing. If yours is from the Singapore console:

```powershell
# .env
DASHSCOPE_REGION=singapore
```

Other Qwen settings in `.env`:

| Variable | Default | Notes |
|---|---|---|
| `QWEN_TTS_MODEL` | `qwen3-tts-flash` | low-latency, multilingual |
| `QWEN_TTS_VOICE` | `Cherry` | also `Serena`, `Ethan`, `Chelsie`, … |
| `QWEN_TTS_LANGUAGE` | `Auto` | naming the language sounds better than `Auto` |

The example sets `QWEN_TTS_LANGUAGE=English` for the English smoke test. For
Chinese, use `Chinese` or `Auto`.

#### Choosing the recogniser

| Variable | Default | Notes |
|---|---|---|
| `STT_PROVIDER` | `whisper` | `whisper` (local, free) or `qwen` (cloud) |
| `WHISPER_MODEL` | `small` | ignored when `STT_PROVIDER=qwen` |
| `QWEN_ASR_MODEL` | `qwen3-asr-flash` | only for `STT_PROVIDER=qwen` |
| `QWEN_ASR_LANGUAGE` | empty | `zh`, `en`, …; empty auto-detects |

Both backends return the same `(text, info)` pair, so `smoke.py` and `main.py`
do not care which one is selected. Locally, whisper keeps audio on the machine
and costs nothing; Qwen transcribes a 45-second clip in 2.2 s instead of 14–16 s.

#### Using ElevenLabs instead

```powershell
setx ELEVENLABS_API_KEY "..."
# .env
TTS_PROVIDER=elevenlabs
```

A free ElevenLabs plan hits two separate walls, and the messages do not say so:

* **The key's own character limit.** Each key can carry a per-key quota, often
  `0` on a test key: `401 quota_exceeded: "… API key (…) quota of 0"`. Set
  *Character limit* on the key (10,000 is plenty) and save.
* **The voice.** Free plans cannot call **library voices** (Rachel, Domi, Josh …)
  over the API: `402 paid_plan_required: "Free users cannot use library voices
  via the API"`. Point `ELEVENLABS_VOICE_ID` at a voice in your own account, or
  upgrade.

`voice_utils._explain_elevenlabs()` prints both with the fix, so a failed
`smoke.py` tells you which one you hit.

### 3.2 Database

Supabase, exactly like the original project:

```powershell
cp .env.example .env
# paste Project settings -> Database -> Connection string (URI) into SUPABASE_URI
# then run generate_tables.sql in the Supabase SQL editor
```

The direct host (`db.<project>.supabase.co:5432`) needs port 5432 to be open on
your network. The pooler host (`aws-0-<region>.pooler.supabase.com:5432`) works
from more networks; both are fine, and this example only reads the URI.

There is no local server to start: the only database the code talks to is the one
in `SUPABASE_URI`.

### 3.3 Customer

```powershell
uv run python seed.py
# CUSTOMER_ID = 1cfa4b0d-...
# copy that line into .env
```

### 3.4 Check

```powershell
uv run python check.py
```

It verifies the interpreter, every package, the keys the selected TTS provider
needs, the database and its tables, the MCP server's tool list, and whether the
whisper model is cached. Each failure prints the command that fixes it.

---

## 4. Run

No microphone, one measured turn:

```powershell
uv run python smoke.py
```

It speaks its own test question with Qwen3-TTS, transcribes it with whisper,
runs the agent, and speaks the answer. Use `--audio file.wav` to substitute your
own recording, and `--no-play` to write the WAV files without touching the
speakers.

With a microphone:

```powershell
uv run python main.py
```

Speak, then press Enter as soon as you finish — the microphone records until
that keypress, and everything you say before it is one turn. To finish, say
"exit", "quit", "close the program" or "that's all", then press Enter; the agent
says goodbye and the program ends. Ctrl+C works too. Every turn is saved to
`out/`: the microphone side at 16 kHz, the Qwen reply at 24 kHz, each WAV already
at the right rate.

With the local recogniser the first thing it prints is
`Loading faster-whisper 'small'...`, then `Recogniser ready.` The model load is
the slow part of a cold start (about 7 s normally, once up to 47 s); doing it
before the first prompt keeps it out of your measured turn.

Offline checks (no network, no keys, no database):

```powershell
uv run python test_offline.py      # 56 checks
```

---

## 5. Measured on this machine

Ryzen 7 PRO 5850U (8C/16T), 14.8 GB RAM, no CUDA, Windows 11, Python 3.12.10.

| Stage | Setting | Measurement |
|---|---|---|
| STT | whisper `small`, CPU int8, beam 5, VAD on | 2.7–3.2× realtime (45.0 s → 14.0–16.5 s) |
| STT | whisper, one 4–6 s utterance | 5.6–7.4 s (per-call overhead dominates) |
| STT | whisper model load | 6.9 s warm, 47 s on a cold disk; `main.py` does it before the first prompt |
| STT | `qwen3-asr-flash`, 45.0 s clip | **20× realtime** (2.2 s) |
| STT | `qwen3-asr-flash`, 4.0 s clip | 0.96–1.08 s |
| LLM | `deepseek-flash`, thinking off, 1 tool | **first token 1.0 s**, whole turn 3.3 s (one run 12.4 s) |
| LLM | same, 5 tools in one turn | 6.4 s, 8 messages |
| TTS | `qwen3-tts-flash`, voice Cherry, SSE | **first audio 0.73–1.29 s** over 6 calls, median 0.87 s |
| TTS | 3.4–4.6 s of speech | 1.35–1.69 s total, median 1.60 s (one cold call took 3.58 s) |
| TTS | non-streaming comparison | ~2.0 s before any audio (why the code uses SSE) |
| Total | one create-expense turn, Qwen STT + Qwen TTS | **~18 s**, dominated by the model's tool turn |
| Total | same turn with local whisper | ~23 s |

The reply is intelligible, not merely non-empty: the 3.6 s Qwen clip for
*"I've logged the team lunch for fifteen dollars under meals."* transcribes back
as *"I've logged the team lunch for $15 on the meals."* — same amounts, same
intent, one preposition changed by whisper.

A short clip costs almost nothing in synthesis and everything in round trips:
the first chunk lands around 0.9 s, so a one-sentence reply is speaking before
the model would even have finished a non-streaming download.

The five-tool turn is worth seeing, because it exercises the loop rather than a
single call:

```
user: "…train ticket to Shanghai $85, taxi $12, client dinner $240,
       hotel $360, office supplies $20. Add all of these and tell me the total."

  < tool: create_expense {"name": "Train ticket to Shanghai", "amount": 85, "category": "travel"}
  < tool: create_expense {"name": "Taxi from station",       "amount": 12, "category": "travel"}
  < tool: create_expense {"name": "Client dinner",           "amount": 240, "category": "meals"}
  < tool: create_expense {"name": "Hotel",                   "amount": 360, "category": "lodging"}
  < tool: create_expense {"name": "Office supplies",         "amount": 20,  "category": "office_supplies"}

answer: "All five expenses are logged … That comes to seven hundred and
         seventeen dollars in total."
```

Eight messages, five tool results, correct arithmetic, one graph invocation.

---

## 6. Files

| File | What it is |
|---|---|
| `main.py` | microphone loop: record → transcribe → agent → speak |
| `smoke.py` | same turn without a microphone; prints a timing table |
| `voice_utils.py` | STT, TTS and recording. The only file that touches audio |
| `assistant_graph.py` | `Agent`, the DeepSeek model, and the stream printer |
| `state.py` | `AgentState`: messages + customer_id |
| `mcp_tools.py` | reads `mcps/mcp_config.json`, starts the server, returns tools |
| `mcps/local_servers/db.py` | the FastMCP server: 5 expense tools |
| `mcps/mcp_config.json` | server definition, same shape Claude Desktop uses |
| `categories.py` | the 9 expense categories, shared by prompt and server |
| `seed.py` | creates tables and a demo customer |
| `check.py` | readiness report with fixes |
| `test_offline.py` | 56 deterministic checks |
| `generate_tables.sql` | the Supabase schema, unchanged from the original |

---

## 7. Why these three swaps

**STT: faster-whisper instead of the Whisper API.** It is free, works offline,
and on this CPU it runs 2.7–3.2× realtime — a 15-second utterance is transcribed
in about 5 seconds, which fits inside a conversation turn. You give up the API's
speed on a GPU-less machine and you own the model download (464 MB for `small`,
cached after the first run). Use `WHISPER_MODEL=base` for roughly 3× faster
drafting, `medium` when accuracy matters more than latency.

If you already have a DashScope key, `STT_PROVIDER=qwen` swaps in
`qwen3-asr-flash` without touching another file: 2.2 s for the same 45 s clip,
and under 1.1 s for a short utterance. The trade is the one you would expect —
the audio leaves the machine. Keep whisper when it must not.

**LLM: DeepSeek instead of GPT-4.1-mini.** The graph only needs reliable tool
calling and short spoken answers, and `deepseek-flash` does both. Thinking is
disabled (`extra_body={"thinking": {"type": "disabled"}}`) because a voice turn
needs its first token immediately, not a reasoning trace.

**TTS: Qwen3-TTS-Flash instead of OpenAI TTS.** Voice quality and latency both
matter in a voice agent, and `qwen3-tts-flash` answers with the first audio chunk
in under a second. It is also the model that matches the key many readers already
have. The code asks for SSE and plays base64 PCM at 24 kHz as it arrives, so
there is no MP3 decoder and no ffmpeg anywhere. ElevenLabs stays as a second
backend (`TTS_PROVIDER=elevenlabs`), because it has a nicer voice than most
free options; its `pcm_16000` output drops straight into the same player.

Note the model naming, since it is the easiest thing to get wrong here:
`qwen3-asr-flash` is **speech recognition**, `qwen3-tts-flash` is **speech
synthesis**. The first one would replace faster-whisper, not the voice.

**Kept: MCP + PostgreSQL.** The tools still run as a separate stdio MCP server
over SQLAlchemy, exactly as in the original, so the agent code never imports the
database. That is what makes `db.py` swappable for any other tool server.

---

## 8. Differences from the source project

| Area | Original | Here |
|---|---|---|
| LLM | `ChatOpenAI` `gpt-4.1-mini` | `ChatDeepSeek` `deepseek-flash`, thinking off |
| STT | OpenAI `whisper-1` API | local `faster-whisper`; optional `qwen3-asr-flash` |
| TTS | OpenAI `gpt-4o-mini-tts`, MP3 | Qwen3-TTS-Flash, SSE PCM 24 kHz (ElevenLabs optional) |
| Audio | `scipy.io.wavfile`, `LocalAudioPlayer` | `wave` + `sounddevice` (no scipy, no MP3) |
| DB driver | `psycopg2-binary` | `psycopg` 3 (SQLAlchemy 2.1's default) |
| SQL results | `pandas.DataFrame.to_json` | `json.dumps` (pandas dropped) |
| Categories | imported from `db.py` (opens a DB connection at import) | `categories.py`, no side effects |
| Config | `.env` only | `.env` + `mcps/mcp_config.json` |

Four bugs in the original `db.py` are fixed, because they silently break tools:

1. `filter(DBExpense.id == id and DBExpense.customer_id == customer_id)` — Python
   `and` on two SQL expressions evaluates to one expression, so the customer
   check was dropped. Now two separate filter clauses.
2. `if amount:` skipped an amount of `0`. Now `if amount is not None`.
3. `SET app.customer_id = :param` — PostgreSQL's `SET` does not accept bind
   parameters. Now `SELECT set_config('app.customer_id', :cid, true)`.
4. `update_expense` and `delete_expense` now require the customer id, so one
   customer cannot touch another's rows by guessing a UUID.

---

## 9. Troubleshooting

**`Qwen TTS returned 401: InvalidApiKey`**
The key is valid, just from the other region. Beijing keys work on
`dashscope.aliyuncs.com`; Singapore keys only on `dashscope-intl.aliyuncs.com`.
Set `DASHSCOPE_REGION=singapore` in `.env` if the key came from the Singapore
console.

**`Qwen TTS returned 401 [Arrearage]`**
The Model Studio account is out of free quota or has an unpaid balance. That is
an account state, not a code problem — the console shows the remaining quota.

**Qwen returns no audio**
`QWEN_TTS_VOICE` must be a system voice (`Cherry`, `Serena`, `Ethan`,
`Chelsie`, …) and `QWEN_TTS_LANGUAGE` must be `Auto` or one of the nine named
languages. `voice_utils._explain_qwen()` prints the API's own message.

### ElevenLabs-specific

**`401 … missing the permission text_to_speech`**
The key is valid but scoped. ElevenLabs → API keys → your key → enable
**Text to Speech** (or create a key that has it), then `setx ELEVENLABS_API_KEY`
again. Restricted keys return 401 for every endpoint they are not scoped for, so
`/v1/models` failing too is the same cause.

**`401 quota_exceeded: "… API key (your_key_name) quota of 0"`**
Not an account problem: that individual key has a character limit of 0.
ElevenLabs → API keys → the key → **Character limit** → `10000` → save. No need
to change the key value or restart the terminal.

**`402 paid_plan_required: "Free users cannot use library voices via the API"`**
The key and the plan are fine; the *voice* is not. Library voices (Rachel, Domi,
Josh, Elli, Sam …) need a paid plan when called over the API. Either upgrade, or
point `ELEVENLABS_VOICE_ID` at a voice in your own account:

```powershell
# .env
TTS_PROVIDER=elevenlabs
ELEVENLABS_VOICE_ID=<the id from ElevenLabs -> Voices -> your voice>
```

Verify either backend in one call before running the whole turn:

```powershell
uv run python -c "import asyncio, voice_utils; print(asyncio.run(voice_utils.speak('Test.', play=False)))"
```

**`'charmap' codec can't encode` or `?????` in the console**
Old Windows code pages. The scripts already force UTF-8 on stdout; if the
terminal still mangles non-ASCII, run once per session:

```powershell
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
```

**`sounddevice` errors / no microphone**
`uv run python check.py` proves everything else works without audio. Use
`smoke.py --audio your.wav` to test the pipeline, and `--no-play` to skip
speakers. List devices with
`uv run python -c "import sounddevice; print(sounddevice.query_devices())"`.

**The first transcription hangs**
`huggingface.co` is unreachable on some networks. `voice_utils` detects that and
switches to `hf-mirror.com` automatically, or set it yourself:
`$env:HF_ENDPOINT = "https://hf-mirror.com"`.

**`Could not load model 'small'` / `open() got an unexpected keyword argument 'metadata_errors'`**
PyAV 19 is incompatible with faster-whisper 1.2.1. `pyproject.toml` pins
`av==18.1.0`; restore it with `uv sync`.

**Database unreachable**
Check `SUPABASE_URI`. The Supabase direct host needs your network to allow port
5432; the pooler host (`...pooler.supabase.com:5432`) is the fallback. Both
connection strings are on Project settings → Database.

**The agent answers in markdown and it sounds terrible**
`voice_utils.for_speech()` strips the usual markup before synthesis, and the
system prompt asks for speech-first answers. Extend `for_speech` if your model
invents new formatting.

---

## 10. Cost per turn

| Stage | Unit | Notes |
|---|---|---|
| STT | free / Qwen audio tokens | local whisper costs nothing; `qwen3-asr-flash` bills per audio second |
| LLM | DeepSeek tokens | a 5-tool turn used ~8 messages; thinking is off |
| TTS | Qwen characters | `qwen3-tts-flash` bills per input character; a 60-character reply costs 60 |
| TTS (alt.) | ElevenLabs characters | billed per character of the reply, not per request |
| Database | free | Supabase free tier |

A spoken sentence costs far more to generate than to understand: the model's
reply is ~40 characters, the prompt is ~1,100 tokens of system prompt plus tool
schemas. If cost matters, shorten the system prompt before shortening the reply.
