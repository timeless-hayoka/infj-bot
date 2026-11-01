from __future__ import annotations

from pathlib import Path

from core import anchor_analytics


def test_build_benchmark_analytics_when_anchor_present() -> None:
    payload = anchor_analytics.build_benchmark_analytics(limit=5, top_n=3)
    root = anchor_analytics.resolve_anchor_root()
    if root is None:
        assert payload["status"] == "unavailable"
        return
    assert payload["status"] == "ready"
    trends = payload["benchmark_trends"]
    assert trends is not None
    assert "schema_version" in trends
    if trends.get("published_count"):
        assert "average_reproduction_rate_display" in trends
    strategy = payload["benchmark_strategy"]
    assert strategy is not None
    assert strategy.get("source") == "anchor_strategy.compute_strategy"


def test_analytics_preserves_application_imports(monkeypatch):
    import sys
    from types import ModuleType

    root = anchor_analytics.resolve_anchor_root()
    if root is None:
        import pytest

        pytest.skip("sibling ANCHOR checkout not available")
    sentinel = ModuleType("anchor_trends")
    monkeypatch.setitem(sys.modules, "anchor_trends", sentinel)
    before = list(sys.path)
    result = anchor_analytics.build_benchmark_analytics()
    assert result["status"] == "ready"
    assert sys.path == before
    assert sys.modules["anchor_trends"] is sentinel
    assert Path(result["analytics_sources"]["anchor_strategy"]).parent == root
