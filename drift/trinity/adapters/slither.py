"""Slither JSON adapter for Trinity.

This adapter turns Slither detector output into Trinity findings with stable
evidence refs, severity/confidence scores, and human-readable summaries.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List


def _clamp01(value: Any, default: float = 0.0) -> float:
    try:
        score = float(value)
    except (TypeError, ValueError):
        return default
    return max(0.0, min(1.0, score))


def _impact_score(label: Any) -> float:
    value = str(label or "").strip().lower()
    mapping = {
        "critical": 1.0,
        "high": 0.9,
        "medium": 0.7,
        "low": 0.45,
        "informational": 0.25,
        "error": 0.9,
        "warn": 0.7,
        "warning": 0.7,
        "note": 0.2,
        "pass": 0.05,
    }
    return mapping.get(value, 0.5)


def _confidence_score(label: Any) -> float:
    value = str(label or "").strip().lower()
    mapping = {
        "certain": 1.0,
        "high": 0.9,
        "medium": 0.7,
        "low": 0.45,
        "informational": 0.25,
    }
    return mapping.get(value, 0.55)


def _first_source_path(element: dict[str, Any]) -> str:
    source_mapping = element.get("source_mapping") or {}
    for key in ("filename_relative", "filename_absolute", "filename", "path"):
        value = source_mapping.get(key) or element.get(key)
        if value:
            return str(value)
    return "unknown"


def _extract_lines(element: dict[str, Any]) -> str:
    source_mapping = element.get("source_mapping") or {}
    start = source_mapping.get("lines") or source_mapping.get("line_start")
    if isinstance(start, list) and start:
        return str(start[0])
    if isinstance(start, int):
        return str(start)
    if isinstance(start, dict):
        for key in ("begin", "start", "from"):
            if start.get(key) is not None:
                return str(start[key])
    if element.get("line") is not None:
        return str(element.get("line"))
    if element.get("lines"):
        return str(element.get("lines"))
    return ""


def _make_evidence_ref(index: int) -> str:
    return f"slither:{index}"


def is_slither_payload(payload: Any) -> bool:
    if isinstance(payload, dict):
        results = payload.get("results") or {}
        if isinstance(results, dict) and results.get("detectors"):
            return True
        return bool(payload.get("detectors"))
    if isinstance(payload, list):
        return any(
            isinstance(record, dict) and any(key in record for key in ("detectors", "check", "impact"))
            for record in payload
        )
    return False


def build_slither_findings(payload: Any, source_path: str | Path) -> List[Dict[str, Any]]:
    source_path = Path(source_path)
    findings: List[Dict[str, Any]] = []

    def add_finding(
        *,
        title: str,
        summary: str,
        confidence: float,
        severity: float,
        evidence_ref: str,
        reproduction_command: str | None = None,
        raw: Any = None,
        labels: list[str] | None = None,
    ) -> None:
        findings.append(
            {
                "id": evidence_ref,
                "title": title,
                "summary": summary,
                "kind": "slither",
                "confidence": round(_clamp01(confidence, 0.5), 4),
                "severity": round(_clamp01(severity, 0.5), 4),
                "evidence_ref": evidence_ref,
                "reproduction_command": reproduction_command,
                "labels": labels or [],
                "source_path": str(source_path),
                "raw": raw,
            }
        )

    def parse_detector(detector: dict[str, Any], index: int) -> None:
        title = (
            detector.get("check")
            or detector.get("name")
            or detector.get("title")
            or f"slither_finding_{index}"
        )
        description = (
            detector.get("description")
            or detector.get("markdown")
            or detector.get("title")
            or title
        )
        elements = detector.get("elements") or []
        primary_element = elements[0] if elements and isinstance(elements[0], dict) else {}
        location = _first_source_path(primary_element) if primary_element else str(source_path)
        line_hint = _extract_lines(primary_element) if primary_element else ""
        reproduction = detector.get("reproduction_command") or detector.get("command")
        impact = _impact_score(detector.get("impact"))
        confidence = max(impact, _confidence_score(detector.get("confidence")))
        severity = max(impact, _impact_score(detector.get("impact")))
        summary = f"{description} @ {location}{(':' + line_hint) if line_hint else ''}"
        add_finding(
            title=title,
            summary=summary,
            confidence=confidence,
            severity=severity,
            evidence_ref=_make_evidence_ref(index),
            reproduction_command=reproduction,
            raw=detector,
            labels=[str(detector.get("impact") or ""), str(detector.get("confidence") or "")],
        )

    if isinstance(payload, dict):
        detectors = []
        results = payload.get("results") or {}
        if isinstance(results, dict):
            detectors = results.get("detectors") or []
        if not detectors:
            detectors = payload.get("detectors") or []
        for index, detector in enumerate(detectors):
            if isinstance(detector, dict):
                parse_detector(detector, index)
    elif isinstance(payload, list):
        index = 0
        for record in payload:
            if not isinstance(record, dict):
                continue
            if "detectors" in record and isinstance(record.get("detectors"), list):
                for detector in record["detectors"]:
                    if isinstance(detector, dict):
                        parse_detector(detector, index)
                        index += 1
                continue
            parse_detector(record, index)
            index += 1

    return findings
