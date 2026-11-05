"""0005-first-evals - dataset, scorer, runner, gate. The model is DeepSeek.

The harness is deliberately plain Python: a JSONL file, a loop, a counter. The
model call reuses the LangChain handle from lesson 2, so the only thing this
lesson adds is the part that tells you whether a change helped.

Four parts, one comparison:

  1. dataset   dataset.jsonl - one {"ticket", "expected"} case per line
  2. scorer    `got == expected` (classification has a right answer)
  3. runner    run() - case in, label out, accuracy and every failure printed
  4. gate      `--threshold` - exit 1 when accuracy drops, so CI can stop a merge

Run it twice: once as-is (write the number down - that is your baseline), once
with CLASSIFIER_PROMPT sabotaged. The score moves; that is the whole point.

This lab talks to the live DeepSeek API. Set DEEPSEEK_API_KEY first:

  PowerShell (this session):  $env:DEEPSEEK_API_KEY = "sk-..."
  PowerShell (persist):       setx DEEPSEEK_API_KEY "sk-..."   # reopen the terminal

Get a key at https://platform.deepseek.com/api_keys. No key -> exit 1 with these
instructions, never a guess.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Literal

from pydantic import BaseModel, Field

HERE = Path(__file__).resolve().parent
DATASET = HERE / "dataset.jsonl"
DEFAULT_THRESHOLD = 0.9
DEFAULT_PROMPT = "Classify the support ticket into billing, bug, or question."


class SupportTicket(BaseModel):
    """The lesson-2 schema, now also the eval's expected shape."""

    category: Literal["billing", "bug", "question"] = Field(
        description="billing, bug, or question"
    )
    urgency: int = Field(ge=1, le=5, description="1-5, 5 being most urgent")
    summary: str


@dataclass(frozen=True)
class Case:
    ticket: str
    expected: str


@dataclass
class Result:
    total: int
    passed: int
    failures: list[tuple[Case, str]] = field(default_factory=list)

    @property
    def accuracy(self) -> float:
        return self.passed / self.total if self.total else 0.0


# --- model wiring -----------------------------------------------------------


def missing_key_message() -> str:
    return (
        "DEEPSEEK_API_KEY is not set.\n"
        '  PowerShell (this session):  $env:DEEPSEEK_API_KEY = "sk-..."\n'
        '  PowerShell (persist):       setx DEEPSEEK_API_KEY "sk-..."   # reopen terminal\n'
        "  Get a key:                  https://platform.deepseek.com/api_keys"
    )


def build_model() -> Any:
    """Return a live ChatDeepSeek handle, or explain exactly what is missing."""
    if not os.getenv("DEEPSEEK_API_KEY"):
        raise RuntimeError(missing_key_message())

    from langchain_deepseek import ChatDeepSeek

    return ChatDeepSeek(
        model=os.getenv("DEEPSEEK_MODEL", "deepseek-flash"),
        api_key=os.getenv("DEEPSEEK_API_KEY"),
        api_base=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        temperature=0,  # comparability: the run must not be the noisy part
        max_retries=2,
        timeout=60,
        extra_body={"thinking": {"type": "disabled"}},
    )


def build_classifier(model: Any) -> Any:
    """One structured-output wrapper for every case, not one per case."""
    return model.with_structured_output(SupportTicket, method="function_calling")


def prompt() -> str:
    """The prompt under test. An env var makes sabotage a one-line experiment."""
    return os.getenv("CLASSIFIER_PROMPT") or DEFAULT_PROMPT


def classify(classifier: Any, ticket: str) -> str:
    from langchain_core.messages import HumanMessage, SystemMessage

    result = classifier.invoke(
        [SystemMessage(content=prompt()), HumanMessage(content=ticket)]
    )
    return result.category


# --- dataset + runner -------------------------------------------------------


def load_cases(path: Path = DATASET) -> list[Case]:
    # utf-8-sig: a dataset saved by Windows PowerShell still loads (BOM tolerated).
    text = path.read_text(encoding="utf-8-sig")
    cases: list[Case] = []
    for number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
            cases.append(Case(ticket=row["ticket"], expected=row["expected"]))
        except (json.JSONDecodeError, KeyError) as error:
            raise ValueError(f"{path.name}:{number}: bad case ({error})") from error
    if not cases:
        raise ValueError(f"{path.name}: no cases")
    return cases


def run(cases: list[Case], classify_one: Callable[[str], str]) -> Result:
    """The entire runner: call once per case, count matches, keep the misses."""
    failures: list[tuple[Case, str]] = []
    for case in cases:
        try:
            got = classify_one(case.ticket)
        except Exception as error:  # noqa: BLE001 - a failed call is a failed case
            got = f"ERROR: {type(error).__name__}: {error}"
        if got != case.expected:
            failures.append((case, got))
    return Result(total=len(cases), passed=len(cases) - len(failures), failures=failures)


def gate(accuracy: float, threshold: float) -> bool:
    """CI's only question: did the number fall below the line?"""
    return accuracy >= threshold


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Score the ticket classifier on a fixed set.")
    parser.add_argument(
        "--threshold",
        type=float,
        default=DEFAULT_THRESHOLD,
        help=f"fail below this accuracy (default {DEFAULT_THRESHOLD:.0%})",
    )
    parser.add_argument("--dataset", type=Path, default=DATASET)
    args = parser.parse_args(argv)

    try:
        model = build_model()
    except RuntimeError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    cases = load_cases(args.dataset)
    classifier = build_classifier(model)
    result = run(cases, lambda ticket: classify(classifier, ticket))

    print(f"prompt: {prompt()[:70]}")
    print(f"accuracy: {result.passed}/{result.total} = {result.accuracy:.0%}")
    for case, got in result.failures:
        print(f"  FAIL expected={case.expected} got={got}  ticket={case.ticket[:60]}")

    ok = gate(result.accuracy, args.threshold)
    verdict = "pass" if ok else "FAIL"
    print(f"gate: {result.accuracy:.0%} vs threshold {args.threshold:.0%} -> {verdict}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
