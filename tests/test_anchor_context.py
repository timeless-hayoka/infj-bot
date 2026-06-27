"""Drift must know ANCHOR vault paths in prompt and path snapshots."""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest


@pytest.fixture()
def anchor_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    vault = tmp_path / "AnchorVault"
    knowledge = vault / "knowledge" / "education"
    knowledge.mkdir(parents=True)
    (knowledge / "anchor-readme.md").write_text(
        "ANCHOR vault education corpus for Drift.\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("ANCHOR_DATA_ROOT", str(tmp_path))
    monkeypatch.setenv("ANCHOR_VAULT_ROOT", str(vault))
    for name in ("config_adapter", "drift.config_adapter", "core.anchor_context", "drift.trinity.http_api"):
        importlib.reload(importlib.import_module(name))
    return tmp_path


def test_prompt_block_names_vault_paths(anchor_env: Path) -> None:
    from drift.core.anchor_context import format_anchor_vault_prompt_block

    block = format_anchor_vault_prompt_block()
    assert "AnchorVault" in block
    assert "knowledge corpus" in block.lower()
    assert str(anchor_env / "AnchorVault" / "knowledge") in block


def test_paths_snapshot_includes_vault(anchor_env: Path) -> None:
    from drift.trinity.http_api import get_trinity_paths_snapshot

    paths = get_trinity_paths_snapshot()
    assert paths["vault_root"].endswith("AnchorVault")
    assert paths["knowledge_root"].endswith("knowledge")


def test_vault_knowledge_search_finds_file(anchor_env: Path) -> None:
    from drift.core.anchor_context import search_vault_knowledge

    hits = search_vault_knowledge("education corpus", n_results=3)
    assert hits
    assert any("anchor-readme" in h["filename"] for h in hits)
