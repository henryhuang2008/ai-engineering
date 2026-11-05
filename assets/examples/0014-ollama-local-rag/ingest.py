"""Build the local index: CSV -> LlamaIndex Documents -> Ollama -> Chroma.

Run after the models are pulled:

    uv run python ingest.py
"""

from __future__ import annotations

import sys

import chromadb
import pandas as pd
from llama_index.core import Document, StorageContext, VectorStoreIndex
from llama_index.vector_stores.chroma import ChromaVectorStore

from common import (
    COLLECTION,
    CSV_PATH,
    DB_DIR,
    EMBED_MODEL,
    configure,
    require_models,
)


def main() -> int:
    try:
        require_models(need_chat=False)
        configure(need_llm=False)
    except RuntimeError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    frame = pd.read_csv(CSV_PATH)
    documents = [
        Document(
            text=f"{row['Title']}. {row['Review']}",
            metadata={
                "title": row["Title"],
                "rating": int(row["Rating"]),
                "date": str(row["Date"]),
            },
        )
        for _, row in frame.iterrows()
    ]

    client = chromadb.PersistentClient(path=str(DB_DIR))
    collection = client.get_or_create_collection(COLLECTION)
    existing = collection.count()
    if existing:
        print(f"collection already has {existing} documents; nothing to do.")
        print(f"delete {DB_DIR} and rerun to rebuild.")
        return 0

    vector_store = ChromaVectorStore(chroma_collection=collection)
    storage = StorageContext.from_defaults(vector_store=vector_store)
    VectorStoreIndex.from_documents(
        documents,
        storage_context=storage,
        show_progress=True,
    )

    print(f"read {len(frame)} rows from {CSV_PATH.name}")
    print(f"embedded {len(documents)} documents with {EMBED_MODEL}")
    print(f"stored in {DB_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
