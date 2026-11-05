"""Offline lane with LlamaIndex: Docling chunks -> Qwen vectors -> LanceDB.

    uv run python ingest.py --preview     # parse + chunk only, no key needed
    uv run python ingest.py               # embed and index
    uv run python ingest.py --rebuild     # delete the index and rebuild

The corpus is the three documents from the main lesson 7 lab, so both examples
answer the same questions over the same text.
"""

from __future__ import annotations

import argparse
import shutil
import statistics
import sys
import time

from llama_index.core import Settings, StorageContext, VectorStoreIndex
from llama_index.core.schema import TextNode
from llama_index.vector_stores.lancedb import LanceDBVectorStore

from common import (
    DB_DIR,
    TABLE_NAME,
    MissingKey,
    docs,
    missing_keys_message,
    require_keys,
)
from parse import parse_documents
from qwen import QwenEmbedding


def preview(records: list[dict], document_count: int, elapsed: float) -> None:
    lengths = [len(record["text"]) for record in records]
    print()
    print(f"{len(records)} chunks from {document_count} documents in {elapsed:.1f}s")
    if not lengths:
        return
    print(
        "characters per chunk: "
        f"min {min(lengths)}  median {int(statistics.median(lengths))}  max {max(lengths)}"
    )
    print("\nfirst three chunks as the embedder will see them:\n")
    for record in records[:3]:
        head = record["text"].replace("\n", " ")
        print(f"  [{record['id']}] {record['source']}  ({record['headings']})")
        print(f"    {head[:220]}{'...' if len(head) > 220 else ''}")
        print()


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--preview", action="store_true")
    parser.add_argument("--rebuild", action="store_true")
    parser.add_argument("--ocr", action="store_true")
    args = parser.parse_args()

    paths = docs()
    print(f"corpus: {len(paths)} documents in {paths[0].parent}")

    if args.preview:
        started = time.perf_counter()
        records = parse_documents(paths, ocr=args.ocr)
        preview(records, len(paths), time.perf_counter() - started)
        return 0

    if DB_DIR.exists() and any(DB_DIR.iterdir()) and not args.rebuild:
        print(f"index already exists in {DB_DIR}; use --rebuild to replace it.")
        return 0

    require_keys(["DASHSCOPE_API_KEY"])

    if args.rebuild:
        shutil.rmtree(DB_DIR, ignore_errors=True)

    Settings.embed_model = QwenEmbedding()

    started = time.perf_counter()
    records = parse_documents(paths, ocr=args.ocr)
    if not records:
        print("no chunks produced - is the corpus empty?", file=sys.stderr)
        return 1

    nodes = [
        TextNode(
            id_=record["id"],
            text=record["text"],
            metadata={
                "source": record["source"],
                "headings": record["headings"],
                "pages": record["pages"],
                "doc_hash": record["doc_hash"],
            },
        )
        for record in records
    ]

    vector_store = LanceDBVectorStore(
        uri=str(DB_DIR),
        table_name=TABLE_NAME,
        mode="overwrite",
    )
    storage = StorageContext.from_defaults(vector_store=vector_store)
    VectorStoreIndex(nodes, storage_context=storage, show_progress=True)

    print(
        f"\nindexed {len(nodes)} chunks from {len(paths)} documents "
        f"in {time.perf_counter() - started:.1f}s"
    )
    print(f"stored in {DB_DIR}")
    print("LlamaIndex embedded and persisted the nodes.")
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
