"""Part 1, offline: documents -> chunks -> vectors + BM25 -> one LanceDB table.

Stages 1-4 of lesson 6, in one command:

    uv run python ingest.py --preview     # parse + chunk only, no API key needed
    uv run python ingest.py               # embed and index
    uv run python ingest.py --rebuild     # ignore hashes, rebuild everything
    uv run python ingest.py --preview --ocr   # scanned PDFs only; OCR is slow

The first run downloads Docling's layout models and a tokenizer (a few hundred
MB, once) and the first preview takes roughly 30-60 s on a CPU. OCR is off by
default because born-digital PDFs already carry text; turn it on with --ocr
when the pages are scans.

Incremental by design: a document whose sha256 has not changed is skipped, and
a changed document has its old rows deleted before the new ones are added. The
document hash is stored in the table, so there is no manifest to drift.
"""

from __future__ import annotations

import argparse
import hashlib
import statistics
import sys
import time
from pathlib import Path

from common import (
    MAX_CHUNK_TOKENS,
    MissingKey,
    TABLE_NAME,
    docs,
    require_keys,
)
from store import (
    Chunk,
    build_fts,
    connect,
    create_table,
    delete_source,
    existing_hashes,
    open_table,
    table_names,
)


def huggingface_hint(exc: Exception) -> SystemExit:
    text = str(exc)
    if "huggingface.co" in text or "couldn't connect" in text.lower():
        return SystemExit(
            "Docling could not download its layout models.\n"
            "If huggingface.co is unreachable from your network, use a mirror and retry:\n"
            '  $env:HF_ENDPOINT = "https://hf-mirror.com"\n'
            "Models are cached after the first successful run."
        )
    return SystemExit(f"Docling failed: {exc}")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def parse_documents(paths: list[Path], ocr: bool = False) -> list[dict]:
    """Docling -> HybridChunker. Structure first, token budget second."""
    print(
        "  load    Docling (first run imports PyTorch and downloads models; be patient)",
        flush=True,
    )
    from docling.chunking import HybridChunker
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    from docling.document_converter import DocumentConverter, PdfFormatOption

    print("  load    converter", flush=True)
    pipeline = PdfPipelineOptions()
    # Born-digital PDFs already carry text; OCR is the slow path and is off
    # by default. Scanned pages need `--ocr`.
    pipeline.do_ocr = ocr
    converter = DocumentConverter(
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline)}
    )
    try:
        chunker = HybridChunker(max_tokens=MAX_CHUNK_TOKENS, merge_peers=True)
    except OSError as exc:
        raise huggingface_hint(exc) from None
    print("  load    chunker (512-token budget)", flush=True)
    records: list[dict] = []

    for path in paths:
        print(f"  parse   {path.name}", flush=True)
        try:
            result = converter.convert(str(path))
        except OSError as exc:
            raise huggingface_hint(exc) from None
        chunks = list(chunker.chunk(dl_doc=result.document))
        doc_hash = sha256(path)
        for position, chunk in enumerate(chunks):
            # contextualize() prepends the heading path, so a chunk about
            # refunds still knows it is under "Refunds and billing corrections".
            text = chunker.contextualize(chunk)
            headings = " > ".join(chunk.meta.headings or [])
            pages = sorted(
                {
                    prov.page_no
                    for item in (chunk.meta.doc_items or [])
                    for prov in (item.prov or [])
                }
            )
            records.append(
                {
                    "id": hashlib.sha1(
                        f"{path.name}|{position}|{text}".encode("utf-8")
                    ).hexdigest()[:12],
                    "text": text,
                    "source": path.name,
                    "headings": headings or "(no heading)",
                    "pages": ",".join(str(page) for page in pages),
                    "doc_hash": doc_hash,
                }
            )
        print(f"          {len(chunks)} chunks", flush=True)

    return records


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
    parser.add_argument(
        "--preview",
        action="store_true",
        help="parse and chunk only; print what would be embedded",
    )
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help="ignore document hashes and re-index everything",
    )
    parser.add_argument(
        "--ocr",
        action="store_true",
        help="run OCR (needed for scanned PDFs; slower, off by default)",
    )
    args = parser.parse_args()

    paths = docs()
    print(f"corpus: {len(paths)} documents in {paths[0].parent}")

    if args.preview:
        started = time.perf_counter()
        records = parse_documents(paths, ocr=args.ocr)
        preview(records, len(paths), time.perf_counter() - started)
        return 0

    db = connect()
    fresh = args.rebuild or TABLE_NAME not in table_names(db)
    table = None
    if fresh:
        todo = paths
    else:
        table = open_table(db)
        known = existing_hashes(table)
        current = {path.name: sha256(path) for path in paths}
        todo = [path for path in paths if known.get(path.name) != current[path.name]]

    if not todo:
        if table is None:
            print("no documents found in docs/", file=sys.stderr)
            return 1
        build_fts(table)
        print(f"nothing changed; {table.count_rows()} chunks already indexed")
        return 0

    require_keys(["DASHSCOPE_API_KEY"])
    if fresh:
        table = create_table(db, [])

    started = time.perf_counter()
    records = parse_documents(todo, ocr=args.ocr)
    if not records:
        print("no chunks produced - is the corpus empty?", file=sys.stderr)
        return 1

    print(f"\n  embed   {len(records)} chunks with Qwen text-embedding-v4")
    from qwen import embed_documents

    vectors = embed_documents([record["text"] for record in records])
    rows = [Chunk(**record, vector=vector) for record, vector in zip(records, vectors)]

    if not fresh:
        for path in todo:
            delete_source(table, path.name)
    table.add(rows)
    build_fts(table)

    print(
        f"\nindexed {len(rows)} chunks from {len(todo)} documents "
        f"({len(paths) - len(todo)} unchanged) in {time.perf_counter() - started:.1f}s; "
        f"table now holds {table.count_rows()}"
    )
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
