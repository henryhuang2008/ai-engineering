#!/usr/bin/env python3
"""
Video / audio -> text, using faster-whisper (CTranslate2 Whisper).

Examples
--------
    python transcribe.py video.mp4
    python transcribe.py video.mp4 --model medium --language zh
    python transcribe.py talk.mp4 --format srt,vtt --output-dir out
    python transcribe.py *.m4a --model small --task translate

No ffmpeg.exe needed: PyAV (bundled with faster-whisper) decodes the audio
stream straight out of the container.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

# ---------------------------------------------------------------- helpers ----

VIDEO_EXT = {
    ".mp4", ".mkv", ".mov", ".avi", ".webm", ".flv", ".wmv", ".m4v", ".mpg",
    ".mpeg", ".ts", ".m2ts", ".3gp", ".ogv",
}
AUDIO_EXT = {
    ".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".opus", ".wma", ".aiff",
}


def log(msg: str) -> None:
    """Progress goes to stdout so PowerShell pipes and redirection behave."""
    print(msg, flush=True)


def err(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def fmt_ts(seconds: float, sep: str = ",") -> str:
    """Seconds -> HH:MM:SS,mmm (SRT) or HH:MM:SS.mmm (VTT)."""
    if seconds < 0:
        seconds = 0.0
    ms = int(round(seconds * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d}{sep}{ms:03d}"


def human_dur(seconds: float) -> str:
    seconds = max(0, int(round(seconds)))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h}h{m:02d}m{s:02d}s" if h else f"{m}m{s:02d}s"


def safe_stem(path: Path) -> str:
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", path.stem).strip() or "output"


def reachable(host: str, timeout: float = 1.5) -> bool:
    import socket

    try:
        with socket.create_connection((host, 443), timeout=timeout):
            return True
    except OSError:
        return False


def enable_mirror_if_needed() -> str | None:
    """huggingface.co is blocked on some networks; use hf-mirror.com instead."""
    if os.environ.get("HF_ENDPOINT"):
        return os.environ["HF_ENDPOINT"]
    if reachable("huggingface.co"):
        return None
    if reachable("hf-mirror.com"):
        os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
        log("Note: huggingface.co is unreachable - using https://hf-mirror.com")
        return os.environ["HF_ENDPOINT"]
    return None


def model_is_cached(name: str) -> bool:
    """True if the model is a local folder or already in the HF cache."""
    if Path(name).expanduser().is_dir():
        return True
    try:
        from huggingface_hub import constants

        hub = Path(constants.HF_HUB_CACHE)
    except Exception:
        home = os.environ.get("HF_HOME") or str(Path.home() / ".cache" / "huggingface")
        hub = Path(home) / "hub"
    return (hub / f"models--Systran--faster-whisper-{name}" / "snapshots").is_dir()



def pick_device(requested: str) -> tuple[str, str]:
    """Return (device, compute_type) that actually works on this machine."""
    if requested == "cpu":
        return "cpu", "int8"

    try:
        import ctranslate2

        n_gpu = ctranslate2.get_cuda_device_count()
    except Exception:
        n_gpu = 0

    if n_gpu > 0:
        return "cuda", "float16"

    if requested == "cuda":
        log("! No CUDA device found - falling back to CPU (int8).")
    return "cpu", "int8"


# ----------------------------------------------------------------- output ----

def write_srt(segments, path: Path, width: int = 0) -> None:
    with path.open("w", encoding="utf-8-sig", newline="\n") as f:
        for i, seg in enumerate(segments, 1):
            f.write(f"{i}\n")
            f.write(f"{fmt_ts(seg['start'])} --> {fmt_ts(seg['end'])}\n")
            f.write(wrap_text(seg["text"].strip(), width) + "\n\n")


def write_vtt(segments, path: Path, width: int = 0) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as f:
        f.write("WEBVTT\n\n")
        for seg in segments:
            f.write(f"{fmt_ts(seg['start'], '.')} --> {fmt_ts(seg['end'], '.')}\n")
            f.write(wrap_text(seg["text"].strip(), width) + "\n\n")


def write_txt(segments, path: Path, timestamps: bool) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as f:
        if not timestamps:
            f.write("\n".join(s["text"].strip() for s in segments) + "\n")
            return
        for seg in segments:
            f.write(f"[{fmt_ts(seg['start'], '.')[:8]}] {seg['text'].strip()}\n")


def write_json(segments, path: Path, meta: dict) -> None:
    payload = {"meta": meta, "segments": segments}
    with path.open("w", encoding="utf-8", newline="\n") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.write("\n")


def paragraphs(segments, gap: float = 2.0) -> str:
    """Group segments into readable paragraphs when pauses are long enough."""
    out: list[str] = []
    buf: list[str] = []
    prev_end = None
    for seg in segments:
        if prev_end is not None and seg["start"] - prev_end > gap and buf:
            out.append(" ".join(buf))
            buf = []
        buf.append(seg["text"].strip())
        prev_end = seg["end"]
    if buf:
        out.append(" ".join(buf))
    return "\n\n".join(out) + "\n"


# ------------------------------------------------------------------- main ----

def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    ap = argparse.ArgumentParser(
        description="Transcribe video/audio to text with faster-whisper "
                    "(PyAV decodes the audio, no ffmpeg.exe needed).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""examples:
  python transcribe.py video.mp4
  python transcribe.py video.mp4 --model medium --language zh
  python transcribe.py talk.mp4 --format srt vtt --output-dir out
  python transcribe.py *.m4a --model small --task translate""",
    )
    ap.add_argument("inputs", nargs="+", help="video/audio files")
    ap.add_argument("-m", "--model", default="small",
                    help="tiny | base | small | medium | large-v3 | "
                         "distil-large-v3 | a local model dir "
                         "(default: small)")
    ap.add_argument("-l", "--language", default=None,
                    help="spoken language code, e.g. zh, en, ja. "
                         "Omit to auto-detect.")
    ap.add_argument("-t", "--task", default="transcribe",
                    choices=["transcribe", "translate"],
                    help="transcribe, or translate speech into English")
    ap.add_argument("-f", "--format", nargs="+", default=["txt,srt"],
                    metavar="FMT",
                    help="txt,srt,vtt,json,md - space or comma separated "
                         "(default: txt,srt)")
    ap.add_argument("-o", "--output-dir", default=None,
                    help="where to write results (default: next to the input)")
    ap.add_argument("-d", "--device", default="auto",
                    choices=["auto", "cpu", "cuda"])
    ap.add_argument("-c", "--compute-type", default=None,
                    help="override: int8, int8_float16, float16, float32")
    ap.add_argument("--threads", type=int, default=0,
                    help="CPU threads (0 = all cores)")
    ap.add_argument("--beam-size", type=int, default=5)
    ap.add_argument("--vad", dest="vad", action="store_true", default=True,
                    help="skip silence with Silero VAD (default: on)")
    ap.add_argument("--no-vad", dest="vad", action="store_false")
    ap.add_argument("--initial-prompt", default=None,
                    help="hint with names/terms, e.g. \"OpenCode, CTranslate2\"")
    ap.add_argument("--max-line-width", type=int, default=0,
                    help="wrap subtitle lines at N characters (0 = off)")
    ap.add_argument("--timestamps", action="store_true",
                    help="prefix each line in the .txt output with a timestamp")
    ap.add_argument("--word-timestamps", action="store_true",
                    help="include per-word timing in the .json output")
    ap.add_argument("--overwrite", action="store_true",
                    help="overwrite existing output files")
    args = ap.parse_args()

    try:
        from faster_whisper import WhisperModel
    except ImportError:
        err("faster-whisper is not installed.\n"
            "  uv sync")
        return 2

    fmts: list[str] = []
    for chunk in args.format:
        fmts += [f.strip().lower() for f in chunk.split(",") if f.strip()]
    bad = set(fmts) - {"txt", "srt", "vtt", "json", "md"}
    if bad:
        err(f"Unknown format(s): {', '.join(sorted(bad))}")
        return 2

    files: list[Path] = []
    for raw in args.inputs:
        p = Path(raw).expanduser()
        if p.is_dir():
            files += sorted(f for f in p.iterdir()
                            if f.suffix.lower() in VIDEO_EXT | AUDIO_EXT)
        elif p.is_file():
            files.append(p)
        else:
            log(f"! Not found, skipping: {raw}")
    if not files:
        err("Nothing to transcribe.")
        return 2

    device, compute_type = pick_device(args.device)
    if args.compute_type:
        compute_type = args.compute_type
    threads = args.threads or (os.cpu_count() or 4)

    log(f"Model      : {args.model}  ({device}, {compute_type}, {threads} threads)")
    log(f"Files      : {len(files)}")
    t0 = time.time()

    os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

    cached = model_is_cached(args.model)
    if cached:
        log("Model found in the local cache - loading offline.")
    else:
        log("Loading model (first run downloads it, then it is cached)...")
        enable_mirror_if_needed()

    def load_model(model_name: str, offline: bool = False):
        return WhisperModel(model_name, device=device,
                            compute_type=compute_type, cpu_threads=threads,
                            local_files_only=offline)

    try:
        model = load_model(args.model, offline=cached)
    except Exception:
        # Cached copy unusable, or download failed: retry with network access.
        err("Offline load failed - retrying over the network...")
        enable_mirror_if_needed()
        try:
            model = load_model(args.model)
        except Exception as exc:
            err(f"Could not load model '{args.model}': {exc}")
            return 1

    log(f"Model ready in {time.time() - t0:.1f}s\n")
    out_root = Path(args.output_dir).expanduser() if args.output_dir else None
    failures = 0

    for idx, src in enumerate(files, 1):
        log(f"[{idx}/{len(files)}] {src.name}")
        started = time.time()
        out_dir = out_root or src.parent
        out_dir.mkdir(parents=True, exist_ok=True)

        try:
            seg_iter, info = model.transcribe(
                str(src),
                language=args.language,
                task=args.task,
                beam_size=args.beam_size,
                vad_filter=args.vad,
                vad_parameters={"min_silence_duration_ms": 500} if args.vad else None,
                initial_prompt=args.initial_prompt,
                word_timestamps=args.word_timestamps,
                condition_on_previous_text=False,
            )

            duration = getattr(info, "duration", 0) or 0
            log(f"      language={info.language} (p={info.language_probability:.2f})"
                f"  duration={human_dur(duration)}")

            segments = []
            for seg in seg_iter:
                item = {
                    "id": len(segments),
                    "start": round(seg.start, 3),
                    "end": round(seg.end, 3),
                    "text": seg.text,
                }
                if args.word_timestamps and seg.words:
                    item["words"] = [
                        {"start": round(w.start, 3), "end": round(w.end, 3),
                         "word": w.word, "probability": round(w.probability, 3)}
                        for w in seg.words
                    ]
                segments.append(item)

                pct = (seg.end / duration * 100) if duration else 0
                line = seg.text.strip()
                if len(line) > 90:
                    line = line[:87] + "..."
                log(f"      {pct:5.1f}%  {line}")

        except Exception as exc:
            failures += 1
            err(f"      FAILED: {exc}\n")
            continue

        if not segments:
            log("      No speech detected.\n")
            continue

        stem = safe_stem(src)
        meta = {
            "source": str(src),
            "model": args.model,
            "language": info.language,
            "language_probability": round(info.language_probability, 4),
            "duration": round(duration, 3),
            "task": args.task,
        }

        written = []
        for fmt in fmts:
            target = out_dir / f"{stem}.{fmt}"
            if target.exists() and not args.overwrite:
                target = out_dir / f"{stem}.{int(time.time())}.{fmt}"
            try:
                if fmt == "txt":
                    write_txt(segments, target, args.timestamps)
                elif fmt == "srt":
                    write_srt(segments, target, args.max_line_width)
                elif fmt == "vtt":
                    write_vtt(segments, target, args.max_line_width)
                elif fmt == "json":
                    write_json(segments, target, meta)
                elif fmt == "md":
                    target.write_text(
                        f"# {src.stem}\n\n"
                        f"- source: `{src.name}`\n- model: `{args.model}`\n"
                        f"- language: `{info.language}`\n"
                        f"- duration: {human_dur(duration)}\n\n"
                        + paragraphs(segments),
                        encoding="utf-8", newline="\n")
                written.append(target.name)
            except OSError as exc:
                err(f"      ! could not write {target.name}: {exc}")

        elapsed = time.time() - started
        speed = (duration / elapsed) if elapsed > 0 and duration else 0
        log(f"      done in {human_dur(elapsed)} ({speed:.1f}x realtime)")
        log(f"      -> {', '.join(written)} in {out_dir}\n")

    msg = "Finished." if not failures else f"Finished with {failures} failure(s)."
    (log if not failures else err)(msg)
    return 0 if not failures else 1


def wrap_text(text: str, width: int = 0) -> str:
    text = text.strip()
    if width <= 0 or len(text) <= width:
        return text
    words = text.split(" ")
    lines, cur = [], ""
    for w in words:
        candidate = f"{cur} {w}".strip()
        if len(candidate) > width and cur:
            lines.append(cur)
            cur = w
        else:
            cur = candidate
    if cur:
        lines.append(cur)
    return "\n".join(lines)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        err("\nInterrupted.")
        raise SystemExit(130)
