"""Online lane with LlamaIndex: question -> retriever -> DeepSeek -> answer.

    uv run python ask.py "How many seats does the Team plan include?"
    uv run python ask.py --show "What does E-311 mean?"

The query engine owns retrieval and synthesis. `response.source_nodes` is the
evidence that backed the answer; print it, because an answer without its sources
is not verifiable.
"""

from __future__ import annotations

import argparse
import os
import sys

from llama_index.core import Settings, VectorStoreIndex
from llama_index.core.prompts import PromptTemplate
from llama_index.llms.deepseek import DeepSeek
from llama_index.vector_stores.lancedb import LanceDBVectorStore

from common import (
    DB_DIR,
    TABLE_NAME,
    MissingKey,
    missing_keys_message,
    require_keys,
)
from qwen import QwenEmbedding

SYSTEM = """You answer questions about NimbusDesk using only the context provided.
If the context does not contain the answer, reply exactly: INSUFFICIENT_CONTEXT.
Do not use prior knowledge and do not invent a source."""

TEXT_QA = PromptTemplate(
    SYSTEM
    + """

Context:
{context_str}

Question: {query_str}
Answer:"""
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("question", nargs="*")
    parser.add_argument("--k", type=int, default=6)
    parser.add_argument("--show", action="store_true")
    args = parser.parse_args()

    require_keys(["DASHSCOPE_API_KEY", "DEEPSEEK_API_KEY"])

    if not DB_DIR.exists():
        print("no index found - run `uv run python ingest.py` first", file=sys.stderr)
        return 1

    Settings.embed_model = QwenEmbedding()
    Settings.llm = DeepSeek(
        model="deepseek-flash",
        api_key=os.environ["DEEPSEEK_API_KEY"],
        api_base=os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        temperature=0,
        is_chat_model=True,
    )

    vector_store = LanceDBVectorStore(uri=str(DB_DIR), table_name=TABLE_NAME)
    index = VectorStoreIndex.from_vector_store(vector_store)
    engine = index.as_query_engine(
        similarity_top_k=args.k,
        text_qa_template=TEXT_QA,
    )

    question = " ".join(args.question).strip()
    if not question:
        question = input("\nquestion> ").strip()
        if not question:
            return 0

    response = engine.query(question)

    print(f"\nquestion: {question}")
    print(f"\nanswer: {response.response}")
    print("\nsources:")
    for number, node in enumerate(response.source_nodes, start=1):
        meta = node.metadata
        print(
            f"  [{number}] {node.score:.4f}  "
            f"{meta.get('source', '?')}  {meta.get('headings', '(no heading)')}"
        )
        if args.show:
            print(f"       {node.text[:300].replace(chr(10), ' ')}...")

    if "INSUFFICIENT_CONTEXT" in str(response.response):
        print("\ninsufficient_context: True")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except MissingKey as exc:
        print(exc, file=sys.stderr)
        raise SystemExit(1) from None
    except KeyboardInterrupt:
        print("\ninterrupted", file=sys.stderr)
        raise SystemExit(130) from None
