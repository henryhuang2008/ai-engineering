import sys

from app.cli import main

if __name__ == "__main__":
    # Windows consoles default to a legacy code page; model replies can contain
    # characters (emoji, CJK) that would raise UnicodeEncodeError on print.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    raise SystemExit(main())
