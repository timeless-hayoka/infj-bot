"""Trinity release and archive helpers.

This module centralizes versioning, run history, archive creation, report export,
and upgrade planning so the CLI stays thin and the release contract remains
stable across commands.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib import metadata
from pathlib import Path
from typing import Any

try:
    import tomllib
except ImportError:  # pragma: no cover - Python < 3.11 fallback
    tomllib = None  # type: ignore[assignment]

from drift.config_adapter import LOGS_DIR, PROJECT_ROOT

from .caseflow import (
    TRINITY_CASES_DIR,
    TRINITY_LEDGER_PATH,
    TrinityCaseLedger,
    load_case_bundle,
    load_case_report,
    resolve_case_root,
)

TRINITY_ARCHIVE_DIR = LOGS_DIR / "trinity_archives"
TRINITY_ARCHIVE_LEDGER_PATH = LOGS_DIR / "trinity_archive_ledger.jsonl"
RELEASE_MANIFEST_PATH = PROJECT_ROOT / "release.json"



def utc_stamp() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _read_pyproject_version() -> str:
    pyproject = PROJECT_ROOT / "pyproject.toml"
    if not pyproject.exists() or tomllib is None:
        return "0.1.0"
    try:
        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
        project = data.get("project", {})
        return str(project.get("version") or "0.1.0")
    except Exception:
        return "0.1.0"


def _git_commit_short() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            check=False,
        )
        commit = result.stdout.strip()
        return commit or "unknown"
    except Exception:
        return "unknown"


def _git_branch() -> str:
    try:
        result = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            check=False,
        )
        branch = result.stdout.strip()
        return branch or "unknown"
    except Exception:
        return "unknown"



def _default_release_manifest() -> dict[str, Any]:
    return {
        "product": "ANCHOR",
        "engine": "Trinity",
        "version": _read_pyproject_version(),
        "build_date": datetime.now(UTC).date().isoformat(),
        "tests_passed": None,
        "warnings": None,
        "status": "release_candidate",
        "build_id": f"anchor-{_read_pyproject_version()}-{datetime.now(UTC).strftime('%Y%m%d')}",
    }


def _load_release_manifest() -> dict[str, Any]:
    if RELEASE_MANIFEST_PATH.exists():
        try:
            loaded = json.loads(RELEASE_MANIFEST_PATH.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                return loaded
        except Exception:
            pass
    return _default_release_manifest()

def get_release_info() -> dict[str, Any]:
    manifest = _load_release_manifest()
    try:
        installed_version = metadata.version("drift")
    except Exception:
        installed_version = _read_pyproject_version()
    version = str(manifest.get("version") or installed_version)
    build = str(manifest.get("build_date") or manifest.get("build") or datetime.now(UTC).strftime("%Y.%m.%d"))
    return {
        "product": str(manifest.get("product") or "ANCHOR"),
        "engine": str(manifest.get("engine") or "Trinity"),
        "name": str(manifest.get("product") or "ANCHOR"),
        "package": "drift",
        "version": version,
        "build": build,
        "commit": str(manifest.get("commit") or _git_commit_short()),
        "branch": str(manifest.get("branch") or _git_branch()),
        "status": str(manifest.get("status") or "release_candidate"),
        "build_id": str(manifest.get("build_id") or f"anchor-{version}-{build.replace('.', '')}"),
        "tests_passed": manifest.get("tests_passed"),
        "warnings": manifest.get("warnings"),
        "manifest_path": str(RELEASE_MANIFEST_PATH),
        "project_root": str(PROJECT_ROOT),
        "cases_dir": str(TRINITY_CASES_DIR),
        "ledger_path": str(TRINITY_LEDGER_PATH),
        "archive_dir": str(TRINITY_ARCHIVE_DIR),
        "archive_ledger_path": str(TRINITY_ARCHIVE_LEDGER_PATH),
    }


def render_release_text(info: dict[str, Any]) -> str:
    return "\n".join(
        [
            f"{info.get('product', 'ANCHOR')} {info.get('version', 'unknown')}",
            "Powered by Trinity",
            f"Build: {info.get('build', 'unknown')}",
            f"Build ID: {info.get('build_id', 'unknown')}",
            f"Commit: {info.get('commit', 'unknown')}",
            f"Branch: {info.get('branch', 'unknown')}",
            f"Status: {info.get('status', 'unknown')}",
            f"Cases dir: {info.get('cases_dir', 'unknown')}",
            f"Ledger: {info.get('ledger_path', 'unknown')}",
            f"Archive dir: {info.get('archive_dir', 'unknown')}",
        ]
    )

def brand_public_report_text(report: str) -> str:
    text = (report or "").strip()
    if not text:
        return "\n".join([
            "ANCHOR Investigation Report",
            "Powered by Trinity",
            "",
        ])

    replacements = [
        ("# Trinity Evidence Packet", "# ANCHOR Investigation Report"),
        ("# Trinity Report", "# ANCHOR Investigation Report"),
        ("Trinity Evidence Packet", "ANCHOR Investigation Report"),
        ("Trinity Report", "ANCHOR Investigation Report"),
    ]
    branded = text
    for old, new in replacements:
        if old in branded:
            branded = branded.replace(old, new, 1)
            break
    else:
        branded = "\n".join([
            "ANCHOR Investigation Report",
            "Powered by Trinity",
            "",
            branded,
        ])
        return branded

    if "Powered by Trinity" not in branded:
        branded = branded.replace(
            "# ANCHOR Investigation Report",
            "# ANCHOR Investigation Report\n\nPowered by Trinity",
            1,
        )
    return branded

@dataclass
class TrinityArchiveLedger:
    ledger_path: Path = TRINITY_ARCHIVE_LEDGER_PATH

    def __post_init__(self) -> None:
        self.ledger_path = Path(self.ledger_path)
        self.ledger_path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, entry: dict[str, Any]) -> dict[str, Any]:
        payload = dict(entry)
        payload.setdefault("timestamp", utc_stamp())
        with self.ledger_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=True) + "\n")
        return payload

    def recent(self, limit: int = 10) -> list[dict[str, Any]]:
        if not self.ledger_path.exists():
            return []
        entries: list[dict[str, Any]] = []
        with self.ledger_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return entries[-max(0, int(limit)) :]

    def find(self, archive_id: str) -> dict[str, Any] | None:
        matches = [
            entry for entry in self.recent(10_000) if str(entry.get("archive_id")) == str(archive_id)
        ]
        return matches[-1] if matches else None

def _history_ledger(ledger_path: str | Path | None = None) -> TrinityCaseLedger:
    return TrinityCaseLedger(Path(ledger_path) if ledger_path else TRINITY_LEDGER_PATH)


def load_history(
    *,
    limit: int = 20,
    ledger_path: str | Path | None = None,
    case_id: str | None = None,
    status: str | None = None,
    scanner_format: str | None = None,
) -> list[dict[str, Any]]:
    entries = _history_ledger(ledger_path).recent(10_000)
    filtered: list[dict[str, Any]] = []
    for entry in entries:
        if case_id and str(entry.get("case_id")) != str(case_id):
            continue
        if status and str(entry.get("status", "")).lower() != str(status).lower():
            continue
        if scanner_format and str(entry.get("scanner_format", "")).lower() != str(scanner_format).lower():
            continue
        filtered.append(entry)
    return filtered[-max(0, int(limit)) :]


def summarize_history(entries: list[dict[str, Any]]) -> dict[str, Any]:
    status_counts: dict[str, int] = {}
    scanner_counts: dict[str, int] = {}
    for entry in entries:
        status = str(entry.get("status", "unknown"))
        scanner = str(entry.get("scanner_format", "unknown"))
        status_counts[status] = status_counts.get(status, 0) + 1
        scanner_counts[scanner] = scanner_counts.get(scanner, 0) + 1
    return {
        "count": len(entries),
        "status_counts": status_counts,
        "scanner_counts": scanner_counts,
    }


def render_history_text(entries: list[dict[str, Any]]) -> str:
    summary = summarize_history(entries)
    lines = [
        "TRINITY HISTORY",
        f"Runs: {summary['count']}",
        f"Statuses: {summary['status_counts'] or {}}",
        f"Scanner formats: {summary['scanner_counts'] or {}}",
        "",
    ]
    for entry in entries:
        lines.append(
            f"{entry.get('timestamp', 'unknown')} | {entry.get('case_id', 'unknown')} | "
            f"{entry.get('status', 'unknown')} | {entry.get('scanner_format', 'unknown')} | "
            f"findings={entry.get('finding_count', 0)} | {entry.get('output_dir', '')}"
        )
    if len(entries) == 0:
        lines.append("No Trinity history recorded yet.")
    return "\n".join(lines)

def render_archive_text(record: dict[str, Any]) -> str:
    return "\n".join(
        [
            f"Archive: {record.get('archive_id', 'unknown')}",
            f"Case: {record.get('case_id', 'unknown')}",
            f"Status: {record.get('status', 'unknown')}",
            f"Archive dir: {record.get('archive_dir', 'unknown')}",
            f"Source bundle: {record.get('source_bundle', 'unknown')}",
            f"Created at: {record.get('created_at', 'unknown')}",
        ]
    )

def _archive_root_for(case_id: str, archive_id: str, output_dir: str | Path | None = None) -> Path:
    return Path(output_dir) if output_dir else TRINITY_ARCHIVE_DIR / case_id / archive_id


def _archive_manifest(
    root: Path,
    *,
    case_id: str,
    case_root: Path,
    bundle: dict[str, Any],
    release: dict[str, Any],
) -> dict[str, Any]:
    packet = bundle.get("packet") or bundle
    claim = bundle.get("claim") or packet.get("claim", {})
    archive_files: list[str] = []
    for item in sorted(root.rglob("*")):
        if item.is_file():
            archive_files.append(str(item.relative_to(root)))
    return {
        "archive_id": root.name,
        "case_id": case_id,
        "status": packet.get("status", bundle.get("status", "unknown")),
        "claim_id": claim.get("id") or packet.get("claim", {}).get("id") or case_id,
        "source_bundle": str(case_root),
        "archive_dir": str(root),
        "created_at": utc_stamp(),
        "release": release,
        "files": archive_files,
    }


def create_archive(
    case_ref: str | Path,
    *,
    output_dir: str | Path | None = None,
    ledger_path: str | Path | None = None,
    archive_ledger_path: str | Path | None = None,
    zip_output: bool = False,
) -> dict[str, Any]:
    history_ledger = _history_ledger(ledger_path)
    case_root = resolve_case_root(case_ref, ledger=history_ledger)
    if case_root is None or not case_root.exists():
        raise FileNotFoundError(f"Case not found: {case_ref}")

    bundle = load_case_bundle(case_root)
    case_id = str(bundle.get("case_id") or (bundle.get("claim") or {}).get("id") or Path(case_root).name)
    archive_id = f"{case_id}-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"
    archive_root = _archive_root_for(case_id, archive_id, output_dir)
    archive_root.parent.mkdir(parents=True, exist_ok=True)
    archive_root.mkdir(parents=True, exist_ok=True)

    shutil.copytree(case_root, archive_root, dirs_exist_ok=True)

    release = get_release_info()
    manifest = _archive_manifest(
        archive_root,
        case_id=case_id,
        case_root=case_root,
        bundle=bundle,
        release=release,
    )
    (archive_root / "archive_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )

    zip_path: str | None = None
    if zip_output:
        zip_target = shutil.make_archive(str(archive_root), "zip", root_dir=archive_root)
        zip_path = str(Path(zip_target))
        manifest["zip_path"] = zip_path
        (archive_root / "archive_manifest.json").write_text(
            json.dumps(manifest, indent=2, ensure_ascii=True) + "\n",
            encoding="utf-8",
        )

    archive_entry = TrinityArchiveLedger(archive_ledger_path or TRINITY_ARCHIVE_LEDGER_PATH).append(
        {
            "archive_id": archive_id,
            "case_id": case_id,
            "status": manifest.get("status"),
            "archive_dir": str(archive_root),
            "source_bundle": str(case_root),
            "zip_path": zip_path,
            "claim_id": manifest.get("claim_id"),
            "created_at": manifest.get("created_at"),
            "release": release,
        }
    )

    return {
        "archive_id": archive_id,
        "case_id": case_id,
        "archive_dir": str(archive_root),
        "source_bundle": str(case_root),
        "manifest": manifest,
        "ledger_entry": archive_entry,
        "zip_path": zip_path,
        "bundle": bundle,
    }


def _load_archive_manifest(archive_dir: Path) -> dict[str, Any]:
    manifest_path = archive_dir / "archive_manifest.json"
    if manifest_path.exists():
        return json.loads(manifest_path.read_text(encoding="utf-8"))
    return {
        "archive_dir": str(archive_dir),
        "case_id": archive_dir.name,
        "status": "unknown",
    }


def load_archive_record(
    archive_ref: str | Path,
    *,
    archive_ledger_path: str | Path | None = None,
) -> dict[str, Any]:
    candidate = Path(archive_ref)
    if candidate.exists():
        manifest = _load_archive_manifest(candidate)
        manifest.setdefault("archive_dir", str(candidate))
        return manifest

    ledger = TrinityArchiveLedger(archive_ledger_path or TRINITY_ARCHIVE_LEDGER_PATH)
    entry = ledger.find(str(archive_ref))
    if entry is None:
        raise FileNotFoundError(f"Archive not found: {archive_ref}")
    archive_dir = Path(entry.get("archive_dir", ""))
    manifest = _load_archive_manifest(archive_dir) if archive_dir.exists() else {}
    merged = {**entry, **manifest}
    merged.setdefault("archive_dir", str(archive_dir))
    return merged


def list_archives(
    *,
    limit: int = 20,
    archive_ledger_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    ledger = TrinityArchiveLedger(archive_ledger_path or TRINITY_ARCHIVE_LEDGER_PATH)
    return ledger.recent(limit)


def export_case_report(
    case_ref: str | Path,
    *,
    output: str | Path | None = None,
    ledger_path: str | Path | None = None,
) -> dict[str, Any]:
    history_ledger = _history_ledger(ledger_path)
    case_root = resolve_case_root(case_ref, ledger=history_ledger)
    if case_root is None or not case_root.exists():
        raise FileNotFoundError(f"Case not found: {case_ref}")

    report = brand_public_report_text(load_case_report(case_root))
    report_path = Path(output) if output else None
    if report_path is not None:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(report, encoding="utf-8")

    bundle = load_case_bundle(case_root)
    claim = bundle.get("claim") or {}
    packet = bundle.get("packet") or bundle
    return {
        "case_id": bundle.get("case_id") or claim.get("id") or Path(case_root).name,
        "status": packet.get("status", bundle.get("status", "unknown")),
        "report": report,
        "output_path": str(report_path) if report_path else None,
        "source_bundle": str(case_root),
    }


def build_upgrade_plan(apply: bool = False) -> dict[str, Any]:
    release = get_release_info()
    git_repo = (PROJECT_ROOT / ".git").exists()
    if git_repo:
        commands: list[list[str]] = [
            ["git", "pull", "--ff-only"],
            [sys.executable, "-m", "pip", "install", "-e", "."],
        ]
    else:
        commands = [[sys.executable, "-m", "pip", "install", "-U", "drift"]]

    executed: list[str] = []
    if apply:
        for command in commands:
            subprocess.run(command, cwd=str(PROJECT_ROOT), check=True)
            executed.append(" ".join(command))

    return {
        "current_release": release,
        "git_repo": git_repo,
        "apply": apply,
        "commands": commands,
        "executed": executed,
        "note": "Applied release update" if apply else "Dry run only; no commands executed",
    }


def render_upgrade_text(plan: dict[str, Any]) -> str:
    release = plan.get("current_release", {})
    lines = [
        "TRINITY UPGRADE PLAN",
        f"Current version: {release.get('version', 'unknown')}",
        f"Current commit: {release.get('commit', 'unknown')}",
        f"Git repo: {'yes' if plan.get('git_repo') else 'no'}",
        f"Mode: {'apply' if plan.get('apply') else 'dry-run'}",
        "",
        "Commands:",
    ]
    for command in plan.get("commands", []):
        lines.append("  $ {}".format(" ".join(command)))
    if plan.get("executed"):
        lines.append("")
        lines.append("Executed:")
        for command in plan["executed"]:
            lines.append(f"  $ {command}")
    return "\n".join(lines)
