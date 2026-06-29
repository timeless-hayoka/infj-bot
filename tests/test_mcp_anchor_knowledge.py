"""MCP + anchor_context integration for structured ANCHOR knowledge."""

from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest


@pytest.fixture()
def anchor_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    repo = tmp_path / "ANCHOR"
    knowledge = repo / "knowledge"
    knowledge.mkdir(parents=True)
    real_anchor = Path(__file__).resolve().parents[2] / "ANCHOR"
    provider_src = real_anchor / "knowledge_provider.py"
    if provider_src.is_file():
        (repo / "knowledge_provider.py").write_text(
            provider_src.read_text(encoding="utf-8"),
            encoding="utf-8",
        )
    (knowledge / "manifest.json").write_text(
        json.dumps(
            {
                "version": 1,
                "topics": [
                    {
                        "slug": "sarif",
                        "title": "SARIF Pipeline",
                        "path": "sarif.md",
                        "subsystems": ["sarif", "pipeline"],
                        "tags": ["sarif"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (knowledge / "sarif.md").write_text(
        "# SARIF Pipeline\n\nNormalize SARIF findings and cluster them.\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("ANCHOR_ROOT", str(repo))
    import core.anchor_context as anchor_context

    anchor_context._knowledge_provider = None
    for name in ("core.anchor_context", "drift.core.anchor_context"):
        if name in importlib.sys.modules:
            mod = importlib.reload(importlib.import_module(name))
            mod._knowledge_provider = None
    return repo


def test_list_and_search_repo_knowledge(anchor_repo: Path) -> None:
    from drift.core.anchor_context import (
        get_anchor_repo_knowledge_topic,
        list_anchor_repo_knowledge,
        refs_anchor_repo_knowledge,
        search_anchor_repo_knowledge,
    )

    topics = list_anchor_repo_knowledge()
    assert len(topics) == 1
    assert topics[0]["slug"] == "sarif"

    hits = search_anchor_repo_knowledge("normalize SARIF", limit=3)
    assert hits
    assert hits[0]["slug"] == "sarif"

    payload = get_anchor_repo_knowledge_topic("sarif")
    assert payload is not None
    assert "SARIF Pipeline" in payload["content"]

    refs = refs_anchor_repo_knowledge("sarif")
    assert any(row["slug"] == "sarif" for row in refs)


def test_mcp_anchor_knowledge_tools(anchor_repo: Path) -> None:
    from core.mcp_server import (
        anchor_knowledge_get,
        anchor_knowledge_list,
        anchor_knowledge_refs,
        anchor_knowledge_search,
    )

    listing = anchor_knowledge_list()
    assert "sarif" in listing

    search = anchor_knowledge_search("cluster", limit=2)
    assert "sarif" in search

    doc = anchor_knowledge_get("sarif")
    assert "SARIF Pipeline" in doc

    refs = anchor_knowledge_refs("pipeline")
    assert "sarif" in refs
