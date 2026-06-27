"""FastAPI surface for the Trinity evidence-packet workflow."""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Optional

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ed25519
from drift.config_adapter import (
    DATA_ROOT,
    LOGS_DIR,
    PROJECT_ROOT,
    get_anchor_knowledge_dir,
    get_anchor_vault_root,
)
from fastapi import APIRouter, FastAPI, HTTPException, Query
from fastapi.responses import PlainTextResponse, StreamingResponse
from pydantic import BaseModel, Field

from .caseflow import (
    TRINITY_CASES_DIR,
    TRINITY_LEDGER_PATH,
    TrinityCaseLedger,
    load_case_bundle,
    load_case_report,
    resolve_case_root,
    run_case_from_scan,
    run_demo_case,
    utc_stamp,
)
from .database import db as trinity_db


class TrinityAnalyzeRequest(BaseModel):
    input_path: str = Field(..., description="Path to scanner or test output.")
    format_hint: str = Field("auto", description="Scanner format hint.")
    output_dir: Optional[str] = Field(
        default=None,
        description="Directory to write the evidence bundle.",
    )
    case_id: Optional[str] = Field(
        default=None,
        description="Optional explicit Trinity case id.",
    )
    subject: str = Field(
        "authorized_audit_target",
        description="Claim subject used by the council.",
    )
    reproduction_command: Optional[str] = Field(
        default=None,
        description="Optional reproduction command to embed in the packet.",
    )
    write_bundle: bool = Field(
        True,
        description="Write the full evidence packet bundle to disk.",
    )


class TrinityDemoRequest(BaseModel):
    output_dir: Optional[str] = Field(
        default=None,
        description="Optional output directory for the demo bundle.",
    )
    case_id: str = Field(
        "demo_reentrancy",
        description="Identifier to assign to the demo case.",
    )
    subject: str = Field(
        "authorized_audit_target",
        description="Claim subject used by the council.",
    )


TRINITY_EVIDENCE_SIGNING_SECRET_PATH = Path(
    os.getenv(
        "ANCHOR_TRINITY_SIGNING_SECRET_PATH",
        str(Path.home() / ".config" / "anchor" / "trinity_evidence_signing_key"),
    )
).expanduser()


def _bootstrap_evidence_signing_key() -> tuple[ed25519.Ed25519PrivateKey, str]:
    secret_path = TRINITY_EVIDENCE_SIGNING_SECRET_PATH
    try:
        if secret_path.exists():
            raw = secret_path.read_bytes()
            if len(raw) == 32:
                return ed25519.Ed25519PrivateKey.from_private_bytes(raw), f"stored locally at {secret_path}"
        secret_path.parent.mkdir(parents=True, exist_ok=True)
        key = ed25519.Ed25519PrivateKey.generate()
        raw = key.private_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PrivateFormat.Raw,
            encryption_algorithm=serialization.NoEncryption(),
        )
        secret_path.write_bytes(raw)
        try:
            secret_path.chmod(0o600)
        except Exception:
            pass
        return key, f"generated locally at {secret_path}"
    except Exception:
        return ed25519.Ed25519PrivateKey.generate(), "in-memory fallback (no file write)"


EVIDENCE_SIGNING_KEY, EVIDENCE_SIGNING_KEY_HINT = _bootstrap_evidence_signing_key()


def _ledger() -> TrinityCaseLedger:
    return TrinityCaseLedger(TRINITY_LEDGER_PATH)


def _case_root(case_ref: str) -> Path | None:
    return resolve_case_root(case_ref, ledger=_ledger())


def _bundle_summary(bundle: dict[str, Any], case_root: Path) -> dict[str, Any]:
    claim = bundle.get("claim") or {}
    packet = bundle.get("packet") or bundle
    scan = bundle.get("scan") or {}
    return {
        "case_id": bundle.get("case_id", claim.get("id", "unknown")),
        "status": packet.get("status", bundle.get("status", "unknown")),
        "scanner_format": scan.get("format", claim.get("scanner", "unknown")),
        "finding_count": scan.get("finding_count", claim.get("finding_count", 0)),
        "claim_id": claim.get("id") or packet.get("claim", {}).get("id") or "unknown",
        "output_dir": str(case_root),
        "reproduction_command": (
            packet.get("reproduction_command")
            or bundle.get("reproduction_command")
            or claim.get("reproduction_command")
        ),
    }


