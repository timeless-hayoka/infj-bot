from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import numpy as np
import pytest

from drift.trinity.adapters.sarif import parse_sarif_payload
from drift.trinity.sarif_deduplicator import SarifDeduplicator
from drift.trinity.sarif_models import SarifFinding
from drift.trinity.sarif_pipeline.pipeline import SARIFProcessingPipeline
from drift.trinity.sarif_pipeline.semantic_clusterer import ClusterResult, semantic_clustering_available

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _fixture_path(name: str) -> Path:
    return FIXTURES / name


class _StubClusterer:
    def cluster(self, findings, return_cluster_summaries=True):
        labels = np.array([0] * len(findings))
        return ClusterResult(
            cluster_labels=labels,
            n_clusters=1,
            cluster_summaries={0: "Base cluster summary"},
        )

    def assign_clusters_to_findings(self, findings, cluster_result):
        for finding in findings:
            finding.properties["semantic_cluster"] = {
                "cluster_id": 0,
                "is_noise": False,
                "cluster_summary": "Base cluster summary",
            }
        return findings


def test_sarif_pipeline_persists_sqlite_without_clustering(tmp_path: Path):
    db_path = tmp_path / "findings.db"
    pipeline = SARIFProcessingPipeline(
        db_path=db_path,
        enable_semantic_clustering=False,
        enable_chroma=False,
    )
    results = pipeline.process(
        {
            "codeql": _fixture_path("minimal_codeql.sarif"),
            "semgrep": _fixture_path("minimal_semgrep.sarif"),
        }
    )
    assert len(results) == 2
    assert all(row.dedup_key for row in results)
    assert {row.normalized.category for row in results} == {"SQL Injection", "Code Injection"}

    conn = sqlite3.connect(db_path)
    rows = conn.execute("SELECT dedup_key, normalized_category, tool FROM findings").fetchall()
    conn.close()
    assert len(rows) == 2
    categories = {row[1] for row in rows}
    assert "SQL Injection" in categories
    assert "Code Injection" in categories


def test_sarif_pipeline_llm_summarizer_hook(tmp_path: Path):
    calls: list[str] = []

    def fake_llm(prompt: str) -> str:
        calls.append(prompt)
        return "Synthetic cluster summary."

    pipeline = SARIFProcessingPipeline(
        db_path=tmp_path / "findings.db",
        enable_semantic_clustering=False,
        enable_chroma=False,
        llm_summarizer=fake_llm,
    )
    pipeline.clusterer = _StubClusterer()
    enriched = pipeline.process({"codeql": _fixture_path("minimal_codeql.sarif")}, enable_llm_summaries=True)
    assert enriched[0].cluster_summary == "Synthetic cluster summary."
    assert calls
    assert "Cluster 0" in calls[0]


def test_sarif_pipeline_source_context(tmp_path: Path):
    source_root = tmp_path / "repo"
    views = source_root / "app"
    views.mkdir(parents=True)
    (views / "views.py").write_text(
        "\n".join(f"line {index}" for index in range(1, 50)),
        encoding="utf-8",
    )

    pipeline = SARIFProcessingPipeline(
        db_path=tmp_path / "findings.db",
        source_root=source_root,
        enable_semantic_clustering=False,
        enable_chroma=False,
    )
    enriched = pipeline.process({"codeql": _fixture_path("minimal_codeql.sarif")})
    assert enriched[0].source_context
    assert "line 42" in enriched[0].source_context


def test_sarif_pipeline_to_trinity_findings(tmp_path: Path):
    pipeline = SARIFProcessingPipeline(
        db_path=tmp_path / "findings.db",
        enable_semantic_clustering=False,
        enable_chroma=False,
    )
    enriched = pipeline.process({"codeql": _fixture_path("minimal_codeql.sarif")})
    rows = pipeline.to_trinity_findings(enriched, source_path=_fixture_path("minimal_codeql.sarif"))
    assert rows[0]["kind"] == "sarif:codeql"
    assert rows[0]["normalized"]["cwe"] == "CWE-89"
    assert "cluster_summary" in rows[0]


def test_deduplicate_cross_tool_helper():
    dedup = SarifDeduplicator(line_tolerance=3)
    codeql = SarifFinding(
        tool="codeql",
        rule_id="py/sql-injection",
        level="error",
        message="SQL injection",
        file_path="app/views.py",
        start_line=42,
        normalized={"category": "SQL Injection", "cwe": "CWE-89"},
    )
    semgrep = SarifFinding(
        tool="semgrep",
        rule_id="python.sql.injection",
        level="error",
        message="Possible SQL injection",
        file_path="app/views.py",
        start_line=43,
        normalized={"category": "SQL Injection", "cwe": "CWE-89"},
    )
    result = dedup.deduplicate_cross_tool(
        {"codeql": [codeql], "semgrep": [semgrep]},
        strategy="normalized",
    )
    assert len(result.unique_findings) == 1
    assert dedup.key_strategy(codeql, strategy="normalized") == dedup.key_strategy(
        semgrep, strategy="normalized"
    )


@pytest.mark.skipif(not semantic_clustering_available(), reason="semantic clustering deps not installed")
def test_semantic_clusterer_assigns_cluster_metadata():
    from drift.trinity.sarif_pipeline.semantic_clusterer import SemanticClusterer

    payload_a = json.loads(_fixture_path("minimal_codeql.sarif").read_text(encoding="utf-8"))
    payload_b = json.loads(_fixture_path("minimal_semgrep.sarif").read_text(encoding="utf-8"))
    findings = parse_sarif_payload(payload_a, source_path="codeql.sarif") + parse_sarif_payload(
        payload_b, source_path="semgrep.sarif"
    )
    for finding in findings:
        finding.normalized = {"category": finding.rule_id, "cwe": "CWE-000"}

    clusterer = SemanticClusterer(hdbscan_min_cluster_size=2)
    result = clusterer.cluster(findings)
    clusterer.assign_clusters_to_findings(findings, result)
    assert "semantic_cluster" in findings[0].properties
