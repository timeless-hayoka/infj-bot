"""Trinity system helpers."""

from .adapters import build_slither_findings, is_slither_payload
from .database import TrinityDatabase, db
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
try:
    from .http_api import app as trinity_app, build_trinity_app, build_trinity_router
except ModuleNotFoundError as exc:  # pragma: no cover - optional web dependency
    if exc.name != "fastapi":
        raise

    trinity_app = None

    def build_trinity_app(*args, **kwargs):  # type: ignore[override]
        raise RuntimeError("FastAPI is not installed; Trinity HTTP API is unavailable.")

    def build_trinity_router(*args, **kwargs):  # type: ignore[override]
        raise RuntimeError("FastAPI is not installed; Trinity HTTP API is unavailable.")

__all__ = [
    'build_slither_findings',
    'is_slither_payload',
    'TRINITY_CASES_DIR',
    'TRINITY_LEDGER_PATH',
    'TrinityDatabase',
    'db',
    'TrinityCaseLedger',
    'build_case_context',
    'default_case_dir',
    'load_case_bundle',
    'load_case_report',
    'load_case_reproduction',
    'parse_scanner_input',
    'resolve_case_root',
    'run_case_from_scan',
    'run_demo_case',
    'build_trinity_router',
    'build_trinity_app',
    'trinity_app',
]