def _artifact_refs(bundle: dict[str, Any], case_root: Path) -> list[str]:
    refs: list[str] = []
    bundle_paths = bundle.get("bundle_paths") or {}
    if isinstance(bundle_paths, dict):
        for value in bundle_paths.values():
            if value:
                refs.append(str(value))
    refs.append(str(case_root))
    deduped: list[str] = []
    for ref in refs:
        if ref not in deduped:
            deduped.append(ref)
    return deduped


def sign_evidence_bundle(bundle: dict[str, Any]) -> dict[str, Any]:
    canonical = json.dumps(bundle, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    digest = hashes.Hash(hashes.SHA256())
    digest.update(canonical)
    digest_hex = digest.finalize().hex()
    public_key = EVIDENCE_SIGNING_KEY.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    ).hex()
    signature_hex = EVIDENCE_SIGNING_KEY.sign(canonical).hex()
    return {
        "schema_version": "1.0",
        "kind": "anchor.evidence_bundle",
        "signed_at": utc_stamp(),
        "signing_key_id": public_key[:16],
        "public_key": public_key,
        "integrity": {
            "algorithm": "SHA-256",
            "digest": digest_hex,
        },
        "signature": {
            "algorithm": "ed25519",
            "value": signature_hex,
            "status": "SIGNED",
        },
        "bundle": bundle,
    }


def _build_case_events(run_id: str, bundle: dict[str, Any], case_root: Path) -> list[dict[str, Any]]:
    packet = bundle.get("packet") or bundle
    claim = bundle.get("claim") or packet.get("claim") or {}
    scan = bundle.get("scan") or {}
    created_at = packet.get("created_at") or bundle.get("created_at") or utc_stamp()
    artifact_refs = _artifact_refs(bundle, case_root)
    schema_version = "1.0"
    case_id = str(bundle.get("case_id") or claim.get("id") or run_id)
    events: list[dict[str, Any]] = []

    events.append(
        {
            "schema_version": schema_version,
            "run_id": str(run_id),
            "case_id": case_id,
            "event_type": "run.started",
            "timestamp": created_at,
            "artifact_refs": artifact_refs,
            "summary": claim.get("summary") or packet.get("summary") or packet.get("status") or "run started",
        }
    )
    events.append(
        {
            "schema_version": schema_version,
            "run_id": str(run_id),
            "case_id": case_id,
            "event_type": "case.started",
            "timestamp": created_at,
            "artifact_refs": artifact_refs,
            "scanner_format": scan.get("format", claim.get("scanner", "unknown")),
            "finding_count": int(scan.get("finding_count", claim.get("finding_count", 0))),
        }
    )

    findings = list(scan.get("findings") or claim.get("findings") or [])
    if findings:
        for finding in findings:
            events.append(
                {
                    "schema_version": schema_version,
                    "run_id": str(run_id),
                    "case_id": case_id,
                    "event_type": "finding.detected",
                    "timestamp": finding.get("timestamp") or created_at,
                    "artifact_refs": artifact_refs,
                    "finding_id": finding.get("id") or finding.get("evidence_ref"),
                    "title": finding.get("title") or finding.get("summary"),
                    "severity": finding.get("severity"),
                }
            )

    messages = packet.get("messages") or []
    for message in messages:
        message_type = str(message.get("message_type", "") or message.get("type", "")).lower()
        if message_type in {"accept", "challenge", "evidence_request", "reject"}:
            events.append(
                {
                    "schema_version": schema_version,
                    "run_id": str(run_id),
                    "case_id": case_id,
                    "event_type": "finding.correlated",
                    "timestamp": message.get("timestamp") or created_at,
                    "artifact_refs": artifact_refs,
                    "message_type": message_type,
                    "message_id": message.get("id") or message.get("message_id"),
                }
            )

    events.append(
        {
            "schema_version": schema_version,
            "run_id": str(run_id),
            "case_id": case_id,
            "event_type": "poc.result",
            "timestamp": packet.get("updated_at") or created_at,
            "artifact_refs": artifact_refs,
            "status": packet.get("status", bundle.get("status", "unknown")),
            "reproduction_command": packet.get("reproduction_command") or claim.get("reproduction_command"),
        }
    )
    events.append(
        {
            "schema_version": schema_version,
            "run_id": str(run_id),
            "case_id": case_id,
            "event_type": "case.completed",
            "timestamp": packet.get("updated_at") or created_at,
            "artifact_refs": artifact_refs,
            "output_dir": str(case_root),
            "reproduced": packet.get("status") == "REPRODUCED_REAL",
        }
    )
    return events


