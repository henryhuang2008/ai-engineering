"""Ask the local LlamaIndex agent a question over the Nimbus Pizza reviews.

Run:

    uv run python ask.py "Is the gluten-free pizza good?"
    uv run python ask.py                 # interactive

No API key and no network: the chat model, embeddings and vector store all run
on this machine.
"""

from __future__ import annotations

import sys

import chromadb
from llama_index.core import VectorStoreIndex
from llama_index.vector_stores.chroma import ChromaVectorStore

from common import (
    CHAT_MODEL,
    COLLECTION,
    DB_DIR,
    configure,
    require_models,
)


def build_engine():
    client = chromadb.PersistentClient(path=str(DB_DIR))
    collection = client.get_or_create_collection(COLLECTION)
    if collection.count() == 0:
        raise RuntimeError("the vector store is empty; run `uv run python ingest.py` first")

    vector_store = ChromaVectorStore(chroma_collection=collection)
    index = VectorStoreIndex.from_vector_store(vector_store)
    return index.as_query_engine(similarity_top_k=4)


def answer(engine, question: str) -> None:
    print(f"\nquerying 4 local chunks with {CHAT_MODEL} ...\n")
    response = engine.query(question)
    print(response.response)
    print("\nsources:")
    for node in response.source_nodes:
        meta = node.metadata
        print(
            f"  [{meta.get('title', 'untitled')}] "
            f"rating={meta.get('rating', '?')} {meta.get('date', '?')}"
        )


def main() -> int:
    try:
        require_models()
        configure()
        engine = build_engine()
    except RuntimeError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    question = " ".join(sys.argv[1:]).strip()
    if question:
        answer(engine, question)
        return 0

    print("Ask about the Nimbus Pizza reviews. Type 'q' to quit.")
    while True:
        try:
            question = input("\nquestion: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if question.lower() in {"q", "quit", "exit"}:
            return 0
        if question:
            answer(engine, question)


if __name__ == "__main__":
    raise SystemExit(main())
