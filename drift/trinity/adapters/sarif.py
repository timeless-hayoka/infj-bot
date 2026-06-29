"""SARIF 2.1 adapter for Trinity scanner ingestion."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from drift.trinity.rule_normalizer import RuleNormalizer
from drift.trinity.sarif_deduplicator import SarifDeduplicator
from drift.trinity.sarif_models import SarifFinding

_LEVEL_SEVERITY = {
    "error": 0.9,
    "warning": 0.7,
    "note": 0.35,
    "none": 0.2,
    "informational": 0.25,
}


def is_sarif_payload(payload: Any) -> bool:
    if not isinstance(payload, dict):
        return False
    version = str(payload.get("version", ""))
    if not version.startswith("2."):
        return False
    runs = payload.get("runs")
    return isinstance(runs, list) and bool(runs)


def _normalize_uri(uri: str) -> str:
    value = str(uri or "").strip()
    if value.startswith("file://"):
        return value.removeprefix("file://")
    return value


def _rule_index(run: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rules = run.get("tool", {}).get("driver", {}).get("rules") or []
    index: dict[str, dict[str, Any]] = {}
    if isinstance(rules, list):
        for rule in rules:
            if isinstance(rule, dict) and rule.get("id"):
                index[str(rule["id"])] = rule
    return index


def _extract_code_flows(result: dict[str, Any]) -> list[list[dict[str, Any]]]:
    flows: list[list[dict[str, Any]]] = []
    for code_flow in result.get("codeFlows") or []:
        if not isinstance(code_flow, dict):
            continue
        for thread_flow in code_flow.get("threadFlows") or []:
            if not isinstance(thread_flow, dict):
                continue
            locations: list[dict[str, Any]] = []
            for loc in thread_flow.get("locations") or []:
                if not isinstance(loc, dict):
                    continue
                physical = loc.get("location", {}).get("physicalLocation", {})
                region = physical.get("region", {})
                locations.append(
                    {
                        "file": _normalize_uri(physical.get("artifactLocation", {}).get("uri", "")),
                        "line": region.get("startLine"),
                        "message": loc.get("location", {}).get("message", {}).get("text", ""),
                    }
                )
            if locations:
                flows.append(locations)
    return flows


def load_sarif_file(path: str | Path, *, tool_hint: str = "unknown") -> list[SarifFinding]:
    source_path = Path(path)
    payload = json.loads(source_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return []
    return parse_sarif_payload(payload, source_path=source_path, tool_hint=tool_hint)


def parse_sarif_payload(
    payload: dict[str, Any],
    *,
    source_path: str | Path,
    tool_hint: str = "unknown",
) -> list[SarifFinding]:
    if not is_sarif_payload(payload):
        return []

    findings: list[SarifFinding] = []
    for run in payload.get("runs") or []:
        if not isinstance(run, dict):
            continue
        driver = run.get("tool", {}).get("driver", {})
        tool_name = str(driver.get("name") or tool_hint or "unknown")
        rules = _rule_index(run)

        for result in run.get("results") or []:
            if not isinstance(result, dict):
                continue
            rule_id = str(result.get("ruleId") or "unknown")
            rule_meta = rules.get(rule_id, {})
            rule_props = rule_meta.get("properties") if isinstance(rule_meta, dict) else {}
            result_props = result.get("properties") if isinstance(result.get("properties"), dict) else {}
            merged_props = {**(rule_props or {}), **(result_props or {})}

            locations = result.get("locations") or [{}]
            primary = locations[0] if locations else {}
            physical = primary.get("physicalLocation", {}) if isinstance(primary, dict) else {}
            artifact = physical.get("artifactLocation", {}) if isinstance(physical, dict) else {}
            region = physical.get("region", {}) if isinstance(physical, dict) else {}

            message_obj = result.get("message") or {}
            message = message_obj.get("text") if isinstance(message_obj, dict) else str(message_obj)
            snippet_obj = region.get("snippet") if isinstance(region, dict) else None
            snippet = snippet_obj.get("text") if isinstance(snippet_obj, dict) else None

            findings.append(
                SarifFinding(
                    tool=tool_name,
                    rule_id=rule_id,
                    level=str(result.get("level") or "note"),
                    message=str(message or rule_id),
                    file_path=_normalize_uri(artifact.get("uri", "")),
                    start_line=int(region.get("startLine") or 0),
                    start_column=region.get("startColumn"),
                    end_line=region.get("endLine"),
                    end_column=region.get("endColumn"),
                    snippet=snippet,
                    related_locations=[
                        loc for loc in (result.get("relatedLocations") or []) if isinstance(loc, dict)
                    ],
                    code_flows=_extract_code_flows(result),
                    properties=merged_props,
                    raw_result=result,
                )
            )
    return findings


def process_sarif_findings(
    findings: list[SarifFinding],
    *,
    normalize: bool = True,
    dedupe: bool = True,
    dedupe_strategy: str = "location",
    mapping_file: Path | None = None,
    line_tolerance: int = 3,
) -> list[SarifFinding]:
    if normalize:
        normalizer = RuleNormalizer(mapping_file=mapping_file)
        for finding in findings:
            norm = normalizer.normalize(finding)
            finding.normalized = {
                "original_rule_id": norm.original_rule_id,
                "tool": norm.tool,
                "cwe": norm.cwe,
                "owasp": norm.owasp,
                "category": norm.category,
                "severity_hint": norm.severity_hint,
                "tags": norm.tags,
                "confidence": norm.confidence,
                "mapping_version": normalizer.mapping_version,
            }

    if dedupe and findings:
        deduplicator = SarifDeduplicator(line_tolerance=line_tolerance)
        result = deduplicator.deduplicate(findings, strategy=dedupe_strategy)
        return result.unique_findings
    return findings


def _severity_from_level(level: str) -> float:
    return _LEVEL_SEVERITY.get(str(level or "").lower(), 0.5)


def sarif_finding_to_trinity_dict(finding: SarifFinding, *, index: int, source_path: Path) -> dict[str, Any]:
    norm = finding.normalized or {}
    category = norm.get("category") or "Uncategorized"
    cwe = norm.get("cwe") or ""
    location = finding.file_path or str(source_path)
    line_hint = f":{finding.start_line}" if finding.start_line else ""
    summary = finding.message
    if finding.code_flows:
        summary = f"{summary} (dataflow steps: {len(finding.code_flows[0])})"
    summary = f"{summary} @ {location}{line_hint}"

    evidence_ref = finding.dedup_key or f"sarif:{index}"
    tool_slug = finding.tool.lower().replace(" ", "-")
    return {
        "id": evidence_ref,
        "title": finding.rule_id,
        "summary": summary,
        "kind": f"sarif:{tool_slug}",
        "confidence": round(float(norm.get("confidence", 0.6)), 4),
        "severity": round(_severity_from_level(finding.level), 4),
        "evidence_ref": evidence_ref,
        "reproduction_command": None,
        "labels": [category, cwe, finding.level, tool_slug],
        "source_path": str(source_path),
        "file_path": finding.file_path,
        "start_line": finding.start_line,
        "normalized": finding.normalized,
        "dedup_key": finding.dedup_key,
        "code_flows": finding.code_flows,
        "raw": finding.raw_result,
    }


def build_sarif_findings(
    payload: Any,
    source_path: str | Path,
    *,
    tool_hint: str = "unknown",
    normalize: bool = True,
    dedupe: bool = True,
    dedupe_strategy: str = "location",
    mapping_file: Path | None = None,
) -> list[dict[str, Any]]:
    source_path = Path(source_path)
    if not isinstance(payload, dict):
        return []

    parsed = parse_sarif_payload(payload, source_path=source_path, tool_hint=tool_hint)
    processed = process_sarif_findings(
        parsed,
        normalize=normalize,
        dedupe=dedupe,
        dedupe_strategy=dedupe_strategy,
        mapping_file=mapping_file,
    )
    return [
        sarif_finding_to_trinity_dict(finding, index=index, source_path=source_path)
        for index, finding in enumerate(processed)
    ]