def _run_council_counts(bundle: dict[str, Any]) -> dict[str, int]:
    packet = bundle.get("packet") or bundle
    messages = packet.get("messages") or bundle.get("messages") or []
    accepted = 0
    rejected = 0
    for message in messages:
        message_type = str(message.get("message_type", "")).lower()
        if message_type == "accept":
            accepted += 1
        elif message_type in {"challenge", "evidence_request", "reject"}:
            rejected += 1
    return {
        "accepted": accepted,
        "rejected": rejected,
        "messages": len(messages),
    }


def _run_history_entry(entry: dict[str, Any]) -> dict[str, Any] | None:
    output_dir = entry.get("output_dir")
    if not output_dir:
        return None
    case_root = Path(output_dir)
    if not case_root.exists():
        return None

    bundle = load_case_bundle(case_root)
    packet = bundle.get("packet") or bundle
    claim = bundle.get("claim") or packet.get("claim") or {}
    scan = bundle.get("scan") or {}
    counts = _run_council_counts(bundle)
    reproduction_status = str(claim.get("reproduction_status") or "unattempted")
    reproduced = packet.get("status") == "REPRODUCED_REAL" or reproduction_status in {
        "reproduced",
        "confirmed",
    }
    return {
        "case_id": str(entry.get("case_id") or bundle.get("case_id") or claim.get("id") or case_root.name),
        "timestamp": entry.get("created_at") or packet.get("created_at") or bundle.get("created_at"),
        "status": packet.get("status", entry.get("status", "unknown")),
        "scanner_format": entry.get("scanner_format") or scan.get("format", claim.get("scanner", "unknown")),
        "finding_count": int(entry.get("finding_count", scan.get("finding_count", claim.get("finding_count", 0)))),
        "accepted_count": counts["accepted"],
        "rejected_count": counts["rejected"],
        "message_count": counts["messages"],
        "reproduced": reproduced,
        "reproduction_status": reproduction_status,
        "reproduction_command": packet.get("reproduction_command") or bundle.get("reproduction_command") or claim.get("reproduction_command"),
        "output_dir": str(case_root),
    }


def _anchor_vault_root() -> Path:
    vault = get_anchor_vault_root()
    if vault is not None:
        return vault
    return DATA_ROOT / "AnchorVault"


def _vault_briefs_dir(vault_root: Path) -> Path:
    """Daily briefs: prefer news/briefs, fall back to hunt_briefs."""
    news = vault_root / "news" / "briefs"
    if news.is_dir() and any(news.iterdir()):
        return news
    return vault_root / "hunt_briefs"


def _count_files(path: Path) -> int:
    if not path.exists():
        return 0
    if path.is_file():
        return 1
    return sum(1 for child in path.rglob("*") if child.is_file())


def _count_jsonl_records(path: Path) -> int:
    if not path.exists():
        return 0
    if path.is_file():
        try:
            return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())
        except Exception:
            return 0
    total = 0
    for child in path.rglob("*.jsonl"):
        try:
            total += sum(1 for line in child.read_text(encoding="utf-8").splitlines() if line.strip())
        except Exception:
            continue
    if total:
        return total
    return _count_files(path)


def _latest_file(path: Path) -> Path | None:
    if not path.exists():
        return None
    candidates = [child for child in path.rglob("*") if child.is_file()]
    if not candidates:
        return None
    return max(candidates, key=lambda item: item.stat().st_mtime)


