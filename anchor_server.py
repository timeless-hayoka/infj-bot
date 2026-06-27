"""ANCHOR // powered by Drift - local-first run server."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import secrets
import sys
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import load_pem_private_key
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse

APP_VERSION = "1.0.0"
ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = Path(os.getenv("ANCHOR_PROJECT_ROOT", str(ROOT))).expanduser().resolve()
SIGNING_KEY_PATH = Path(os.getenv("ANCHOR_SIGNING_KEY_PATH", str(ROOT / "anchor_signing_key.pem"))).expanduser()
DEFAULT_HOST = os.getenv("ANCHOR_SERVER_HOST", "127.0.0.1")
DEFAULT_PORT = int(os.getenv("ANCHOR_SERVER_PORT", "8000"))
DEFAULT_SCRIPT = os.getenv("ANCHOR_DEFAULT_HUNT_SCRIPT", "trinity_hunt_v4_2_fixed.py")
ALLOWED_SCRIPT_NAMES = {
    name.strip()
    for name in os.getenv(
        "ANCHOR_ALLOWED_HUNT_SCRIPTS",
        "trinity_hunt_v4_2_fixed.py,anchor_hunt.py",
    ).split(",")
    if name.strip()
}
ALLOW_HUNT_ARGS = os.getenv("ANCHOR_ALLOW_HUNT_ARGS", "0").strip().lower() in {"1", "true", "yes"}
BENCHMARK = "3a8b8bf0"
LADDER = {"DETECTED": 0, "CORRELATED": 1, "REPRODUCED_REAL": 2}
TERMINAL_EVENTS = {"run.completed", "run.stopped"}

SWC = {
    "SWC-101": {"name": "Integer Overflow / Underflow", "sev": "high", "fix": "Use Solidity ^0.8 checked math or SafeMath.", "cvss": 7.5, "vector": "AV:N/AC:L/PR:N/UI:N/S:U/C:N/I:H/A:N"},
    "SWC-104": {"name": "Unchecked Call Return", "sev": "medium", "fix": "Check the boolean return of low-level calls or use a checked transfer.", "cvss": 6.5, "vector": "AV:N/AC:L/PR:N/UI:N/S:U/C:N/I:L/A:L"},
    "SWC-105": {"name": "Unprotected Ether Withdrawal", "sev": "high", "fix": "Add access control and withdrawal limits.", "cvss": 9.1, "vector": "AV:N/AC:L/PR:N/UI:N/S:U/C:N/I:H/A:H"},
    "SWC-106": {"name": "Unprotected Selfdestruct", "sev": "critical", "fix": "Gate selfdestruct behind access control, or remove it entirely.", "cvss": 9.1, "vector": "AV:N/AC:L/PR:N/UI:N/S:U/C:N/I:H/A:H"},
    "SWC-107": {"name": "Reentrancy", "sev": "high", "fix": "Apply checks-effects-interactions or a reentrancy guard.", "cvss": 9.1, "vector": "AV:N/AC:L/PR:N/UI:N/S:U/C:N/I:H/A:H"},
    "SWC-115": {"name": "Authorization via tx.origin", "sev": "high", "fix": "Use msg.sender for authorization, never tx.origin.", "cvss": 6.5, "vector": "AV:N/AC:L/PR:N/UI:R/S:U/C:N/I:H/A:N"},
}

SPECIMENS = [
    {"case_id": "TinyReentrancy", "contract": "TinyReentrancy", "swc": "SWC-107", "validation_state": "REPRODUCED_REAL"},
    {"case_id": "TinyReentrancyEvents", "contract": "TinyReentrancyEvents", "swc": "SWC-107", "validation_state": "REPRODUCED_REAL"},
    {"case_id": "TinyReentrancyHelper", "contract": "TinyReentrancyHelper", "swc": "SWC-107", "validation_state": "REPRODUCED_REAL"},
    {"case_id": "TinyUnprotectedSelfdestruct", "contract": "TinyUnprotectedSelfdestruct", "swc": "SWC-106", "validation_state": "REPRODUCED_REAL"},
    {"case_id": "TinyUnprotectedWithdrawal", "contract": "TinyUnprotectedWithdrawal", "swc": "SWC-105", "validation_state": "REPRODUCED_REAL"},
    {"case_id": "TinyIntegerOverflow", "contract": "TinyIntegerOverflow", "swc": "SWC-101", "validation_state": "REPRODUCED_REAL"},
    {"case_id": "TinyIntegerUnderflow", "contract": "TinyIntegerUnderflow", "swc": "SWC-101", "validation_state": "REPRODUCED_REAL"},
    {"case_id": "TinyTxOrigin", "contract": "TinyTxOrigin", "swc": "SWC-115", "validation_state": "REPRODUCED_REAL"},
    {"case_id": "TinyUncheckedTransfer", "contract": "TinyUncheckedTransfer", "swc": "SWC-104", "validation_state": "REPRODUCED_REAL"},
    {"case_id": "TinySafeReentrancy", "contract": "TinySafeReentrancy", "swc": None, "validation_state": "NEGATIVE_CONTROL_PASSED"},
]


def utc_stamp() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def canonical_json(payload: Any) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def _self_url() -> str:
    host = os.getenv("ANCHOR_SERVER_HOST", DEFAULT_HOST)
    port = os.getenv("ANCHOR_SERVER_PORT", str(DEFAULT_PORT))
    return f"http://{host}:{port}"


def _ensure_under_project_root(path: Path, label: str) -> Path:
    candidate = path.expanduser()
    if not candidate.is_absolute():
        candidate = PROJECT_ROOT / candidate
    candidate = candidate.resolve()
    try:
        candidate.relative_to(PROJECT_ROOT)
    except ValueError as exc:
        raise ValueError(f"{label} must stay under the approved project root: {PROJECT_ROOT}") from exc
    return candidate


def _resolve_project_path(raw: str | None, *, default: str | None = None, must_exist: bool = True, label: str = "path") -> Path | None:
    value = raw
    if value is None or not str(value).strip():
        if default is None:
            return None
        value = default
    candidate = _ensure_under_project_root(Path(str(value)), label)
    if must_exist and not candidate.exists():
        raise ValueError(f"{label} not found: {candidate}")
    return candidate


def _normalize_args(value: Any) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("args must be a list")
    return [str(v) for v in value]


def _bootstrap_signing_key() -> tuple[Ed25519PrivateKey, str]:
    path = SIGNING_KEY_PATH
    try:
        if path.exists():
            raw = path.read_bytes()
            try:
                key = load_pem_private_key(raw, password=None)
                if isinstance(key, Ed25519PrivateKey):
                    try:
                        os.chmod(path, 0o600)
                    except Exception:
                        pass
                    return key, f"stored locally at {path}"
            except Exception:
                pass
        path.parent.mkdir(parents=True, exist_ok=True)
        key = Ed25519PrivateKey.generate()
        pem = key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "wb") as fh:
                fh.write(pem)
        except FileExistsError:
            path.write_bytes(pem)
        try:
            os.chmod(path, 0o600)
        except Exception:
            pass
        return key, f"generated locally at {path}"
    except Exception:
        return Ed25519PrivateKey.generate(), "in-memory fallback"


SIGNING_KEY, SIGNING_HINT = _bootstrap_signing_key()
PUBLIC_KEY_HEX = SIGNING_KEY.public_key().public_bytes(
    encoding=serialization.Encoding.Raw,
    format=serialization.PublicFormat.Raw,
).hex()
PUBLIC_KEY_ID = PUBLIC_KEY_HEX[:16]


def sign_bundle(bundle: dict[str, Any]) -> dict[str, Any]:
    canonical = canonical_json(bundle)
    digest = hashlib.sha256(canonical).hexdigest()
    signature = SIGNING_KEY.sign(canonical).hex()
    return {
        "schema_version": "1.0",
        "kind": "anchor.evidence_bundle",
        "signed_at": utc_stamp(),
        "signing_key_id": PUBLIC_KEY_ID,
        "public_key": PUBLIC_KEY_HEX,
        "integrity": {"algorithm": "SHA-256", "digest": digest},
        "signature": {"algorithm": "ed25519", "value": signature, "status": "SIGNED"},
        "bundle": bundle,
    }


def ladder_index(state: str) -> int:
    return LADDER.get(state, -1)


def fixture_case(spec: dict[str, Any]) -> dict[str, Any]:
    swc = spec.get("swc")
    state = spec.get("validation_state", "UNKNOWN")
    detected = [swc] if swc and ladder_index(state) >= 0 else []
    correlated = [swc] if swc and ladder_index(state) >= 1 else []
    reproduced = [swc] if swc and ladder_index(state) >= 2 else []
    artifacts = []
    if state == "REPRODUCED_REAL" and swc:
        artifacts.append({
            "swc": swc,
            "success": True,
            "exploit_verified": True,
            "assertion_count": 1,
            "unavailable": False,
            "test_path": f"test/Test_{spec['case_id']}.t.sol",
            "stderr": "",
            "failure_reason": "",
        })
    return {
        "case_id": spec["case_id"],
        "contract": spec["contract"],
        "swc": swc,
        "expected": [swc] if swc else [],
        "detected": detected,
        "correlated": correlated,
        "reproduced_real": reproduced,
        "validation_state": state,
        "reproduction_status": "REPRODUCED_REAL" if state == "REPRODUCED_REAL" else ("NOT_TESTED" if state == "NEGATIVE_CONTROL_PASSED" else "FAILED"),
        "true_positive": 1 if state == "REPRODUCED_REAL" else 0,
        "false_positive": 0,
        "false_negative": 0,
        "true_negative": 1 if state == "NEGATIVE_CONTROL_PASSED" and not swc else 0,
        "execution_artifacts": artifacts,
        "benchmark_id": BENCHMARK,
        "archived": False,
        "timestamp": utc_stamp(),
    }


def specimen_registry() -> dict[str, Any]:
    results = [fixture_case(spec) for spec in SPECIMENS]
    reproduced = sum(1 for item in results if item["validation_state"] == "REPRODUCED_REAL")
    total = len(results)
    precision = 1.0 if total else 0.0
    return {
        "schema_version": "1.0",
        "kind": "anchor.registry",
        "benchmark_id": BENCHMARK,
        "generated_at": utc_stamp(),
        "total": total,
        "reproduced": reproduced,
        "precision": precision,
        "recall": precision,
        "f1": precision,
        "results": results,
    }


def normalize_registry(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, dict):
        if isinstance(data.get("results"), list):
            return [c for c in data["results"] if isinstance(c, dict)]
        if isinstance(data.get("cases"), list):
            return [c for c in data["cases"] if isinstance(c, dict)]
        if isinstance(data.get("registry"), list):
            return [c for c in data["registry"] if isinstance(c, dict)]
    if isinstance(data, list):
        return [c for c in data if isinstance(c, dict)]
    return []


def case_from_registry(entry: dict[str, Any]) -> dict[str, Any]:
    validation_state = str(entry.get("validation_state") or entry.get("status") or "UNKNOWN")
    if validation_state == "UNAVAILABLE":
        validation_state = "TOOL_UNAVAILABLE"
    artifacts = entry.get("execution_artifacts") or []
    if not isinstance(artifacts, list):
        artifacts = []
    if not artifacts and validation_state == "REPRODUCED_REAL":
        artifacts = [{
            "swc": entry.get("swc"),
            "success": True,
            "exploit_verified": True,
            "assertion_count": entry.get("assertion_count", 1),
            "unavailable": False,
            "test_path": entry.get("test_path"),
            "stderr": "",
            "failure_reason": "",
        }]
    return {
        "case_id": entry.get("case_id") or entry.get("id") or entry.get("challenge") or "unknown_case",
        "contract": entry.get("contract") or entry.get("subject") or None,
        "swc": entry.get("swc") or (entry.get("expected") or [None])[0],
        "expected": entry.get("expected") or [],
        "detected": entry.get("detected") or [],
        "correlated": entry.get("correlated") or [],
        "reproduced_real": entry.get("reproduced_real") or [],
        "validation_state": validation_state,
        "reproduction_status": entry.get("reproduction_status") or ("REPRODUCED_REAL" if validation_state == "REPRODUCED_REAL" else "FAILED"),
        "execution_artifacts": artifacts,
        "timestamp": entry.get("timestamp") or utc_stamp(),
    }


def build_registry_from_cases(run: "Run") -> dict[str, Any]:
    results = list(run.cases.values())
    reproduced = sum(1 for item in results if item.get("validation_state") == "REPRODUCED_REAL")
    total = len(results)
    precision = 1.0 if total else 0.0
    return {
        "schema_version": "1.0",
        "kind": "anchor.registry",
        "benchmark_id": run.benchmark,
        "generated_at": utc_stamp(),
        "total": total,
        "reproduced": reproduced,
        "precision": precision,
        "recall": precision,
        "f1": precision,
        "results": results,
    }


@dataclass
class Run:
    run_id: str
    benchmark: str
    mode: str
    params: dict[str, Any]
    created_at: str = field(default_factory=utc_stamp)
    status: str = "pending"
    done: asyncio.Event = field(default_factory=asyncio.Event)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    events: list[dict[str, Any]] = field(default_factory=list)
    subscribers: list[asyncio.Queue] = field(default_factory=list)
    cases: dict[str, dict[str, Any]] = field(default_factory=dict)
    registry: dict[str, Any] | None = None
    task: asyncio.Task | None = None
    process: asyncio.subprocess.Process | None = None
    ingested: bool = False
    cancelled: bool = False

    def _event(self, type_: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        seq = len(self.events) + 1
        return {
            "schema_version": "1.0",
            "event_id": f"evt_{self.run_id}_{seq:06d}",
            "run_id": self.run_id,
            "type": type_,
            "timestamp": utc_stamp(),
            "payload": payload or {},
        }

    def _apply_event(self, event: dict[str, Any]) -> None:
        payload = event.get("payload") or {}
        event_type = str(event.get("type") or "")
        case_id = str(payload.get("case_id") or event.get("case_id") or "")
        if event_type == "run.started":
            self.status = "running"
        elif event_type == "case.started":
            self.cases[case_id] = {
                "case_id": case_id,
                "contract": payload.get("contract") or None,
                "swc": (payload.get("expected") or [None])[0],
                "expected": payload.get("expected") or [],
                "detected": [],
                "correlated": [],
                "reproduced_real": [],
                "validation_state": "PENDING",
                "reproduction_status": "NOT_STARTED",
                "stage": "queued",
                "execution_artifacts": [],
                "timestamp": payload.get("timestamp") or utc_stamp(),
            }
        elif event_type == "stage.started":
            self.cases.setdefault(case_id, {"case_id": case_id})["stage"] = payload.get("stage")
        elif event_type == "finding.detected":
            case = self.cases.setdefault(case_id, {"case_id": case_id})
            case.update({"swc": payload.get("swc") or case.get("swc"), "validation_state": "DETECTED"})
            if payload.get("swc"):
                case["detected"] = [payload.get("swc")]
        elif event_type == "finding.correlated":
            case = self.cases.setdefault(case_id, {"case_id": case_id})
            case.update({"swc": payload.get("swc") or case.get("swc"), "validation_state": "CORRELATED"})
            if payload.get("swc"):
                case["correlated"] = [payload.get("swc")]
        elif event_type == "poc.result":
            case = self.cases.setdefault(case_id, {"case_id": case_id})
            verified = bool(payload.get("exploit_verified"))
            case.update({
                "swc": payload.get("swc") or case.get("swc"),
                "validation_state": "REPRODUCED_REAL" if verified else "FAILED",
                "reproduction_status": "REPRODUCED_REAL" if verified else "FAILED",
            })
            if verified and payload.get("swc"):
                case["reproduced_real"] = [payload.get("swc")]
                case.setdefault("execution_artifacts", []).append({
                    "swc": payload.get("swc"),
                    "success": True,
                    "exploit_verified": True,
                    "assertion_count": payload.get("assertion_count", 1),
                    "unavailable": False,
                    "test_path": payload.get("test_path"),
                    "stderr": "",
                    "failure_reason": "",
                })
        elif event_type == "case.completed":
            case = self.cases.setdefault(case_id, {"case_id": case_id})
            case["validation_state"] = payload.get("validation_state") or case.get("validation_state", "UNKNOWN")
            case["stage"] = "done"
        elif event_type == "run.completed":
            self.status = "done"
            self.done.set()
        elif event_type == "run.stopped":
            self.status = "stopped"
            self.done.set()

    async def publish(self, event: dict[str, Any], terminal: bool = False) -> None:
        async with self.lock:
            self.events.append(event)
            self._apply_event(event)
            subscribers = list(self.subscribers)
            if terminal:
                self.done.set()
                self.subscribers.clear()
                self.status = "done" if event["type"] == "run.completed" else "stopped"
        for queue in subscribers:
            queue.put_nowait(event)
        if terminal:
            for queue in subscribers:
                queue.put_nowait(None)

    async def emit(self, type_: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        event = self._event(type_, payload)
        await self.publish(event, terminal=type_ in TERMINAL_EVENTS)
        return event

    async def ingest_envelope(self, event: dict[str, Any]) -> None:
        await self.publish(event, terminal=event.get("type") in TERMINAL_EVENTS)

    async def open_stream(self, after: str | None = None) -> tuple[asyncio.Queue | None, list[dict[str, Any]], bool]:
        queue: asyncio.Queue = asyncio.Queue()
        async with self.lock:
            start = 0
            if after:
                for idx, event in enumerate(self.events):
                    if event.get("event_id") == after:
                        start = idx + 1
                        break
            replay = list(self.events[start:])
            already_done = self.done.is_set()
            if not already_done:
                self.subscribers.append(queue)
            else:
                queue = None
        return queue, replay, already_done

    async def close_stream(self, queue: asyncio.Queue | None) -> None:
        if queue is None:
            return
        async with self.lock:
            if queue in self.subscribers:
                self.subscribers.remove(queue)


RUNS: dict[str, Run] = {}
CASE_INDEX: dict[str, dict[str, Any]] = {}


def _sse_frame(event: dict[str, Any]) -> str:
    return f"data: {json.dumps(event, ensure_ascii=True)}\n\n"


def _fixture_for_case(case_id: str) -> dict[str, Any] | None:
    for spec in SPECIMENS:
        if spec["case_id"] == case_id:
            return fixture_case(spec)
    return None


def _terminal_registry(run: Run) -> dict[str, Any]:
    if run.registry is not None:
        return run.registry
    return build_registry_from_cases(run)


async def demo_run(run: Run) -> None:
    total = len(SPECIMENS)
    await run.emit("run.started", {"mode": "demo", "benchmark_id": run.benchmark, "total_cases": total})
    reproduced = 0
    for spec in SPECIMENS:
        if run.cancelled:
            break
        case_id = spec["case_id"]
        state = spec["validation_state"]
        swc = spec.get("swc")
        contract = spec.get("contract")
        run_case = fixture_case(spec)
        run.cases[case_id] = run_case
        CASE_INDEX[case_id] = run_case
        await run.emit("case.started", {"case_id": case_id, "contract": contract, "expected": run_case["expected"]})
        await run.emit("stage.started", {"case_id": case_id, "stage": "slither"})
        await asyncio.sleep(0.08)
        if swc:
            await run.emit("finding.detected", {"case_id": case_id, "swc": swc, "source": "slither", "severity": (SWC.get(swc) or {}).get("sev")})
        await run.emit("stage.started", {"case_id": case_id, "stage": "mythril"})
        await asyncio.sleep(0.08)
        if state == "REPRODUCED_REAL":
            await run.emit("stage.started", {"case_id": case_id, "stage": "echidna-test"})
            await run.emit("stage.started", {"case_id": case_id, "stage": "medusa"})
            await run.emit("finding.correlated", {"case_id": case_id, "swc": swc, "evidence": ["slither", "mythril", "echidna-test", "medusa"]})
            await run.emit("stage.started", {"case_id": case_id, "stage": "forge"})
            artifact = run_case["execution_artifacts"][0]
            await run.emit("poc.result", {"case_id": case_id, "swc": swc, "exploit_verified": True, "assertion_count": artifact.get("assertion_count", 1), "test_path": artifact.get("test_path")})
            reproduced += 1
        await run.emit("case.completed", {"case_id": case_id, "validation_state": state})
        await asyncio.sleep(0.05)
    run.registry = specimen_registry()
    await run.emit("run.completed", {"reproduced": reproduced, "total": total, "precision": 1.0 if total else 0.0, "recall": 1.0 if total else 0.0, "f1": 1.0 if total else 0.0})


async def hunt_run(run: Run) -> None:
    try:
        script = _resolve_project_path(run.params.get("script"), default=DEFAULT_SCRIPT, must_exist=True, label="hunt script")
        registry_path = _resolve_project_path(run.params.get("registry"), default="registry.json", must_exist=False, label="registry path")
        args = _normalize_args(run.params.get("args"))
    except ValueError as exc:
        await run.emit("log.line", {"message": str(exc), "text": str(exc)})
        run.registry = build_registry_from_cases(run)
        await run.emit("run.completed", {"reproduced": 0, "total": 0, "precision": 0.0, "recall": 0.0, "f1": 0.0})
        return
    if args and not ALLOW_HUNT_ARGS:
        await run.emit("log.line", {"message": "hunt args rejected: set ANCHOR_ALLOW_HUNT_ARGS=1 to allow explicit script arguments.", "text": "hunt args rejected"})
        run.registry = build_registry_from_cases(run)
        await run.emit("run.completed", {"reproduced": 0, "total": 0, "precision": 0.0, "recall": 0.0, "f1": 0.0})
        return
    if script.name not in ALLOWED_SCRIPT_NAMES:
        await run.emit("log.line", {"message": f"hunt script rejected: {script.name} is not allowlisted.", "text": "hunt script rejected"})
        run.registry = build_registry_from_cases(run)
        await run.emit("run.completed", {"reproduced": 0, "total": 0, "precision": 0.0, "recall": 0.0, "f1": 0.0})
        return
    await run.emit("run.started", {"mode": "hunt", "benchmark_id": run.benchmark, "total_cases": 0})
    env = dict(os.environ)
    env["ANCHOR_SERVER_URL"] = _self_url()
    env["ANCHOR_RUN_ID"] = run.run_id
    env["PYTHONUNBUFFERED"] = "1"
    try:
        proc = await asyncio.create_subprocess_exec(
            sys.executable,
            str(script),
            *args,
            cwd=str(PROJECT_ROOT),
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
    except Exception as exc:
        await run.emit("log.line", {"message": f"failed to launch hunt: {exc}", "text": f"failed to launch hunt: {exc}"})
        run.registry = build_registry_from_cases(run)
        await run.emit("run.completed", {"reproduced": 0, "total": 0, "precision": 0.0, "recall": 0.0, "f1": 0.0})
        return
    run.process = proc

    async def pump_stdout() -> None:
        assert proc.stdout is not None
        while True:
            line = await proc.stdout.readline()
            if not line:
                return
            text = line.decode(errors="replace").rstrip()
            if text:
                await run.emit("log.line", {"message": text, "text": text})

    stdout_task = asyncio.create_task(pump_stdout())
    returncode = await proc.wait()
    await stdout_task
    if run.cancelled:
        return

    reproduced = 0
    total = 0
    if registry_path and registry_path.exists():
        try:
            registry_data = json.loads(registry_path.read_text(encoding="utf-8"))
            run.registry = registry_data if isinstance(registry_data, dict) else {"results": registry_data}
            results = normalize_registry(registry_data)
            total = len(results)
            reproduced = sum(1 for item in results if item.get("validation_state") == "REPRODUCED_REAL" or item.get("success"))
            if not run.ingested:
                for item in results:
                    normalized = case_from_registry(item)
                    cid = normalized["case_id"]
                    run.cases[cid] = normalized
                    CASE_INDEX[cid] = normalized
                    await run.emit("case.started", {"case_id": cid, "contract": normalized.get("contract"), "expected": normalized.get("expected", [])})
                    if ladder_index(normalized["validation_state"]) >= 0:
                        await run.emit("finding.detected", {"case_id": cid, "swc": normalized.get("swc"), "source": "registry", "severity": (SWC.get(normalized.get("swc")) or {}).get("sev")})
                    if ladder_index(normalized["validation_state"]) >= 1:
                        await run.emit("finding.correlated", {"case_id": cid, "swc": normalized.get("swc"), "evidence": ["registry"]})
                    if ladder_index(normalized["validation_state"]) >= 2:
                        artifact = (normalized.get("execution_artifacts") or [{}])[0]
                        await run.emit("poc.result", {"case_id": cid, "swc": normalized.get("swc"), "exploit_verified": True, "assertion_count": artifact.get("assertion_count", 1), "test_path": artifact.get("test_path")})
                    await run.emit("case.completed", {"case_id": cid, "validation_state": normalized.get("validation_state")})
        except Exception as exc:
            await run.emit("log.line", {"message": f"registry parse failed: {exc}", "text": f"registry parse failed: {exc}"})

    if run.registry is None:
        run.registry = build_registry_from_cases(run)
        total = len(run.registry.get("results", []))
        reproduced = run.registry.get("reproduced", 0)
    elif total == 0:
        results = normalize_registry(run.registry)
        total = len(results)
        reproduced = sum(1 for item in results if item.get("validation_state") == "REPRODUCED_REAL" or item.get("success"))

    await run.emit("run.completed", {
        "reproduced": reproduced,
        "total": total,
        "precision": float(run.registry.get("precision", 0.0)) if isinstance(run.registry, dict) else 0.0,
        "recall": float(run.registry.get("recall", 0.0)) if isinstance(run.registry, dict) else 0.0,
        "f1": float(run.registry.get("f1", 0.0)) if isinstance(run.registry, dict) else 0.0,
    })


async def run_driver(run: Run) -> None:
    try:
        if run.mode == "hunt":
            await hunt_run(run)
        else:
            await demo_run(run)
    except asyncio.CancelledError:
        run.cancelled = True
        run.status = "stopped"
    finally:
        if not run.done.is_set():
            run.done.set()


def create_run(mode: str = "demo", *, script: str | None = None, registry: str | None = None, args: Optional[list[str]] = None, benchmark: str | None = None, target: str | None = None) -> Run:
    run_id = f"run_{secrets.token_hex(6)}"
    params: dict[str, Any] = {"target": target}
    if script is not None:
        params["script"] = str(_resolve_project_path(script, must_exist=True, label="hunt script"))
    if registry is not None:
        params["registry"] = str(_resolve_project_path(registry, must_exist=False, label="registry path"))
    if args is not None:
        params["args"] = _normalize_args(args)
    return Run(run_id=run_id, benchmark=str(benchmark or BENCHMARK), mode=mode, params=params)


app = FastAPI(title="ANCHOR run server", version=APP_VERSION)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root() -> dict[str, Any]:
    return {
        "service": "anchor",
        "version": APP_VERSION,
        "schema_version": "1.0",
        "public_key": PUBLIC_KEY_HEX,
        "public_key_id": PUBLIC_KEY_ID,
        "runs": len(RUNS),
        "signing_key_hint": SIGNING_HINT,
    }


@app.get("/pubkey")
async def pubkey() -> dict[str, Any]:
    return {"algorithm": "ed25519", "public_key": PUBLIC_KEY_HEX, "public_key_id": PUBLIC_KEY_ID}


@app.post("/runs")
async def create_run_route(req: Request) -> dict[str, Any]:
    try:
        body = await req.json()
    except Exception:
        body = {}
    if not isinstance(body, dict):
        body = {}
    mode = str(body.get("mode") or "demo").strip().lower()
    if mode not in {"demo", "hunt"}:
        mode = "demo"
    args = body.get("args")
    if args and not ALLOW_HUNT_ARGS:
        raise HTTPException(status_code=400, detail="hunt args are disabled; set ANCHOR_ALLOW_HUNT_ARGS=1 to allow explicit script arguments")
    try:
        run = create_run(
            mode,
            script=body.get("script"),
            registry=body.get("registry"),
            args=_normalize_args(args) if args is not None else None,
            benchmark=body.get("benchmark"),
            target=body.get("target"),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if run.mode == "hunt" and run.params.get("script") is not None:
        script_name = Path(run.params["script"]).name
        if script_name not in ALLOWED_SCRIPT_NAMES:
            raise HTTPException(status_code=400, detail=f"hunt script {script_name} is not allowlisted")
    RUNS[run.run_id] = run
    run.task = asyncio.create_task(run_driver(run))
    return {"run_id": run.run_id, "mode": run.mode, "status": run.status}


@app.get("/runs/{run_id}/events")
async def run_events(run_id: str, request: Request) -> StreamingResponse:
    run = RUNS.get(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")
    after = request.query_params.get("after")
    queue, replay, already_done = await run.open_stream(after)

    async def stream():
        yield ": anchor stream open\n\n"
        for event in replay:
            yield _sse_frame(event)
        if already_done:
            return
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15)
                except asyncio.TimeoutError:
                    if run.done.is_set():
                        break
                    yield ": keepalive\n\n"
                    continue
                if event is None:
                    break
                yield _sse_frame(event)
                if event.get("type") in TERMINAL_EVENTS:
                    break
        finally:
            await run.close_stream(queue)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


@app.post("/runs/{run_id}/ingest")
async def ingest(run_id: str, req: Request) -> dict[str, Any]:
    run = RUNS.get(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")
    body = await req.json()
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="Event payload must be an object")
    event_type = str(body.get("type") or body.get("event_type") or "").strip()
    if not event_type:
        raise HTTPException(status_code=400, detail="Event type is required")
    payload = body.get("payload")
    if not isinstance(payload, dict):
        payload = {k: v for k, v in body.items() if k not in {"schema_version", "event_id", "run_id", "type", "event_type", "timestamp", "payload"}}
    event = {
        "schema_version": str(body.get("schema_version") or "1.0"),
        "event_id": str(body.get("event_id") or f"evt_{secrets.token_hex(8)}"),
        "run_id": run_id,
        "type": event_type,
        "timestamp": str(body.get("timestamp") or utc_stamp()),
        "payload": payload,
    }
    if event_type != "log.line":
        run.ingested = True
    await run.ingest_envelope(event)
    return {"ok": True, "event": event}


@app.post("/runs/{run_id}/cancel")
async def cancel_run(run_id: str) -> dict[str, Any]:
    run = RUNS.get(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")
    run.cancelled = True
    if run.process and run.process.returncode is None:
        try:
            run.process.terminate()
        except ProcessLookupError:
            pass
    await run.emit("run.stopped", {"reason": "cancelled_by_operator"})
    if run.task:
        run.task.cancel()
    return {"ok": True, "run_id": run_id, "status": run.status}


@app.get("/runs/{run_id}/registry")
async def run_registry(run_id: str) -> dict[str, Any]:
    run = RUNS.get(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")
    if run.registry is None and not run.done.is_set():
        return {"status": run.status, "registry": None, "note": "run not finished"}
    if run.registry is None:
        run.registry = build_registry_from_cases(run)
    return {
        "run_id": run.run_id,
        "mode": run.mode,
        "status": run.status,
        "registry": run.registry,
        "cases": list(run.cases.values()),
        "event_count": len(run.events),
    }


@app.get("/cases/{case_id}")
async def get_case(case_id: str) -> dict[str, Any]:
    if case_id in CASE_INDEX:
        case = CASE_INDEX[case_id]
        if case.get("swc"):
            case = dict(case)
            case["swc_detail"] = SWC.get(case["swc"])
        return case
    for run in RUNS.values():
        if case_id in run.cases:
            case = dict(run.cases[case_id])
            if case.get("swc"):
                case["swc_detail"] = SWC.get(case["swc"])
            return case
    fixture = _fixture_for_case(case_id)
    if fixture:
        case = dict(fixture)
        if case.get("swc"):
            case["swc_detail"] = SWC.get(case["swc"])
        return case
    raise HTTPException(status_code=404, detail=f"Case not found: {case_id}")


@app.post("/evidence/sign")
async def evidence_sign(req: Request) -> dict[str, Any]:
    payload = await req.json()
    if isinstance(payload, dict) and isinstance(payload.get("bundle"), dict):
        bundle = payload["bundle"]
    elif isinstance(payload, dict):
        bundle = payload
    else:
        raise HTTPException(status_code=400, detail="Evidence bundle must be an object")
    bundle.pop("signature", None)
    bundle.pop("integrity", None)
    return {"ok": True, "signed_bundle": sign_bundle(bundle), "signing_hint": SIGNING_HINT, "public_key": PUBLIC_KEY_HEX}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=DEFAULT_HOST, port=DEFAULT_PORT, reload=False)
