#!/usr/bin/env python
"""Repo guard: every lab that needs packages is a uv project, and no doc teaches pip.

Run from anywhere:

    python check_uv.py

Checks:
  1. every example whose Python needs packages has a pyproject.toml somewhere in it
  2. and a uv.lock somewhere in it (generated environments, __pycache__, site-packages
     are ignored; a multi-service example may keep both under backend/)
  3. no requirements.txt survives anywhere in the repo
  4. lessons/ and reference/ contain no `pip install -r` or `requirements.txt`

Folders that are pure stdlib (a skill payload script, a demo) are not forced to
carry a project file; adding one is still allowed and then gets validated too.
The example is the unit, not every nested package directory: `backend/app/` is
part of the backend project, not a separate one.

Exit code 0 = consistent, 1 = drift found.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
EXAMPLES = ROOT / "assets" / "examples"

# Generated or vendored trees: never course projects, never worth locking.
SKIP_PARTS = {
    ".venv",
    "venv",
    "__pycache__",
    ".deepeval",
    ".git",
    "node_modules",
    "site-packages",
    "dist-packages",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
}
STDLIB = set(sys.stdlib_module_names)


def is_generated(path: Path) -> bool:
    return any(part in SKIP_PARTS for part in path.parts)


def external_imports(example: Path) -> set[str]:
    """Top-level modules this example imports that are neither stdlib nor local."""
    scripts = [p for p in example.rglob("*.py") if not is_generated(p)]
    local = {p.stem for p in scripts}
    local |= {p.name for p in example.rglob("*") if p.is_dir() and not is_generated(p)}
    found: set[str] = set()

    for script in scripts:
        try:
            tree = ast.parse(script.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name.split(".")[0] for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                if node.level:  # relative import inside the lab
                    continue
                names = [(node.module or "").split(".")[0]]
            else:
                continue
            for name in names:
                if name and name not in STDLIB and name not in local:
                    found.add(name)
    return found


def project_files(example: Path, name: str) -> list[Path]:
    return [p for p in example.rglob(name) if not is_generated(p)]


def is_project(example: Path) -> bool:
    if project_files(example, "pyproject.toml") or project_files(example, "uv.lock"):
        return True
    return bool(external_imports(example))


def main() -> int:
    failures: list[str] = []

    project_dirs = sorted(
        {
            example
            for example in EXAMPLES.iterdir()
            if example.is_dir() and not is_generated(example) and is_project(example)
        }
    )
    for folder in project_dirs:
        rel = folder.relative_to(ROOT)
        pyprojects = project_files(folder, "pyproject.toml")
        if not pyprojects:
            failures.append(f"{rel}: missing pyproject.toml")
        for pyproject in pyprojects:
            if not (pyproject.parent / "uv.lock").is_file():
                where = pyproject.parent.relative_to(ROOT)
                failures.append(f"{where}: pyproject.toml has no sibling uv.lock")

    for stale in sorted(EXAMPLES.rglob("requirements.txt")):
        if is_generated(stale):
            continue
        failures.append(f"{stale.relative_to(ROOT)}: delete (pyproject.toml is the source)")

    pages = sorted((ROOT / "lessons").glob("*.html"))
    pages += sorted((ROOT / "reference").rglob("*.html")) if (ROOT / "reference").is_dir() else []
    for page in pages:
        text = page.read_text(encoding="utf-8")
        for needle in ("pip install -r", "requirements.txt"):
            if needle in text:
                failures.append(f"{page.relative_to(ROOT)}: contains {needle!r}")

    if failures:
        print(f"FAIL — {len(failures)} uv drift issue(s):")
        for item in failures:
            print(" -", item)
        return 1

    print(f"OK — {len(project_dirs)} uv projects, no requirements.txt, no pip instructions in docs")
    return 0


if __name__ == "__main__":
    sys.exit(main())
