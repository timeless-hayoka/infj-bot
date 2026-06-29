"""End-to-end Trinity caseflow helpers.

This module turns scanner input into a council round, writes the evidence
packet bundle, and appends a persistent ledger entry.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Optional

from drift.config_adapter import LOGS_DIR

from .adapters.slither import build_slither_findings, is_slither_payload
from .adapters.sarif import build_sarif_findings, is_sarif_payload
from .council.council_runner import CouncilRunner
from .council.evidence_board import EvidenceBoard

TRINITY_CASES_DIR = Path(
    os.getenv('TRINITY_CASES_DIR', str(LOGS_DIR / 'trinity_cases'))
).expanduser()
TRINITY_LEDGER_PATH = Path(
    os.getenv('TRINITY_LEDGER_PATH', str(LOGS_DIR / 'trinity_case_ledger.jsonl'))
).expanduser()


def utc_stamp() -> str:
    return datetime.now(UTC).isoformat().replace('+00:00', 'Z')


def _load_jsonish(path: Path) -> Any:
    text = path.read_text(encoding='utf-8', errors='ignore').strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        records = []
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                records.append({'raw': line})
        return records if records else {'raw': text}

def _impact_score(label: Any) -> float:
    value = str(label or '').strip().lower()
    mapping = {
        'critical': 1.0,
        'high': 0.9,
        'medium': 0.7,
        'low': 0.45,
        'informational': 0.25,
        'error': 0.9,
        'warn': 0.7,
        'warning': 0.7,
        'note': 0.2,
        'pass': 0.05,
    }
    return mapping.get(value, 0.5)


def _confidence_score(label: Any) -> float:
    value = str(label or '').strip().lower()
    mapping = {
        'certain': 1.0,
        'high': 0.9,
        'medium': 0.7,
        'low': 0.45,
        'informational': 0.25,
    }
    return mapping.get(value, 0.55)




def parse_scanner_input(path: str | Path, format_hint: str = 'auto') -> dict[str, Any]:
    source_path = Path(path)
    payload = _load_jsonish(source_path)
    scan_format = format_hint.lower() if format_hint else 'auto'
    findings: list[dict[str, Any]] = []
    sarif_pipeline_stats = None

    def add_finding(
        *,
        title: str,
        summary: str,
        kind: str,
        confidence: float,
        severity: float,
        evidence_ref: str,
        reproduction_command: str | None = None,
        raw: Any = None,
        labels: Optional[list[str]] = None,
    ) -> None:
        findings.append(
            {
                'id': evidence_ref,
                'title': title,
                'summary': summary,
                'kind': kind,
                'confidence': round(max(0.0, min(1.0, float(confidence))), 4),
                'severity': round(max(0.0, min(1.0, float(severity))), 4),
                'evidence_ref': evidence_ref,
                'reproduction_command': reproduction_command,
                'labels': labels or [],
                'source_path': str(source_path),
                'raw': raw,
            }
        )

    def parse_foundry(record: dict[str, Any]) -> None:
        failures: list[Any] = []
        if isinstance(record.get('failures'), list):
            failures = record['failures']
        elif isinstance(record.get('test_results'), list):
            failures = [
                item
                for item in record['test_results']
                if str(item.get('status', '')).lower() not in {'pass', 'passed', 'ok', 'success'}
            ]
        elif isinstance(record.get('tests'), list):
            failures = [
                item
                for item in record['tests']
                if str(item.get('status', '')).lower() not in {'pass', 'passed', 'ok', 'success'}
            ]

        for index, failure in enumerate(failures):
            if not isinstance(failure, dict):
                failure = {'message': failure}
            title = (
                failure.get('test')
                or failure.get('name')
                or failure.get('title')
                or failure.get('contract')
                or f'foundry_failure_{index}'
            )
            summary = (
                failure.get('reason')
                or failure.get('message')
                or failure.get('error')
                or failure.get('stderr')
                or failure.get('output')
                or title
            )
            evidence_ref = f'foundry:{index}'
            reproduction = (
                failure.get('reproduction_command')
                or record.get('reproduction_command')
                or 'forge test'
            )
            confidence = max(0.55, _confidence_score(failure.get('confidence')))
            severity = max(0.5, _impact_score(failure.get('severity') or failure.get('impact')))
            add_finding(
                title=title,
                summary=summary,
                kind='foundry',
                confidence=confidence,
                severity=severity,
                evidence_ref=evidence_ref,
                reproduction_command=reproduction,
                raw=failure,
                labels=[str(failure.get('status') or ''), str(failure.get('reason') or '')],
            )

    if isinstance(payload, dict):
        looks_like_slither = is_slither_payload(payload)
        looks_like_sarif = is_sarif_payload(payload)
        looks_like_foundry = bool(payload.get('failures') or payload.get('test_results') or payload.get('tests'))
        looks_like_generic_findings = isinstance(payload.get('findings'), list)

        sarif_pipeline_stats = None
        if scan_format == 'sarif' or (scan_format == 'auto' and looks_like_sarif):
            from .anchor_pipeline_bridge import preprocess_sarif_payload

            filtered, pipeline_stats = preprocess_sarif_payload(payload, source_path)
            findings.extend(filtered)
            scan_format = 'sarif'
            sarif_pipeline_stats = pipeline_stats.to_dict()
        elif scan_format == 'slither' or (scan_format == 'auto' and looks_like_slither):
            findings.extend(build_slither_findings(payload, source_path))
            scan_format = 'slither'
        elif scan_format == 'foundry' or (scan_format == 'auto' and looks_like_foundry):
            parse_foundry(payload)
            scan_format = 'foundry'
        elif looks_like_generic_findings:
            for index, record in enumerate(payload.get('findings', [])):
                if not isinstance(record, dict):
                    continue
                add_finding(
                    title=record.get('title') or record.get('name') or f'finding_{index}',
                    summary=record.get('summary')
                    or record.get('description')
                    or json.dumps(record, ensure_ascii=True)[:500],
                    kind=str(record.get('kind') or 'generic'),
                    confidence=_confidence_score(record.get('confidence')),
                    severity=_impact_score(record.get('severity')),
                    evidence_ref=record.get('evidence_ref') or f'{source_path.stem}:{index}',
                    reproduction_command=record.get('reproduction_command'),
                    raw=record,
                    labels=[str(record.get('status') or ''), str(record.get('kind') or '')],
                )
            if scan_format == 'auto':
                scan_format = 'generic'
        else:
            title = payload.get('title') or payload.get('name') or source_path.stem
            summary = (
                payload.get('summary')
                or payload.get('description')
                or json.dumps(payload, ensure_ascii=True)[:500]
            )
            add_finding(
                title=title,
                summary=summary,
                kind='generic',
                confidence=_confidence_score(payload.get('confidence')),
                severity=_impact_score(payload.get('severity')),
                evidence_ref=f'{source_path.stem}:0',
                reproduction_command=payload.get('reproduction_command'),
                raw=payload,
            )
    elif isinstance(payload, list):
        for index, record in enumerate(payload):
            if not isinstance(record, dict):
                continue
            if scan_format == 'slither' or any(k in record for k in ('detectors', 'check', 'impact')):
                findings.extend(build_slither_findings(record, source_path))
                scan_format = 'slither'
            elif scan_format == 'foundry' or any(k in record for k in ('test_results', 'failures', 'status', 'reason')):
                parse_foundry(record)
                scan_format = 'foundry'
            else:
                add_finding(
                    title=record.get('title') or record.get('name') or f'finding_{index}',
                    summary=record.get('summary')
                    or record.get('description')
                    or json.dumps(record, ensure_ascii=True)[:500],
                    kind=str(record.get('kind') or 'generic'),
                    confidence=_confidence_score(record.get('confidence')),
                    severity=_impact_score(record.get('severity')),
                    evidence_ref=record.get('evidence_ref') or f'{source_path.stem}:{index}',
                    reproduction_command=record.get('reproduction_command'),
                    raw=record,
                )
    else:
        add_finding(
            title=source_path.stem,
            summary=str(payload),
            kind='generic',
            confidence=0.5,
            severity=0.5,
            evidence_ref=f'{source_path.stem}:0',
            reproduction_command=None,
            raw={'raw': payload},
        )

    if not findings:
        findings.append(
            {
                'id': f'{source_path.stem}:0',
                'title': source_path.stem,
                'summary': 'No structured findings detected in scanner input.',
                'kind': 'generic',
                'confidence': 0.25,
                'severity': 0.25,
                'evidence_ref': f'{source_path.stem}:0',
                'reproduction_command': None,
                'labels': [],
                'source_path': str(source_path),
                'raw': payload,
            }
        )
        if scan_format == 'auto':
            scan_format = 'generic'

    return {
        'source_path': str(source_path),
        'format': scan_format,
        'findings': findings,
        'finding_count': len(findings),
        'case_id': source_path.stem,
        'created_at': utc_stamp(),
        'pipeline_stats': sarif_pipeline_stats,
    }


def build_case_context(
    scan: dict[str, Any],
    *,
    subject: str = 'authorized_audit_target',
    reproduction_command: str | None = None,
) -> dict[str, Any]:
    findings = list(scan.get('findings', []))
    if findings:
        top = max(
            findings,
            key=lambda item: (
                _impact_score(item.get('severity')),
                _confidence_score(item.get('confidence')),
            ),
        )
    else:
        top = {
            'title': scan.get('case_id', 'trinity_case'),
            'summary': 'No scanner findings available.',
            'evidence_ref': 'none',
            'kind': 'generic',
            'confidence': 0.25,
            'severity': 0.25,
        }

    evidence_refs: list[str] = []
    for finding in findings:
        ref = finding.get('evidence_ref')
        if ref and ref not in evidence_refs:
            evidence_refs.append(ref)

    failure_modes = [finding.get('title') for finding in findings[:5] if finding.get('title')]
    counter_examples = [finding.get('summary') for finding in findings[1:4] if finding.get('summary')]
    reproduction = reproduction_command or top.get('reproduction_command') or scan.get('reproduction_command')

    return {
        'subject': subject,
        'claim': {
            'summary': top.get('summary') or top.get('title') or 'Trinity case',
            'scanner': scan.get('format', 'generic'),
            'source_path': scan.get('source_path'),
            'findings': findings,
            'top_finding': top,
        },
        'signals': findings,
        'evidence_refs': evidence_refs,
        'failure_modes': failure_modes,
        'counter_examples': counter_examples,
        'attack_mode': top.get('kind') or scan.get('format', 'generic'),
        'confidence': max(0.35, _confidence_score(top.get('confidence'))),
        'novelty': min(1.0, 0.25 + (len(findings) * 0.1)),
        'risk': max(0.2, _impact_score(top.get('severity'))),
        'reproduction_command': reproduction,
        'updated_weights': {
            'formal': 0.25,
            'fuzz': 0.25,
            'threat': 0.2,
            'evidence': 0.3,
        },
    }


@dataclass
class TrinityCaseLedger:
    ledger_path: Path = TRINITY_LEDGER_PATH

    def __post_init__(self) -> None:
        self.ledger_path = Path(self.ledger_path)
        self.ledger_path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, entry: dict[str, Any]) -> dict[str, Any]:
        payload = dict(entry)
        payload.setdefault('timestamp', utc_stamp())
        with self.ledger_path.open('a', encoding='utf-8') as handle:
            handle.write(json.dumps(payload, ensure_ascii=True) + '\n')
        return payload

    def recent(self, limit: int = 10) -> list[dict[str, Any]]:
        if not self.ledger_path.exists():
            return []
        entries: list[dict[str, Any]] = []
        with self.ledger_path.open('r', encoding='utf-8') as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return entries[-max(0, int(limit)) :]

    def find(self, case_id: str) -> dict[str, Any] | None:
        matches = [
            entry for entry in self.recent(10_000) if str(entry.get('case_id')) == str(case_id)
        ]
        return matches[-1] if matches else None


def default_case_dir(case_id: str) -> Path:
    return TRINITY_CASES_DIR / case_id


def resolve_case_root(case_ref: str | Path, *, ledger: TrinityCaseLedger | None = None) -> Path | None:
    candidate = Path(case_ref)
    if candidate.exists():
        return candidate

    ledger = ledger or TrinityCaseLedger()
    entry = ledger.find(str(case_ref))
    if entry:
        output_dir = entry.get('output_dir')
        if output_dir:
            output_path = Path(output_dir)
            if output_path.exists():
                return output_path

    fallback = default_case_dir(str(case_ref))
    return fallback if fallback.exists() else None


def run_case_from_scan(
    input_path: str | Path,
    *,
    format_hint: str = 'auto',
    output_dir: str | Path | None = None,
    case_id: str | None = None,
    subject: str = 'authorized_audit_target',
    reproduction_command: str | None = None,
    ledger: TrinityCaseLedger | None = None,
    write_bundle: bool = True,
) -> dict[str, Any]:
    scan = parse_scanner_input(input_path, format_hint=format_hint)
    case_id = case_id or scan['case_id']
    case_root = Path(output_dir) if output_dir else default_case_dir(case_id)

    if write_bundle:
        case_root.mkdir(parents=True, exist_ok=True)
        board_storage = case_root / 'council_evidence.jsonl'
    else:
        board_storage = None

    board = EvidenceBoard(storage_path=board_storage)
    runner = CouncilRunner(board=board)
    context = build_case_context(
        scan,
        subject=subject,
        reproduction_command=reproduction_command,
    )
    context['claim_id'] = case_id
    if write_bundle:
        context['output_dir'] = str(case_root)
        context['packet_root'] = str(case_root)
    context['claim']['case_id'] = case_id
    context['claim']['scanner_format'] = scan['format']
    context['claim']['finding_count'] = scan['finding_count']

    result = runner.run_round(context)
    packet = result.get('packet') or {}
    bundle_paths = result.get('bundle_paths') or {}
    ledger = ledger or TrinityCaseLedger()

    ledger_entry = ledger.append(
        {
            'case_id': case_id,
            'claim_id': result.get('claim_id'),
            'input_path': str(Path(input_path)),
            'scanner_format': scan['format'],
            'finding_count': scan['finding_count'],
            'status': packet.get('status'),
            'output_dir': str(case_root),
            'bundle_paths': bundle_paths,
            'bundle_written': bool(write_bundle and bundle_paths),
            'reproduction_command': packet.get('reproduction_command'),
            'created_at': packet.get('created_at') or utc_stamp(),
        }
    )

    return {
        'case_id': case_id,
        'scan': scan,
        'context': context,
        'result': result,
        'packet': packet,
        'bundle_paths': bundle_paths,
        'ledger_entry': ledger_entry,
        'output_dir': str(case_root),
        'report_path': str(case_root / 'export_report.md'),
        'bundle_written': bool(write_bundle and bundle_paths),
    }


def load_case_bundle(bundle_dir: str | Path) -> dict[str, Any]:
    root = Path(bundle_dir)
    packet_path = root / 'packet.json'
    manifest_path = root / 'manifest.json'
    claim_path = root / 'claim.json'
    rejected_path = root / 'rejected_hypotheses.json'
    report_path = root / 'export_report.md'
    reasoning_path = root / 'reasoning_summary.md'

    if packet_path.exists():
        packet = json.loads(packet_path.read_text(encoding='utf-8'))
        if isinstance(packet, dict):
            packet.setdefault('bundle_dir', str(root))
            return packet

    payload: dict[str, Any] = {'bundle_dir': str(root)}
    if manifest_path.exists():
        payload['manifest'] = json.loads(manifest_path.read_text(encoding='utf-8'))
    if claim_path.exists():
        payload['claim'] = json.loads(claim_path.read_text(encoding='utf-8'))
    if rejected_path.exists():
        payload['rejected_hypotheses'] = json.loads(rejected_path.read_text(encoding='utf-8'))
    if reasoning_path.exists():
        payload['reasoning_summary'] = reasoning_path.read_text(encoding='utf-8')
    if report_path.exists():
        payload['report'] = report_path.read_text(encoding='utf-8')
    return payload


def load_case_report(bundle_dir: str | Path) -> str:
    root = Path(bundle_dir)
    report_path = root / 'export_report.md'
    if report_path.exists():
        return report_path.read_text(encoding='utf-8')
    bundle = load_case_bundle(root)
    return str(bundle.get('report', ''))


def load_case_reproduction(bundle_dir: str | Path) -> str:
    bundle = load_case_bundle(bundle_dir)
    reproduction = bundle.get('reproduction_command')
    if reproduction:
        return str(reproduction)
    claim = bundle.get('claim') or {}
    return str(
        claim.get('reproduction_command')
        or claim.get('content', {}).get('reproduction_command')
        or ''
    )



def run_demo_case(
    *,
    output_dir: str | Path | None = None,
    ledger: TrinityCaseLedger | None = None,
    case_id: str = 'demo_reentrancy',
    subject: str = 'authorized_audit_target',
) -> dict[str, Any]:
    demo_payload = {
        'results': {
            'detectors': [
                {
                    'check': 'reentrancy',
                    'impact': 'High',
                    'confidence': 'High',
                    'description': 'Possible reentrancy path in withdraw flow',
                    'elements': [
                        {
                            'source_mapping': {
                                'filename_relative': 'contracts/DemoVault.sol',
                                'lines': [42],
                            }
                        }
                    ],
                    'reproduction_command': 'forge test --match-test testDemoReentrancy',
                }
            ]
        }
    }

    with tempfile.TemporaryDirectory(prefix='trinity_demo_input_') as tmpdir:
        demo_input = Path(tmpdir) / 'demo_slither.json'
        demo_input.write_text(json.dumps(demo_payload, indent=2), encoding='utf-8')
        demo_output_dir = Path(output_dir) if output_dir else None
        result = run_case_from_scan(
            demo_input,
            output_dir=demo_output_dir,
            case_id=case_id,
            subject=subject,
            reproduction_command='forge test --match-test testDemoReentrancy',
            ledger=ledger,
        )
    result['demo'] = True
    return result