def _latest_daily_brief(path: Path) -> tuple[str | None, int | None]:
    latest = _latest_file(path)
    if latest is None:
        return None, None
    brief_date = datetime.fromtimestamp(latest.stat().st_mtime, UTC).date()
    age_days = (datetime.now(UTC).date() - brief_date).days
    return brief_date.isoformat(), age_days


def _vault_freshness_label(age_days: int | None) -> str:
    if age_days is None:
        return 'No daily brief'
    if age_days <= 1:
        return 'Fresh'
    return f'{age_days} days stale'


def _github_contribution_snapshot() -> dict[str, Any]:
    if shutil.which('gh') is None:
        return {
            'source': 'unavailable',
            'repo': None,
            'open_prs': 0,
            'merged_prs': 0,
            'issues_filed': 0,
            'highlights': [],
        }

    def _list(command: list[str]) -> list[dict[str, Any]]:
        result = subprocess.run(
            command,
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            check=False,
            timeout=12,
        )
        if result.returncode != 0:
            return []
        try:
            payload = json.loads(result.stdout or '[]')
        except Exception:
            return []
        return payload if isinstance(payload, list) else []

    open_prs = _list(['gh', 'pr', 'list', '--state', 'open', '--limit', '100', '--json', 'number,title,url'])
    merged_prs = _list(['gh', 'pr', 'list', '--state', 'merged', '--limit', '100', '--json', 'number,title,url'])
    issues = _list(['gh', 'issue', 'list', '--state', 'open', '--limit', '100', '--json', 'number,title,url'])
    repo = None
    try:
        remote = subprocess.run(
            ['git', 'remote', 'get-url', 'origin'],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
        remote_url = remote.stdout.strip()
        if remote_url.endswith('.git'):
            remote_url = remote_url[:-4]
        if 'github.com/' in remote_url:
            repo = remote_url.split('github.com/', 1)[1].strip('/')
    except Exception:
        repo = None
    return {
        'source': 'github_cli',
        'repo': repo,
        'open_prs': len(open_prs),
        'merged_prs': len(merged_prs),
        'issues_filed': len(issues),
        'highlights': {
            'open_prs': open_prs[:3],
            'merged_prs': merged_prs[:3],
            'issues': issues[:3],
        },
    }


def get_trinity_history_snapshot(limit: int = 5) -> dict[str, Any]:
    entries = list(reversed(_ledger().recent(limit)))
    runs = [run for entry in entries if (run := _run_history_entry(entry)) is not None]
    accepted_total = sum(run['accepted_count'] for run in runs)
    rejected_total = sum(run['rejected_count'] for run in runs)
    reproduced_total = sum(1 for run in runs if run['reproduced'])
    return {
        'count': len(runs),
        'accepted_total': accepted_total,
        'rejected_total': rejected_total,
        'reproduced_total': reproduced_total,
        'runs': runs,
    }


def get_trinity_metrics_snapshot() -> dict[str, Any]:
    entries = list(reversed(_ledger().recent(10000)))
    runs = [run for entry in entries if (run := _run_history_entry(entry)) is not None]
    claims_generated = len(runs)
    claims_accepted = sum(run['accepted_count'] for run in runs)
    claims_rejected = sum(run['rejected_count'] for run in runs)
    reproduced_runs = sum(1 for run in runs if run['reproduced'])
    findings_total = trinity_db.count_findings()
    verified_findings = len(trinity_db.get_findings(reproduced=True))
    latest_benchmark = trinity_db.get_latest_benchmark()
    reproduction_rate = round(reproduced_runs / claims_generated, 4) if claims_generated else 0.0
    return {
        'claims_generated': claims_generated,
        'claims_accepted': claims_accepted,
        'claims_rejected': claims_rejected,
        'reproduced_runs': reproduced_runs,
        'reproduction_rate': reproduction_rate,
        'verified_findings': verified_findings,
        'findings_total': findings_total,
        'latest_benchmark': latest_benchmark,
        'latest_run': runs[0] if runs else None,
    }


def get_trinity_vault_snapshot() -> dict[str, Any]:
    vault_root = _anchor_vault_root()
    news_briefs_dir = _vault_briefs_dir(vault_root)
    news_snapshots_dir = vault_root / 'news' / 'snapshots'
    claims_dir = vault_root / 'claims'
    triage_templates_dir = vault_root / 'triage_templates'
    decision_trees_dir = vault_root / 'decision_trees'
    knowledge_dir = get_anchor_knowledge_dir() or (vault_root / 'knowledge')
    history_dir = vault_root.parent / 'Anchor' / 'history'
    brief_date, age_days = _latest_daily_brief(news_briefs_dir)
    status = 'ready' if vault_root.exists() else 'missing'
    knowledge_files = _count_files(knowledge_dir) if knowledge_dir.exists() else 0
    return {
        'vault_root': str(vault_root),
        'knowledge_root': str(knowledge_dir) if knowledge_dir.exists() else None,
        'knowledge_files': knowledge_files,
        'knowledge_source': 'anchor_vault' if knowledge_dir.exists() else 'local',
        'news_briefs': _count_files(news_briefs_dir),
        'news_snapshots': _count_files(news_snapshots_dir),
        'history_records': _count_jsonl_records(history_dir),
        'bug_classes': _count_files(claims_dir),
        'triage_templates': _count_files(triage_templates_dir),
        'decision_trees': _count_files(decision_trees_dir),
        'last_daily_brief': brief_date,
        'vault_freshness_days': age_days,
        'vault_status_label': _vault_freshness_label(age_days),
        'status': status,
    }


def get_trinity_contributions_snapshot() -> dict[str, Any]:
    snapshot = _github_contribution_snapshot()
    return {
        **snapshot,
        'tracked_at': datetime.now(UTC).isoformat().replace('+00:00', 'Z'),
    }


def get_trinity_paths_snapshot() -> dict[str, str]:
    from drift.core.anchor_context import get_anchor_runtime

    paths = {
        'cases_dir': str(TRINITY_CASES_DIR),
        'ledger_path': str(TRINITY_LEDGER_PATH),
        'database_path': str(trinity_db.db_path),
        'logs_dir': str(LOGS_DIR),
    }
    anchor = get_anchor_runtime()
    if anchor.get("vault_root"):
        paths["vault_root"] = anchor["vault_root"]
    if anchor.get("knowledge_root"):
        paths["knowledge_root"] = anchor["knowledge_root"]
    if anchor.get("knowledge_chroma_dir"):
        paths["knowledge_chroma_dir"] = anchor["knowledge_chroma_dir"]
    if anchor.get("anchor_data_root"):
        paths["anchor_data_root"] = anchor["anchor_data_root"]
    return paths


def build_trinity_snapshot(limit: int = 5) -> dict[str, Any]:
    return {
        'history': get_trinity_history_snapshot(limit=limit),
        'metrics': get_trinity_metrics_snapshot(),
        'vault': get_trinity_vault_snapshot(),
        'contributions': get_trinity_contributions_snapshot(),
        'paths': get_trinity_paths_snapshot(),
    }


def build_trinity_router() -> APIRouter:
    router = APIRouter(prefix="/api/trinity", tags=["trinity"])

    @router.get("/health")
    async def health() -> dict[str, Any]:
        recent_cases = _ledger().recent(1)
        latest_benchmark = trinity_db.get_latest_benchmark()
        findings = trinity_db.get_findings()
        return {
            "status": "ok",
            "cases_dir": str(TRINITY_CASES_DIR),
            "ledger_path": str(TRINITY_LEDGER_PATH),
            "recent_case": recent_cases[0] if recent_cases else None,
            "latest_benchmark": latest_benchmark,
            "stored_findings": trinity_db.count_findings(),
        }

    @router.post("/analyze")
    async def analyze(request: TrinityAnalyzeRequest) -> dict[str, Any]:
        input_path = Path(request.input_path).expanduser()
        if not input_path.exists():
            raise HTTPException(status_code=404, detail=f"Input file not found: {input_path}")

        try:
            result = await asyncio.to_thread(
                run_case_from_scan,
                input_path,
                format_hint=request.format_hint,
                output_dir=request.output_dir,
                case_id=request.case_id,
                subject=request.subject,
                reproduction_command=request.reproduction_command,
                ledger=_ledger(),
                write_bundle=request.write_bundle,
            )
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

        return result

    @router.post("/demo")
    async def demo(request: TrinityDemoRequest) -> dict[str, Any]:
        try:
            result = await asyncio.to_thread(
                run_demo_case,
                output_dir=request.output_dir,
                ledger=_ledger(),
                case_id=request.case_id,
                subject=request.subject,
            )
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

        return result

    @router.get("/cases")
    async def cases(limit: int = Query(20, ge=1, le=100)) -> dict[str, Any]:
        entries = _ledger().recent(limit)
        return {"cases": entries, "count": len(entries)}

    @router.get("/history")
    async def history(limit: int = Query(5, ge=1, le=20)) -> dict[str, Any]:
        return get_trinity_history_snapshot(limit=limit)

    @router.get("/metrics")
    async def metrics() -> dict[str, Any]:
        return get_trinity_metrics_snapshot()

    @router.get("/vault")
    async def vault() -> dict[str, Any]:
        return get_trinity_vault_snapshot()

    @router.get("/contributions")
    async def contributions() -> dict[str, Any]:
        return get_trinity_contributions_snapshot()

    @router.get("/cases/{case_ref}")
    async def case_bundle(case_ref: str) -> dict[str, Any]:
        case_root = _case_root(case_ref)
        if case_root is None:
            raise HTTPException(status_code=404, detail=f"Case not found: {case_ref}")
        return load_case_bundle(case_root)

    @router.get("/cases/{case_ref}/summary")
    async def case_summary(case_ref: str) -> dict[str, Any]:
        case_root = _case_root(case_ref)
        if case_root is None:
            raise HTTPException(status_code=404, detail=f"Case not found: {case_ref}")
        bundle = load_case_bundle(case_root)
        return _bundle_summary(bundle, case_root)

    @router.get("/cases/{case_ref}/report")
    async def case_report(case_ref: str) -> PlainTextResponse:
        case_root = _case_root(case_ref)
        if case_root is None:
            raise HTTPException(status_code=404, detail=f"Case not found: {case_ref}")
        return PlainTextResponse(load_case_report(case_root))

    @router.get("/cases/{case_ref}/packet")
    async def case_packet(case_ref: str) -> dict[str, Any]:
        case_root = _case_root(case_ref)
        if case_root is None:
            raise HTTPException(status_code=404, detail=f"Case not found: {case_ref}")
        bundle = load_case_bundle(case_root)
        return bundle.get("packet") or bundle

    @router.get("/ledger/{case_ref}")
    async def ledger_entry(case_ref: str) -> dict[str, Any]:
        entry = _ledger().find(case_ref)
        if entry is None:
            raise HTTPException(status_code=404, detail=f"Ledger entry not found: {case_ref}")
        return entry

    @router.get("/findings")
    async def findings(
        tier: Optional[str] = None,
        reproduced: Optional[bool] = None,
    ) -> dict[str, Any]:
        rows = trinity_db.get_findings(tier=tier, reproduced=reproduced)
        return {"findings": rows, "count": len(rows)}

    @router.get("/benchmarks/latest")
    async def latest_benchmark() -> dict[str, Any]:
        benchmark = trinity_db.get_latest_benchmark()
        if benchmark is None:
            raise HTTPException(status_code=404, detail="No benchmark runs recorded yet")
        return benchmark

    @router.get("/audit")
    async def audit(limit: int = Query(50, ge=1, le=500)) -> dict[str, Any]:
        rows = trinity_db.get_audit_entries(limit=limit)
        return {"events": rows, "count": len(rows)}

    @router.get("/paths")
    async def paths() -> dict[str, str]:
        return get_trinity_paths_snapshot()

    @router.get("/runs/{run_id}/events")
    async def run_events(run_id: str) -> StreamingResponse:
        case_root = _case_root(run_id)
        if case_root is None:
            raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")
        bundle = load_case_bundle(case_root)
        events = _build_case_events(run_id, bundle, case_root)

        async def event_stream():
            for event in events:
                yield f"data: {json.dumps(event, ensure_ascii=True)}\n\n"
                await asyncio.sleep(0)

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    return router


def build_trinity_app() -> FastAPI:
    app = FastAPI(title="Trinity Evidence API")
    app.include_router(build_trinity_router())
    return app


app = build_trinity_app()

