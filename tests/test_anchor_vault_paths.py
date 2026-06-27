"""Smoke tests: Trinity archives land under ANCHOR_DATA_ROOT vault paths."""

from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest

from drift.trinity.caseflow import run_case_from_scan, TrinityCaseLedger


def _write_slither_payload(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "results": {
                    "detectors": [
                        {
                            "check": "reentrancy",
                            "impact": "High",
                            "confidence": "High",
                            "description": "vault path smoke test",
                            "elements": [
                                {
                                    "source_mapping": {
                                        "filename_relative": "contracts/V.sol",
                                        "lines": [1],
                                    }
                                }
                            ],
                        }
                    ]
                }
            }
        ),
        encoding="utf-8",
    )


@pytest.fixture()
def anchor_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    for sub in (
        "Anchor/archives",
        "Anchor/history",
        "Anchor/benchmarks",
        "AnchorVault/claims",
    ):
        (tmp_path / sub).mkdir(parents=True)
    monkeypatch.setenv("ANCHOR_DATA_ROOT", str(tmp_path))
    import drift.trinity.release as release

    importlib.reload(release)
    return tmp_path


def test_resolve_trinity_paths_under_anchor(anchor_root: Path) -> None:
    from drift.trinity import release

    assert release.TRINITY_ARCHIVE_DIR == anchor_root / "Anchor" / "archives"
    assert release.TRINITY_ARCHIVE_LEDGER_PATH == (
        anchor_root / "Anchor" / "history" / "trinity_archive_ledger.jsonl"
    )


def test_create_archive_lands_in_vault(anchor_root: Path, tmp_path: Path) -> None:
    from drift.trinity import release

    scan_path = tmp_path / "scan.json"
    case_dir = tmp_path / "case_out"
    ledger_path = tmp_path / "run_ledger.jsonl"
    _write_slither_payload(scan_path)

    run_case_from_scan(
        scan_path,
        output_dir=case_dir,
        ledger=TrinityCaseLedger(ledger_path),
    )

    result = release.create_archive(
        case_dir,
        ledger_path=ledger_path,
        archive_ledger_path=release.TRINITY_ARCHIVE_LEDGER_PATH,
    )

    archive_dir = Path(result["archive_dir"])
    assert archive_dir.is_dir()
    assert str(archive_dir).startswith(str(anchor_root / "Anchor" / "archives"))
    assert (archive_dir / "archive_manifest.json").is_file()

    ledger_path_on_disk = anchor_root / "Anchor" / "history" / "trinity_archive_ledger.jsonl"
    assert ledger_path_on_disk.is_file()
    lines = [ln for ln in ledger_path_on_disk.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(lines) >= 1
    entry = json.loads(lines[-1])
    assert entry["archive_dir"] == str(archive_dir)

    listed = release.list_archives(limit=5)
    assert any(item.get("archive_id") == result["archive_id"] for item in listed)
