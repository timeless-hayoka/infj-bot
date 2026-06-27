"""Verify Drift resolves ANCHOR vault as its knowledge source when configured."""

from __future__ import annotations

import importlib
import os
from pathlib import Path

import pytest


@pytest.fixture()
def anchor_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    vault = tmp_path / "AnchorVault"
    knowledge = vault / "knowledge"
    (knowledge / "education").mkdir(parents=True)
    (knowledge / "education" / "sample.md").write_text(
        "# Sample\nDrift reads from AnchorVault knowledge.\n",
        encoding="utf-8",
    )
    (vault / "hunt_briefs").mkdir()
    (vault / "hunt_briefs" / "2026-06-26.md").write_text("daily brief", encoding="utf-8")
    (vault / "claims").mkdir()
    monkeypatch.setenv("ANCHOR_DATA_ROOT", str(tmp_path))
    monkeypatch.setenv("ANCHOR_VAULT_ROOT", str(vault))

    for module_name in (
        "config_adapter",
        "drift.config_adapter",
        "core.config",
        "core.plugins.documents",
        "drift.trinity.http_api",
    ):
        importlib.reload(importlib.import_module(module_name))
    return tmp_path


def test_anchor_vault_root_from_data_root(anchor_env: Path) -> None:
    from drift.config_adapter import get_anchor_vault_root, get_anchor_knowledge_dir

    assert get_anchor_vault_root() == anchor_env / "AnchorVault"
    assert get_anchor_knowledge_dir() == anchor_env / "AnchorVault" / "knowledge"


def test_chroma_persist_under_vault_knowledge(anchor_env: Path) -> None:
    from drift.config_adapter import get_anchor_knowledge_chroma_dir, PERSIST_DIRECTORY

    chroma = get_anchor_knowledge_chroma_dir()
    assert chroma is not None
    assert chroma.is_dir()
    assert Path(PERSIST_DIRECTORY) == chroma


def test_document_store_uses_vault_chroma(anchor_env: Path, tmp_path: Path) -> None:
    from core.plugins.documents import DocumentStore

    store = DocumentStore(persist_directory=str(tmp_path / "isolated_chroma"))
    sample = anchor_env / "AnchorVault" / "knowledge" / "education" / "sample.md"
    chunks = store.ingest(str(sample), tags=["anchor"])
    assert chunks >= 1
    hits = store.search("AnchorVault knowledge", n_results=1)
    assert hits
    assert "AnchorVault" in hits[0]["document"]


def test_vault_snapshot_reports_knowledge_source(anchor_env: Path) -> None:
    from drift.trinity import http_api

    snap = http_api.get_trinity_vault_snapshot()
    assert snap["status"] == "ready"
    assert snap["knowledge_source"] == "anchor_vault"
    assert snap["knowledge_files"] >= 1
    assert snap["news_briefs"] >= 1
    assert str(snap["vault_root"]).endswith("AnchorVault")


@pytest.mark.skipif(
    not Path("/mnt/anchor-hdd/AnchorVault/knowledge").is_dir(),
    reason="live ANCHOR HDD not mounted",
)
def test_live_storage_env_points_at_anchor_vault(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage_env = Path.home() / ".drift_os" / "config" / "storage.env"
    if not storage_env.is_file():
        pytest.skip("storage.env not configured")

    vault_root: Path | None = None
    for line in storage_env.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        monkeypatch.setenv(key.strip(), value.strip())
        if key.strip() == "ANCHOR_VAULT_ROOT":
            vault_root = Path(value.strip())

    if vault_root is None:
        pytest.skip("ANCHOR_VAULT_ROOT not in storage.env")

    for module_name in ("config_adapter", "drift.config_adapter", "core.config"):
        importlib.reload(importlib.import_module(module_name))

    assert vault_root.is_dir()
    assert (vault_root / "knowledge").is_dir()

    from drift.config_adapter import ANCHOR_VAULT_ROOT, get_anchor_knowledge_dir

    assert ANCHOR_VAULT_ROOT is not None
    assert ANCHOR_VAULT_ROOT.resolve() == vault_root.resolve()
    knowledge = get_anchor_knowledge_dir()
    assert knowledge is not None
    assert knowledge.is_dir()
