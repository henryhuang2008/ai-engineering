"""Part 2, online: question -> two representations -> hybrid search -> answer.

Stages 5-8 of lesson 6:

  5 prepare  embed the question with text_type="query"; BM25 uses the same text
  6 retrieve one hybrid query: dense + BM25, fused by reciprocal rank fusion
  7 rerank   optional cross-encoder (--rerank); off by default so you can compare
  8 generate ChatDeepSeek, forced into a pydantic Answer, citations validated

Run one question:

    uv run python ask.py "How many seats does the Team plan include?"

Or leave the question off for a prompt loop. `--show` prints the evidence that
was retrieved, which is the first thing to inspect when an answer is wrong.
"""

from __future__ import annotations

import argparse
import sys

from pydantic import BaseModel, Field

from common import TABLE_NAME, MissingKey, require_keys
from qwen import embed_query
from store import connect, hybrid_search, open_table, table_names

SYSTEM = """You answer questions about NimbusDesk using only the evidence provided.

Rules:
- Every factual claim must come from the evidence, not from prior knowledge.
- Cite the evidence numbers you used in square brackets, for example [1] or [2, 4].
- If the evidence does not contain the answer, say so plainly and set
  insufficient_context to true. Do not guess and do not invent a source."""


class Answer(BaseModel):
    answer: str = Field(description="The answer, grounded only in the evidence.")
    citations: list[int] = Field(
        default_factory=list,
        description="Evidence numbers used, for example [1, 3].",
    )
    insufficient_context: bool = Field(
        description="True when the evidence does not answer the question.",
    )


def format_evidence(rows: list[dict]) -> str:
    blocks = []
    for number, row in enumerate(rows, start=1):
        heading = row.get("headings") or "(no heading)"
        blocks.append(f"[{number}] {row['source']} - {heading}\n{row['text']}")
    return "\n\n".join(blocks)


def answer_question(question: str, k: int, rerank: bool, show: bool) -> None:
    db = connect()
    if TABLE_NAME not in table_names(db):
        raise SystemExit("no index found - run `uv run python ingest.py` first")
    table = open_table(db)

    vector = embed_query(question)
    rows = hybrid_search(table, question, vector, k=k, rerank=rerank)
    if not rows:
        print("no chunks retrieved - is the index empty?")
        return

    print(f"\nquestion: {question}")
    print(f"retrieved {len(rows)} chunks (hybrid, {'cross-encoder' if rerank else 'RRF'})")
    for number, row in enumerate(rows, start=1):
        score = row.get("_relevance_score")
        score_text = f"{score:.4f}" if isinstance(score, float) else "-"
        print(f"  [{number}] {score_text}  {row['source']}  {row['headings']}")

    if show:
        print("\n--- evidence ---")
        print(format_evidence(rows))
        print("--- end evidence ---")

    from langchain_core.messages import HumanMessage, SystemMessage
    from langchain_deepseek import ChatDeepSeek

    model = ChatDeepSeek(
        model="deepseek-flash",
        temperature=0,
        extra_body={"thinking": {"type": "disabled"}},
    )
    structured = model.with_structured_output(Answer, method="function_calling")
    message = (
        f"Question: {question}\n\n"
        f"Evidence:\n\n{format_evidence(rows)}\n\n"
        "Answer from the evidence above."
    )
    result = structured.invoke(
        [SystemMessage(content=SYSTEM), HumanMessage(content=message)]
    )

    valid = [number for number in result.citations if 1 <= number <= len(rows)]
    if len(valid) != len(result.citations):
        bad = sorted({n for n in result.citations if not 1 <= n <= len(rows)})
        print(f"\nwarning: dropped citations outside the evidence set: {bad}")
    if not valid and not result.insufficient_context:
        print("\nwarning: answer has no citations and does not flag insufficient context")

    print(f"\nanswer: {result.answer}")
    print(f"insufficient_context: {result.insufficient_context}")
    if valid:
        print("citations:")
        for number in dict.fromkeys(valid):
            row = rows[number - 1]
            print(f"  [{number}] {row['source']}  chunk {row['id']}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("question", nargs="*", help="one question; omit for a prompt loop")
    parser.add_argument("--k", type=int, default=6, help="chunks passed to the model (default 6)")
    parser.add_argument(
        "--rerank",
        action="store_true",
        help="add a cross-encoder reranker (downloads a model on first use)",
    )
    parser.add_argument("--show", action="store_true", help="print the retrieved evidence")
    args = parser.parse_args()

    require_keys(["DASHSCOPE_API_KEY", "DEEPSEEK_API_KEY"])

    if args.question:
        answer_question(" ".join(args.question), args.k, args.rerank, args.show)
        return 0

    while True:
        try:
            question = input("\nquestion> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if not question or question.lower() in {"exit", "quit"}:
            return 0
        answer_question(question, args.k, args.rerank, args.show)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except MissingKey as exc:
        print(exc, file=sys.stderr)
        raise SystemExit(1) from None
    except KeyboardInterrupt:
        print("\ninterrupted", file=sys.stderr)
        raise SystemExit(130) from None
