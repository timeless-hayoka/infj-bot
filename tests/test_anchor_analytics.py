from __future__ import annotations

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
