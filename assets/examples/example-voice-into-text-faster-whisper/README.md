# Video → Text (faster-whisper)

Local, offline-capable speech-to-text for video and audio files, built on
[faster-whisper](https://github.com/SYSTRAN/faster-whisper). No ffmpeg install
needed, no API key, nothing uploaded anywhere.

---

## 1. Is your computer good enough? Yes.

`.\check.ps1` reports on this machine:

| | |
|---|---|
| CPU | AMD Ryzen 7 PRO 5850U — 8 cores / 16 threads |
| RAM | 14.8 GB |
| GPU | AMD Radeon iGPU (no CUDA) |
| Disk free | ~118 GB |
| OS | Windows 11 (Chinese), Python 3.12.10 |

There is no NVIDIA GPU, so it runs on the **CPU with int8 quantization**. That is
the normal, supported path — you just get roughly 3x realtime instead of 10x.

**Measured on your machine** (85 s of English speech, 16 threads, `beam_size=5`, VAD on):

| Model | Speed | 1 h video takes | Disk | RAM while running | Use when |
|---|---|---|---|---|---|
| `tiny` | ~18x realtime | ~5 min | 75 MB | ~0.5 GB | quick drafts, noisy audio |
| `base` | **8–9x realtime** | ~9 min | 141 MB | ~0.8 GB | fast drafts |
| `small` | **2.7–3.9x realtime** | ~18 min | 464 MB | ~1.2 GB | **default** — good accuracy |
| `medium` | **1.3x realtime** | ~45 min | 1.4 GB | ~2.5 GB | hard audio, accents |
| `large-v3` | ~0.7x realtime (est.) | ~85 min | 3.1 GB | ~4 GB | best accuracy, patience |

Everything fits in your RAM. `small` is the sweet spot: accurate enough for
meetings/lectures, 3x faster than the audio length.

---

## 2. One-time setup (uv)

[uv](https://docs.astral.sh/uv/) 0.8.22 is already installed at
`C:\Users\Henry Huang\.local\bin\uv.exe`. Dependencies live in `pyproject.toml`
and are pinned exactly in `uv.lock`, so setup is one command:

```powershell
uv sync      # creates .venv and installs everything (~1 min, then cached)
```

Already done here: `.venv` was built by uv with `faster-whisper 1.2.1`,
`ctranslate2 4.8.5`, `av 18.1.0`, Python 3.12 (pinned in `.python-version`).

Useful uv commands for this project:

```powershell
uv run transcribe.py video.mp4     # run without activating anything
uv add "av<19"                     # change a dependency, updates uv.lock
uv sync --upgrade                  # refresh all packages
uv lock --check                    # verify .venv matches uv.lock
uv export --format requirements-txt > requirements.txt   # pip fallback
```

(`av` is pinned below 19 because faster-whisper 1.2.1 is incompatible with
PyAV 19 — see troubleshooting.)

You do **not** need ffmpeg.exe: PyAV decodes the audio track straight out of
`.mp4/.mkv/.mov/.webm/...`.

---

## 3. Transcribe a video

```powershell
uv run transcribe.py "D:\videos\meeting.mp4"
```

or, with the wrapper (same thing, shorter, uses the same `.venv`):

```powershell
.\transcribe.ps1 "D:\videos\meeting.mp4"
```

That's it. With no options you get:

```
Model      : small  (cpu, int8, 16 threads)
Files      : 1
Model found in the local cache - loading offline.
Model ready in 2.2s

[1/1] meeting.mp4
      language=en (p=1.00)  duration=1m26s
         5.9%  Artificial intelligence has changed the way we work with language.
        11.3%  Speech recognition is one of the most practical applications,
       ...
      done in 0m27s (3.2x realtime)
      -> meeting.txt, meeting.srt in D:\videos
```

Output lands next to the video:

- `meeting.txt` — plain text
- `meeting.srt` — subtitles with timestamps (plus `.vtt`, `.json`, `.md` on request)

### Common variants

```powershell
# Chinese video, best-subtitle output
.\transcribe.ps1 "D:\videos\讲座.mp4" --language zh --format srt txt vtt

# higher accuracy for a difficult recording
.\transcribe.ps1 talk.mp4 --model medium

# everything, with per-word timings
.\transcribe.ps1 clip.mp4 -m medium -f txt srt vtt json --word-timestamps

# translate any language into English text
.\transcribe.ps1 interview.mkv --task translate

# a whole folder, written into .\out
.\transcribe.ps1 "D:\recordings" -o out -f txt md

# help names/terms get spelled right
.\transcribe.ps1 demo.mp4 --initial-prompt "faster-whisper, CTranslate2, OpenCode"
```

`.\transcribe.ps1` is just a thin, argument-safe wrapper around:

```powershell
uv run transcribe.py video.mp4 --model small     # canonical uv way
.\.venv\Scripts\python.exe transcribe.py video.mp4   # no uv at all
```

### All options

```
inputs                 video/audio files, or folders
-m, --model            tiny|base|small|medium|large-v3|distil-large-v3, or a local dir
-l, --language         zh, en, ja, ...   (omit = auto-detect)
-t, --task             transcribe | translate (-> English)
-f, --format           txt srt vtt json md
-o, --output-dir       default: next to the input
-d, --device           auto | cpu | cuda
-c, --compute-type     int8 | float16 | float32 ...
--threads              CPU threads (default: all)
--beam-size            default 5 (lower = faster)
--no-vad               keep silence instead of skipping it
--initial-prompt       hint with names and jargon
--max-line-width 40    wrap subtitle lines at N characters
--timestamps           add [00:00:06.130] prefixes in the .txt
--word-timestamps      per-word timing in the .json
--overwrite            replace existing output files
```

---

## 4. About models (do I need to download one?)

Yes, once. The first run downloads it automatically to
`C:\Users\Henry Huang\.cache\huggingface\hub` and every later run loads it in
~2 s. Nothing else to do.

**Your network cannot reach `huggingface.co`** (connection timeout — the model
download failed until this was fixed). `transcribe.py` now detects that and
automatically switches to the `https://hf-mirror.com` mirror. If you prefer to
set it yourself, or want it in a different terminal:

```powershell
$env:HF_ENDPOINT = "https://hf-mirror.com"
```

Disk usage of downloaded models so far: tiny 75 MB, base 141 MB, small 464 MB,
medium 1.4 GB. Delete them with:

```powershell
Remove-Item "$env:USERPROFILE\.cache\huggingface\hub\models--Systran--faster-whisper-medium" -Recurse
```

Benchmark your own machine on your own file:

```powershell
.\benchmark.ps1 "D:\videos\sample.mp4" --models base small medium
```

---

## 5. Troubleshooting

**`open() got an unexpected keyword argument 'metadata_errors'`**
PyAV 19 broke faster-whisper 1.2.1. `pyproject.toml` already pins `av==18.1.0`;
if something upgraded it: `uv add "av==18.1.0"` (or `uv sync` to restore the lock).

**Download hangs / `ConnectTimeout` to huggingface.co**
Blocked network. The script falls back to `hf-mirror.com` automatically; set
`HF_ENDPOINT` manually if it does not.

**Transcription is slower than expected**
- First run includes the model download; measure the second run.
- Timestamps: `--threads 8` can be *better* than 16 on laptops (less thermal
  throttling).
- `--beam-size 1` roughly doubles speed with a small accuracy cost.
- Plugging in the charger helps: the 5850U throttles hard on battery.

**`No speech detected`**
The clip may be music/silence-only, or the speech is too quiet. Try
`--no-vad` and/or a bigger model.

**Wrong language detected on short clips**
Pass `--language zh` (or `en`, `ja`, ...) explicitly; auto-detect needs ~30 s of
speech to be confident.

**Some words are wrong**
Normal for `tiny`/`base`. Use `--model medium` for the hard parts, or
`--initial-prompt "CorrectName, 专业术语"` to bias the recognizer.

---

## 6. Files here

| File | What it is |
|---|---|
| `transcribe.py` | main CLI: transcribe, translate, batch, subtitles |
| `transcribe.ps1` | wrapper that uses `.venv` and passes flags through unchanged |
| `check.ps1` | system + environment report (CPU/RAM/GPU, packages, cached models) |
| `benchmark.py` / `benchmark.ps1` | times each model on one file |
| `pyproject.toml` | dependencies (`faster-whisper`, `av==18.1.0`) |
| `uv.lock` | exact resolved versions - commit this, `uv sync` reproduces it |
| `.python-version` | pins Python 3.12 for uv |
| `.venv/` | the uv-managed environment (delete + `uv sync` to recreate) |

Everything runs locally. No audio leaves your computer.
