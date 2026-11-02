# ruff: noqa: N999 - legacy public filename or repository compatibility shim
"""Trinity system helpers."""

from .adapters import (
    build_sarif_findings,
    build_slither_findings,
    is_sarif_payload,
    is_slither_payload,
)
from .caseflow import (
    TRINITY_CASES_DIR,
    TRINITY_LEDGER_PATH,
    TrinityCaseLedger,
    build_case_context,
    default_case_dir,
    load_case_bundle,
    load_case_report,
    load_case_reproduction,
    parse_scanner_input,
    resolve_case_root,
    run_case_from_scan,
    run_demo_case,
)
from .database import TrinityDatabase, db

try:
    from .http_api import app as trinity_app
    from .http_api import build_trinity_app, build_trinity_router
except ModuleNotFoundError as exc:  # pragma: no cover - optional web dependency
    if exc.name != "fastapi":
        raise

    trinity_app = None

    def build_trinity_app(*args, **kwargs):  # type: ignore[override]
        raise RuntimeError("FastAPI is not installed; Trinity HTTP API is unavailable.")

    def build_trinity_router(*args, **kwargs):  # type: ignore[override]
        raise RuntimeError("FastAPI is not installed; Trinity HTTP API is unavailable.")


__all__ = [
    "TRINITY_CASES_DIR",
    "TRINITY_LEDGER_PATH",
    "TrinityCaseLedger",
    "TrinityDatabase",
    "build_case_context",
    "build_sarif_findings",
    "build_slither_findings",
    "build_trinity_app",
    "build_trinity_router",
    "db",
    "default_case_dir",
    "is_sarif_payload",
    "is_slither_payload",
    "load_case_bundle",
    "load_case_report",
    "load_case_reproduction",
    "parse_scanner_input",
    "resolve_case_root",
    "run_case_from_scan",
    "run_demo_case",
    "trinity_app",
]
