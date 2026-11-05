"""Docling -> HybridChunker, shared by ingest and --preview.

The parsing and chunking are intentionally identical to the main lesson 7 lab:
the framework changes, the chunk contract does not.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from common import MAX_CHUNK_TOKENS


def huggingface_hint(exc: Exception) -> SystemExit:
    text = str(exc)
    lower = text.lower()
    if (
        "huggingface.co" in lower
        or "couldn't connect" in lower
        or "connecttimeout" in lower
        or "winerror 10060" in lower
    ):
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
    print(
        "  load    Docling (first run imports PyTorch and downloads models; be patient)",
        flush=True,
    )
    from docling.chunking import HybridChunker
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    from docling.document_converter import DocumentConverter, PdfFormatOption

    print("  load    converter", flush=True)
    try:
        pipeline = PdfPipelineOptions()
        pipeline.do_ocr = ocr
        converter = DocumentConverter(
            format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline)}
        )
        chunker = HybridChunker(max_tokens=MAX_CHUNK_TOKENS, merge_peers=True)
    except Exception as exc:
        raise huggingface_hint(exc) from None
    print(f"  load    chunker ({MAX_CHUNK_TOKENS}-token budget)", flush=True)

    records: list[dict] = []
    for path in paths:
        print(f"  parse   {path.name}", flush=True)
        try:
            result = converter.convert(str(path))
        except Exception as exc:
            raise huggingface_hint(exc) from None
        chunks = list(chunker.chunk(dl_doc=result.document))
        doc_hash = sha256(path)
        for position, chunk in enumerate(chunks):
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
