"""Bridge ANCHOR anchor_sarif preprocessing into Trinity caseflow."""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from drift.trinity.adapters.sarif import (
    build_sarif_findings,
    is_sarif_payload,
    sarif_finding_to_trinity_dict,
)
from drift.trinity.sarif_models import SarifFinding


def resolve_anchor_root() -> Path | None:
    env = os.getenv("ANCHOR_ROOT", "").strip()
    candidates: list[Path] = []
    if env:
        candidates.append(Path(env).expanduser())
    infj_root = Path(__file__).resolve().parents[2]
    candidates.append(infj_root.parent / "ANCHOR")
    candidates.append(infj_root / "ANCHOR")
    for path in candidates:
        if (path / "anchor_sarif" / "pipeline.py").is_file():
            return path.resolve()
    return None


@dataclass
class PreprocessStats:
    ingested: int = 0
    after_dedup: int = 0
    signal_discarded: int = 0
    signal_promoted: int = 0
    signal_review: int = 0
    source: str = "local"

    def to_dict(self) -> dict[str, Any]:
        return {
            "ingested": self.ingested,
            "after_dedup": self.after_dedup,
            "signal_discarded": self.signal_discarded,
            "signal_promoted": self.signal_promoted,
            "signal_review": self.signal_review,
            "source": self.source,
        }


def _finding_to_sarif(finding: Any) -> SarifFinding:
    return SarifFinding(
        tool=finding.tool,
        rule_id=finding.rule_id,
        level=finding.level,
        message=finding.message,
        file_path=finding.file_path,
        start_line=finding.start_line,
        start_column=finding.start_column,
        end_line=finding.end_line,
        end_column=finding.end_column,
        snippet=finding.snippet,
        related_locations=list(finding.related_locations or []),
        code_flows=list(finding.code_flows or []),
        properties=dict(finding.properties or {}),
        raw_result=dict(finding.raw_result or {}),
        dedup_key=finding.dedup_key or "",
        normalized=dict(finding.normalized or {}),
    )


def _local_signal_filter(findings: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], PreprocessStats]:
    stats = PreprocessStats(ingested=len(findings), source="local_fallback")
    kept: list[dict[str, Any]] = []
    for item in findings:
        labels = [str(x).lower() for x in (item.get("labels") or [])]
        title = str(item.get("title") or "").lower()
        noise_markers = (
            "naming-convention",
            "solc-version",
            "unused-import",
            "dead-code",
            "pragma",
        )
        if any(m in title or any(m in label for label in labels) for m in noise_markers):
            stats.signal_discarded += 1
            continue
        stats.signal_promoted += 1
        kept.append(item)
    stats.after_dedup = len(findings)
    return kept, stats


def _run_anchor_stages(
    payload: dict[str, Any],
    source_path: Path,
    *,
    tool_hint: str,
    fp_discard_threshold: float,
) -> tuple[list[Any], PreprocessStats]:
    root = resolve_anchor_root()
    if root is None:
        raise ImportError("ANCHOR root not found")

    root_str = str(root)
    if root_str not in sys.path:
        sys.path.insert(0, root_str)

    from anchor_sarif.parser import parse_sarif  # type: ignore
    from anchor_sarif.pipeline import SARIFProcessingPipeline  # type: ignore

    pipeline = SARIFProcessingPipeline(
        filter_false_positives=True,
        fp_discard_threshold=fp_discard_threshold,
        enable_semantic_clustering=False,
    )
    raw = parse_sarif(payload, tool_name=tool_hint)
    stats = PreprocessStats(ingested=len(raw), source="anchor_sarif")

    norm_map = {id(f): pipeline.normalizer.normalize(f) for f in raw}
    for finding in raw:
        norm = norm_map[id(finding)]
        finding.normalized = {
            "original_rule_id": norm.original_rule_id,
            "tool": norm.tool,
            "cwe": norm.cwe,
            "owasp": norm.owasp,
            "category": norm.category,
            "confidence": norm.confidence,
        }

    deduped = pipeline._stage_deduplicate(raw)  # noqa: SLF001
    stats.after_dedup = len(deduped)
    filtered, counts = pipeline._stage_signal_filter(  # noqa: SLF001
        deduped,
        apply_filter=True,
    )
    stats.signal_discarded = counts.get("discarded", 0)
    stats.signal_promoted = counts.get("promoted", 0)
    stats.signal_review = counts.get("review", 0)
    return filtered, stats


def preprocess_sarif_payload(
    payload: dict[str, Any],
    source_path: str | Path,
    *,
    tool_hint: str = "unknown",
    filter_signals: bool = True,
    fp_discard_threshold: float = 0.7,
) -> tuple[list[dict[str, Any]], PreprocessStats]:
    """Run ANCHOR SARIF stages and return Trinity-shaped finding dicts."""
    source_path = Path(source_path)
    if not is_sarif_payload(payload):
        return [], PreprocessStats(source="none")

    hint = tool_hint
    if hint == "unknown":
        stem = source_path.stem.lower()
        for candidate in ("slither", "mythril", "aderyn", "semgrep", "codeql"):
            if candidate in stem:
                hint = candidate
                break

    if filter_signals:
        try:
            anchor_findings, stats = _run_anchor_stages(
                payload,
                source_path,
                tool_hint=hint,
                fp_discard_threshold=fp_discard_threshold,
            )
            trinity_findings = [
                sarif_finding_to_trinity_dict(
                    _finding_to_sarif(f),
                    index=i,
                    source_path=source_path,
                )
                for i, f in enumerate(anchor_findings)
            ]
            for item in trinity_findings:
                item.setdefault("labels", []).append("anchor_signal_filter")
            return trinity_findings, stats
        except ImportError:
            pass

    findings = build_sarif_findings(
        payload,
        source_path,
        tool_hint=hint,
        normalize=True,
        dedupe=True,
    )
    if not filter_signals:
        stats = PreprocessStats(
            ingested=len(findings),
            after_dedup=len(findings),
            signal_promoted=len(findings),
            source="trinity_sarif",
        )
        return findings, stats
    return _local_signal_filter(findings)


def preprocess_sarif_file(
    path: str | Path,
    *,
    tool_hint: str = "unknown",
    filter_signals: bool = True,
) -> tuple[list[dict[str, Any]], PreprocessStats]:
    source_path = Path(path)
    payload = json.loads(source_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return [], PreprocessStats(source="invalid")
    return preprocess_sarif_payload(
        payload,
        source_path,
        tool_hint=tool_hint,
        filter_signals=filter_signals,
    )
