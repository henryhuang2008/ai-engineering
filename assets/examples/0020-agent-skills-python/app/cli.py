from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from app.config import get_settings
from app.lint import BLOCK, blocking, lint_library
from app.runtime import RuntimeUnavailable, ask, probe
from app.skills import SkillError, catalog_lines, discover, estimate_tokens


def _lint(json_output: bool) -> int:
    settings = get_settings()
    try:
        findings = lint_library(settings.library)
    except SkillError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    if json_output:
        print(
            json.dumps(
                [
                    {
                        "severity": finding.severity,
                        "rule": finding.rule,
                        "path": str(finding.path),
                        "line": finding.line,
                        "message": finding.message,
                    }
                    for finding in findings
                ],
                indent=2,
            )
        )
    else:
        for finding in findings:
            print(finding.format(settings.library))
        counts = {
            level: len([f for f in findings if f.severity == level]) for level in ("BLOCK", "WARN")
        }
        print(f"\n{counts['BLOCK']} blocking, {counts['WARN']} warnings")

    return 1 if blocking(findings) else 0


def _catalog(json_output: bool) -> int:
    settings = get_settings()
    try:
        skills = discover(settings.library)
    except SkillError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    lines = catalog_lines(skills)
    catalog_tokens = estimate_tokens("\n".join(lines))

    if json_output:
        print(
            json.dumps(
                {
                    "library": str(settings.library),
                    "catalog_tokens": catalog_tokens,
                    "skills": [
                        {
                            "name": skill.name,
                            "description": skill.description,
                            "body_lines": skill.body_lines,
                            "body_tokens": estimate_tokens(skill.body),
                            "files": skill.relative_files(),
                        }
                        for skill in skills
                    ],
                },
                indent=2,
            )
        )
        return 0

    print(f"library: {settings.library}")
    print(f"always-on catalog: ~{catalog_tokens} tokens, {len(skills)} skills\n")
    for skill in skills:
        print(f"{skill.name}  ({skill.body_lines} body lines, ~{estimate_tokens(skill.body)} tokens on load)")
        print(f"  {skill.description}")
        files = skill.relative_files()
        if files:
            print(f"  files: {', '.join(files)}")
        print()
    return 0


def _verify() -> int:
    settings = get_settings()
    try:
        captured = probe(settings)
    except RuntimeUnavailable as error:
        print(f"runtime unavailable: {error}", file=sys.stderr)
        return 2

    instructions = captured.get("instructions", "")
    print("tools:", ", ".join(captured.get("tools", [])))
    print("require_loaded:", settings.require_loaded)
    marker = '<context id="capability:deferred_capabilities">'
    if marker in instructions:
        block = instructions.split(marker, 1)[1].split("</context>", 1)[0].strip()
        print("\ncatalog the model sees:")
        print(block)
    else:
        print("\nno deferred-capability catalog in instructions")
    return 0


def _ask(question: str) -> int:
    settings = get_settings()
    try:
        print(ask(settings, question))
    except (ValueError, RuntimeUnavailable) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


def _resolve(available: list[str], requested: str) -> str | None:
    if requested in available:
        return requested
    matches = [name for name in available if name.rsplit("/", 1)[-1] == requested]
    return matches[0] if len(matches) == 1 else None


def _run_script(skill_name: str, script_name: str, pairs: list[str]) -> int:
    from app.runtime import build_capability

    settings = get_settings()
    try:
        capability = build_capability(settings)
    except RuntimeUnavailable as error:
        print(f"runtime unavailable: {error}", file=sys.stderr)
        return 2

    package = capability.packages.get(skill_name)
    if package is None:
        print(f"error: no skill named {skill_name!r}; have {sorted(capability.packages)}", file=sys.stderr)
        return 1

    scripts = {script.name: script for script in package.scripts}
    resolved = _resolve(list(scripts), script_name)
    if resolved is None:
        print(f"error: no script {script_name!r}; have {sorted(scripts)}", file=sys.stderr)
        return 1

    args: dict[str, str] = {}
    for pair in pairs:
        if "=" not in pair:
            print(f"error: --set expects key=value, got {pair!r}", file=sys.stderr)
            return 1
        key, value = pair.split("=", 1)
        args[key] = value

    script = scripts[resolved]
    output = asyncio.run(script.executor.run(script, args))  # type: ignore[arg-type]
    print(output)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="0020-agent-skills-python",
        description="Author, lint and run Agent Skills.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    lint = sub.add_parser("lint", help="check the skill library")
    lint.add_argument("--json", action="store_true")

    catalog = sub.add_parser("catalog", help="show what the model sees before loading")
    catalog.add_argument("--json", action="store_true")

    sub.add_parser("verify", help="build the runtime and print its tools and catalog")

    ask_parser = sub.add_parser("ask", help="run the live agent")
    ask_parser.add_argument("question", nargs="+")

    script = sub.add_parser("run-script", help="run a bundled skill script without a model")
    script.add_argument("skill")
    script.add_argument("script")
    script.add_argument("--set", action="append", default=[], metavar="KEY=VALUE")

    args = parser.parse_args(argv)

    if args.command == "lint":
        return _lint(args.json)
    if args.command == "catalog":
        return _catalog(args.json)
    if args.command == "verify":
        return _verify()
    if args.command == "ask":
        return _ask(" ".join(args.question))
    return _run_script(args.skill, args.script, args.set)


if __name__ == "__main__":
    raise SystemExit(main())
