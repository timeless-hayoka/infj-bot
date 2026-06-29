from __future__ import annotations

import json
from pathlib import Path

from drift.trinity.adapters.sarif import (
    build_sarif_findings,
    is_sarif_payload,
    parse_sarif_payload,
    process_sarif_findings,
)
from drift.trinity.caseflow import parse_scanner_input
from drift.trinity.rule_normalizer import RuleNormalizer
from drift.trinity.sarif_deduplicator import SarifDeduplicator
from drift.trinity.sarif_models import SarifFinding

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_is_sarif_payload():
    assert is_sarif_payload(_load("minimal_codeql.sarif")) is True
    assert is_sarif_payload({"results": []}) is False


def test_parse_codeql_sarif_extracts_dataflow():
    payload = _load("minimal_codeql.sarif")
    findings = parse_sarif_payload(payload, source_path="codeql.sarif", tool_hint="codeql")
    assert len(findings) == 1
    finding = findings[0]
    assert finding.tool == "CodeQL"
    assert finding.rule_id == "py/sql-injection"
    assert finding.file_path == "app/views.py"
    assert finding.start_line == 42
    assert len(finding.code_flows) == 1
    assert len(finding.code_flows[0]) == 2


def test_rule_normalizer_maps_codeql_rule():
    payload = _load("minimal_codeql.sarif")
    finding = parse_sarif_payload(payload, source_path="codeql.sarif")[0]
    norm = RuleNormalizer().normalize(finding)
    assert norm.cwe == "CWE-89"
    assert norm.category == "SQL Injection"


def test_rule_normalizer_uses_sarif_properties():
    payload = _load("minimal_semgrep.sarif")
    finding = parse_sarif_payload(payload, source_path="semgrep.sarif")[0]
    norm = RuleNormalizer().normalize(finding)
    assert norm.cwe == "CWE-94"
    assert norm.category == "Code Injection"


def test_deduplicator_merges_cross_tool_same_line():
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
    unique = dedup.deduplicate([codeql, semgrep], strategy="normalized").unique_findings
    assert len(unique) == 1


def test_build_sarif_findings_returns_trinity_shape(tmp_path):
    payload = _load("minimal_codeql.sarif")
    path = tmp_path / "codeql.sarif"
    path.write_text(json.dumps(payload), encoding="utf-8")
    findings = build_sarif_findings(payload, path)
    assert len(findings) == 1
    row = findings[0]
    assert row["kind"] == "sarif:codeql"
    assert row["normalized"]["cwe"] == "CWE-89"
    assert row["dedup_key"]
    assert "dataflow steps" in row["summary"]


def test_parse_scanner_input_auto_detects_sarif(tmp_path):
    payload = _load("minimal_semgrep.sarif")
    path = tmp_path / "semgrep.sarif"
    path.write_text(json.dumps(payload), encoding="utf-8")
    scan = parse_scanner_input(path)
    assert scan["format"] == "sarif"
    assert scan["finding_count"] == 1
    assert scan["findings"][0]["normalized"]["category"] == "Code Injection"


def test_process_sarif_findings_pipeline_order():
    payload = _load("minimal_codeql.sarif")
    parsed = parse_sarif_payload(payload, source_path="codeql.sarif")
    processed = process_sarif_findings(parsed, normalize=True, dedupe=True)
    assert processed[0].normalized["category"] == "SQL Injection"
