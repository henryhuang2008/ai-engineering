#!/usr/bin/env python3
"""Time each model on one file, so you can pick the right size.

    python benchmark.py video.mp4 --models base small medium
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

from transcribe import enable_mirror_if_needed, model_is_cached, pick_device


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("input")
    ap.add_argument("--models", nargs="+",
                    default=["base", "small", "medium"])
    ap.add_argument("--language", default=None)
    ap.add_argument("--threads", type=int, default=0)
    args = ap.parse_args()

    if not Path(args.input).is_file():
        print(f"No such file: {args.input}")
        return 2

    os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
    device, compute_type = pick_device("auto")
    threads = args.threads or (os.cpu_count() or 4)

    from faster_whisper import WhisperModel

    print(f"{args.input}  ({device}, {compute_type}, {threads} threads)\n")
    print(f"{'model':<14}{'load':>8}{'run':>9}{'speed':>12}{'1h video':>12}")
    print("-" * 55)

    for name in args.models:
        cached = model_is_cached(name)
        if not cached:
            enable_mirror_if_needed()
        try:
            t0 = time.time()
            model = WhisperModel(name, device=device,
                                 compute_type=compute_type, cpu_threads=threads,
                                 local_files_only=cached)
            load = time.time() - t0

            t1 = time.time()
            segments, info = model.transcribe(
                args.input, language=args.language, beam_size=5,
                vad_filter=True, condition_on_previous_text=False)
            text = " ".join(s.text.strip() for s in segments)
            run = time.time() - t1

            duration = info.duration or 0
            speed = duration / run if run else 0
            eta = duration / speed if speed else 0
            print(f"{name:<14}{load:>7.1f}s{run:>8.1f}s{speed:>10.1f}x"
                  f"{eta:>10.0f} min")
            del model
        except Exception as exc:
            print(f"{name:<14}FAILED: {exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
