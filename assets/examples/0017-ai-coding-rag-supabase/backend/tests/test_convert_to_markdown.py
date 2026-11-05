from __future__ import annotations

import json
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from data.convert_to_markdown import _load_filings, convert_filings


def _write_html_manifest(input_dir: Path) -> Path:
    filing_path = input_dir / "2025" / "googl.htm"
    filing_path.parent.mkdir(parents=True)
    filing_path.write_text("<html>filing</html>", encoding="utf-8")
    manifest_path = input_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "source": "SEC EDGAR",
                "filings": [
                    {
                        "ticker": "GOOGL",
                        "form": "10-K",
                        "filing_date": "2026-02-05",
                        "report_date": "2025-12-31",
                        "accession_number": "accession-GOOGL",
                        "source_url": "https://example.test/filing",
                        "local_path": "2025/googl.htm",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return manifest_path


def test_load_filings_validates_and_preserves_manifest_paths(tmp_path: Path) -> None:
    manifest_path = _write_html_manifest(tmp_path)

    manifest, filings = _load_filings(tmp_path)

    assert manifest["source"] == "SEC EDGAR"
    assert len(filings) == 1
    assert filings[0][0] == (tmp_path / "2025" / "googl.htm").resolve()
    assert filings[0][1]["ticker"] == "GOOGL"
    assert manifest_path.is_file()


def test_convert_filings_preserves_folder_structure_and_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    input_dir = tmp_path / "downloads"
    _write_html_manifest(input_dir)
    output_dir = tmp_path / "markdown"

    class FakeDocumentConverter:
        def convert(self, source: Path) -> SimpleNamespace:
            assert source.suffix == ".htm"
            return SimpleNamespace(
                document=SimpleNamespace(export_to_markdown=lambda: "# GOOGL filing")
            )

    fake_module = ModuleType("docling.document_converter")
    fake_module.DocumentConverter = FakeDocumentConverter
    monkeypatch.setitem(sys.modules, "docling.document_converter", fake_module)

    converted = convert_filings(input_dir, output_dir)

    output_path = output_dir / "2025" / "googl.md"
    output_manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
    record = output_manifest["filings"][0]
    assert converted == 1
    assert output_path.read_text(encoding="utf-8") == "# GOOGL filing\n"
    assert record["ticker"] == "GOOGL"
    assert record["local_path"] == "2025/googl.md"
    assert record["source_local_path"] == "2025/googl.htm"
