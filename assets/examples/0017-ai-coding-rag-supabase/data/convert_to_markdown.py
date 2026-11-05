# /// script
# requires-python = ">=3.12"
# ///
from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

HTML_SUFFIXES = {".htm", ".html"}
DATA_DIR = Path(__file__).resolve().parent
DEFAULT_INPUT_DIR = DATA_DIR / "downloads"
DEFAULT_OUTPUT_DIR = DATA_DIR / "markdown"


def _relative_path(value: str) -> PurePosixPath:
    path = PurePosixPath(value.replace("\\", "/"))
    if path.is_absolute() or not path.parts or ".." in path.parts:
        raise ValueError(f"Manifest path must be a relative path inside downloads: {value!r}")
    return path


def _load_filings(input_dir: Path) -> tuple[dict[str, Any], list[tuple[Path, dict[str, Any]]]]:
    manifest_path = input_dir / "manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"Downloads manifest not found: {manifest_path}")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    records = manifest.get("filings")
    if not isinstance(records, list):
        raise ValueError(f"Expected a 'filings' list in {manifest_path}")

    root = input_dir.resolve()
    by_path: dict[str, dict[str, Any]] = {}
    for record in records:
        if not isinstance(record, dict) or not isinstance(record.get("local_path"), str):
            raise ValueError(f"Invalid filing entry in {manifest_path}: {record!r}")
        relative = _relative_path(record["local_path"])
        key = relative.as_posix().casefold()
        if key in by_path:
            raise ValueError(f"Duplicate local_path in {manifest_path}: {record['local_path']}")
        if Path(relative.name).suffix.casefold() not in HTML_SUFFIXES:
            raise ValueError(f"Manifest entry is not an HTML file: {record['local_path']}")
        source = root.joinpath(*relative.parts).resolve()
        if not source.is_relative_to(root):
            raise ValueError(
                f"Manifest path escapes the downloads directory: {record['local_path']}"
            )
        if not source.is_file():
            raise FileNotFoundError(f"Manifest filing not found: {source}")
        by_path[key] = record

    html_files = sorted(
        path
        for path in root.rglob("*")
        if path.is_file() and path.suffix.casefold() in HTML_SUFFIXES
    )
    actual_paths = {path.relative_to(root).as_posix().casefold() for path in html_files}
    if actual_paths != set(by_path):
        missing_manifest = sorted(actual_paths - set(by_path))
        missing_files = sorted(set(by_path) - actual_paths)
        details = []
        if missing_manifest:
            details.append(f"HTML files missing from manifest: {', '.join(missing_manifest)}")
        if missing_files:
            details.append(f"Manifest files missing from disk: {', '.join(missing_files)}")
        raise ValueError("; ".join(details))

    return manifest, [
        (path, by_path[path.relative_to(root).as_posix().casefold()]) for path in html_files
    ]


def convert_filings(input_dir: Path, output_dir: Path) -> int:
    from docling.document_converter import DocumentConverter

    source_manifest, filings = _load_filings(input_dir)
    if not filings:
        raise ValueError(f"No HTML filings found under {input_dir}")

    input_root = input_dir.resolve()
    output_root = output_dir.resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    converter = DocumentConverter()
    converted_records: list[dict[str, Any]] = []

    for source, record in filings:
        relative_source = source.relative_to(input_root)
        relative_markdown = relative_source.with_suffix(".md")
        destination = output_root / relative_markdown
        destination.parent.mkdir(parents=True, exist_ok=True)

        print(f"Converting {relative_source}")
        result = converter.convert(source)
        markdown = result.document.export_to_markdown()

        if not markdown.strip():
            raise ValueError(f"Docling produced empty Markdown for {source}")
        destination.write_text(markdown.rstrip() + "\n", encoding="utf-8")

        converted_records.append(
            {
                **record,
                "source_local_path": record["local_path"],
                "local_path": relative_markdown.as_posix(),
            }
        )

    output_manifest = {
        key: value
        for key, value in source_manifest.items()
        if key not in {"generated_at_utc", "downloaded_count", "filings"}
    }
    output_manifest.update(
        {
            "generated_at_utc": datetime.now(UTC).isoformat(),
            "converted_count": len(converted_records),
            "source_manifest": "../downloads/manifest.json",
            "filings": converted_records,
        }
    )
    (output_root / "manifest.json").write_text(
        json.dumps(output_manifest, indent=2) + "\n",
        encoding="utf-8",
    )
    return len(converted_records)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert downloaded SEC HTML filings to Markdown with Docling."
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=DEFAULT_INPUT_DIR,
        help=f"Source filings directory (default: {DEFAULT_INPUT_DIR})",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help=f"Markdown output directory (default: {DEFAULT_OUTPUT_DIR})",
    )
    args = parser.parse_args()

    converted = convert_filings(args.input_dir, args.output_dir)
    print(f"Converted {converted} filing(s) to {args.output_dir.resolve()}")
    print(f"Manifest: {(args.output_dir / 'manifest.json').resolve()}")


if __name__ == "__main__":
    main()
