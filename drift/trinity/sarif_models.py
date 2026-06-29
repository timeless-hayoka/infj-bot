"""Shared datatypes for SARIF ingestion in Trinity."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class SarifFinding:
    tool: str
    rule_id: str
    level: str
    message: str
    file_path: str
    start_line: int
    start_column: int | None = None
    end_line: int | None = None
    end_column: int | None = None
    snippet: str | None = None
    related_locations: list[dict[str, Any]] = field(default_factory=list)
    code_flows: list[list[dict[str, Any]]] = field(default_factory=list)
    properties: dict[str, Any] = field(default_factory=dict)
    raw_result: dict[str, Any] = field(default_factory=dict)
    dedup_key: str = ""
    normalized: dict[str, Any] = field(default_factory=dict)


@dataclass
class NormalizedRule:
    original_rule_id: str
    tool: str
    cwe: str | None = None
    owasp: str | None = None
    category: str = "Uncategorized"
    severity_hint: str | None = None
    tags: list[str] = field(default_factory=list)
    confidence: float = 1.0


@dataclass
class EnrichedFinding:
    finding: SarifFinding
    normalized: NormalizedRule
    source_context: str | None = None
    dedup_key: str = ""
    cluster_id: int | None = None
    cluster_summary: str = ""
    processed_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    )
