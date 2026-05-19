#!/usr/bin/env python3
"""selfcheck.py — DRIFT comprehensive self-check and health validation.

Validates the integrity of all cognitive subsystems, databases, plugin registry,
and runtime environment. Can be run as a CLI tool or imported to register checks
with the HealthMonitor from resilience.py.

Exit codes:
    0 — All systems healthy
    1 — Warnings present (degraded but functional)
    2 — Critical failures (system may not operate correctly)
"""

import argparse
import json
import os
import sqlite3
import sys
import time
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

# ── Lazy imports for drift subsystems ─────────────────────────────────────────
# We import lazily so a missing dependency doesn't crash the whole check suite.


def _import_config() -> Tuple[Any, Any]:
    try:
        from infj_bot.core.config import DATA_DIR, SQLITE_DIR, CHROMA_DIR
        return DATA_DIR, SQLITE_DIR, CHROMA_DIR
    except Exception:
        return None, None, None


def _import_resilience() -> Any:
    try:
        from infj_bot.core.resilience import HealthCheck, HealthMonitor
        return HealthCheck, HealthMonitor
    except Exception:
        return None, None


def _import_architecture() -> Any:
    try:
        from infj_bot.core.cognitive_architecture import CognitiveArchitecture
        return CognitiveArchitecture
    except Exception:
        return None


def _import_being() -> Any:
    try:
        from infj_bot.core.being import get_being
        return get_being
    except Exception:
        return None


def _import_shadow() -> Any:
    try:
        from infj_bot.core.shadow import get_shadow
        return get_shadow
    except Exception:
        return None


def _import_homeostasis() -> Any:
    try:
        from infj_bot.core.homeostasis import get_homeostasis
        return get_homeostasis
    except Exception:
        return None


# ── Check registry ────────────────────────────────────────────────────────────

CheckFn = Callable[[], Any]


class SelfCheckRunner:
    """Runs a suite of health checks and aggregates results."""

    def __init__(self):
        self._checks: Dict[str, CheckFn] = {}
        self._results: List[Any] = []

    def register(self, name: str, fn: CheckFn):
        self._checks[name] = fn

    def run(self, names: Optional[List[str]] = None, verbose: bool = False) -> Tuple[List[Any], int]:
        """Run checks and return (results, max_severity).

        Severity: 0 = healthy, 1 = warning, 2 = critical
        """
        results = []
        max_severity = 0
        to_run = [(n, self._checks[n]) for n in (names or list(self._checks.keys()))]

        for name, fn in to_run:
            start = time.time()
            try:
                result = fn()
            except Exception as exc:
                result = self._make_check(name, False, f"Check crashed: {exc}", start)
                max_severity = max(max_severity, 2)
            else:
                if not getattr(result, "healthy", True):
                    max_severity = max(max_severity, 2 if "CRITICAL" in getattr(result, "message", "") else 1)
                elif "WARNING" in getattr(result, "message", ""):
                    max_severity = max(max_severity, 1)
            results.append(result)
            if verbose:
                status = "OK" if getattr(result, "healthy", True) else "FAIL"
                msg = getattr(result, "message", "")
                print(f"  [{status}] {name}: {msg}")

        self._results = results
        return results, max_severity

    @staticmethod
    def _make_check(name: str, healthy: bool, message: str, start: float):
        HealthCheck, _ = _import_resilience()
        if HealthCheck is None:
            # Fallback simple object when resilience isn't available
            class _FallbackCheck:
                def __init__(self, name, healthy, message, latency_ms):
                    self.name = name
                    self.healthy = healthy
                    self.message = message
                    self.latency_ms = latency_ms
                    self.timestamp = datetime.now().isoformat()
            return _FallbackCheck(name, healthy, message, (time.time() - start) * 1000)
        return HealthCheck(
            name=name,
            healthy=healthy,
            latency_ms=(time.time() - start) * 1000,
            message=message,
        )

    def report_text(self) -> str:
        lines = ["=== DRIFT SELF-CHECK REPORT ===", f"Timestamp: {datetime.now().isoformat()}", ""]
        healthy_count = 0
        warning_count = 0
        fail_count = 0
        for r in self._results:
            if getattr(r, "healthy", True):
                if "WARNING" in getattr(r, "message", ""):
                    lines.append(f"  [WARN] {r.name}: {r.message}")
                    warning_count += 1
                else:
                    lines.append(f"  [ OK ] {r.name}: {r.message}")
                    healthy_count += 1
            else:
                lines.append(f"  [FAIL] {r.name}: {r.message}")
                fail_count += 1
        lines.append("")
        lines.append(f"Summary: {healthy_count} healthy, {warning_count} warnings, {fail_count} critical")
        return "\n".join(lines)

    def report_json(self) -> str:
        payload = {
            "timestamp": datetime.now().isoformat(),
            "healthy": all(getattr(r, "healthy", True) for r in self._results),
            "checks": [
                {
                    "name": r.name,
                    "healthy": getattr(r, "healthy", True),
                    "message": getattr(r, "message", ""),
                    "latency_ms": getattr(r, "latency_ms", 0.0),
                }
                for r in self._results
            ],
        }
        return json.dumps(payload, indent=2)


# ── Individual check implementations ──────────────────────────────────────────

def check_data_directories() -> Any:
    """Verify data root and subdirectories exist and are writable."""
    start = time.time()
    DATA_DIR, SQLITE_DIR, CHROMA_DIR = _import_config()
    if DATA_DIR is None:
        return _quick_check("data_directories", False, "Cannot import config (DATA_DIR unknown)", start)

    issues = []
    for label, path in [("data", DATA_DIR), ("sqlite", SQLITE_DIR), ("chroma", CHROMA_DIR)]:
        if path is None:
            issues.append(f"{label} path is None")
            continue
        p = Path(path)
        if not p.exists():
            issues.append(f"{label} dir missing: {p}")
        elif not os.access(p, os.W_OK):
            issues.append(f"{label} dir not writable: {p}")

    if issues:
        return _quick_check("data_directories", False, "; ".join(issues), start)
    return _quick_check("data_directories", True, f"DATA_DIR={DATA_DIR}", start)


def check_sqlite_databases() -> Any:
    """Verify all SQLite databases in the sqlite directory are responsive."""
    start = time.time()
    DATA_DIR, SQLITE_DIR, _ = _import_config()
    if SQLITE_DIR is None:
        return _quick_check("sqlite_databases", False, "SQLITE_DIR unknown", start)

    sqlite_dir = Path(SQLITE_DIR)
    if not sqlite_dir.exists():
        return _quick_check("sqlite_databases", False, f"SQLITE_DIR does not exist: {sqlite_dir}", start)

    dbs = list(sqlite_dir.glob("*.db"))
    if not dbs:
        return _quick_check("sqlite_databases", True, "No .db files found yet (fresh install)", start)

    failures = []
    warnings = []
    for db_path in dbs:
        # Skip files that are not SQLite databases (e.g. NDJSON files with .db extension)
        header = db_path.read_bytes()[:16]
        if not header.startswith(b"SQLite format 3"):
            warnings.append(f"{db_path.name}: not a SQLite file (skipping)")
            continue
        try:
            conn = sqlite3.connect(str(db_path), timeout=3)
            cur = conn.execute("PRAGMA integrity_check;")
            result = cur.fetchone()
            conn.close()
            if result is None or result[0] != "ok":
                failures.append(f"{db_path.name}: integrity_check={result}")
        except Exception as e:
            failures.append(f"{db_path.name}: {e}")

    if failures:
        return _quick_check("sqlite_databases", False, f"{len(failures)} DB issue(s): {failures[0]}", start)
    msg = f"{len(dbs)} database(s) healthy"
    if warnings:
        msg += f"; {len(warnings)} warning(s)"
    return _quick_check("sqlite_databases", True, msg, start)


def check_required_tables() -> Any:
    """Verify key subsystem databases have their required schema tables."""
    start = time.time()
    DATA_DIR, SQLITE_DIR, _ = _import_config()
    if SQLITE_DIR is None:
        return _quick_check("required_tables", False, "SQLITE_DIR unknown", start)

    required = {
        "being.db": ["being_state", "thoughts", "insights", "narrative", "autonomous_choices"],
        "shadow.db": ["shadow_content", "shadow_state"],
        "homeostasis.db": ["need_history", "survival_events", "regulation_actions"],
        "cognitive_architecture.db": ["cognitive_plugins", "plugin_proposals", "architecture_events"],
        "health.db": ["health_checks"],
    }

    failures = []
    warnings_list = []
    sqlite_dir = Path(SQLITE_DIR)
    for db_name, tables in required.items():
        db_path = sqlite_dir / db_name
        if not db_path.exists():
            warnings_list.append(f"{db_name}: missing (will be created on first use)")
            continue
        try:
            conn = sqlite3.connect(str(db_path), timeout=3)
            cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table';")
            existing = {row[0] for row in cur.fetchall()}
            conn.close()
            missing = [t for t in tables if t not in existing]
            if missing:
                failures.append(f"{db_name}: missing tables {missing}")
        except Exception as e:
            failures.append(f"{db_name}: {e}")

    if failures:
        return _quick_check("required_tables", False, f"{len(failures)} issue(s): {failures[0]}", start)
    msg = "All required tables present"
    if warnings_list:
        msg += f"; {len(warnings_list)} DB(s) not yet initialized"
    return _quick_check("required_tables", True, msg, start)


def check_plugin_registry() -> Any:
    """Verify core cognitive plugins are registered and enabled."""
    start = time.time()
    CognitiveArchitecture = _import_architecture()
    if CognitiveArchitecture is None:
        return _quick_check("plugin_registry", False, "Cannot import CognitiveArchitecture", start)

    try:
        arch = CognitiveArchitecture()
        registered = set(arch.list_plugins())
        from infj_bot.core.cognitive_architecture import CORE_PLUGINS
        missing_core = CORE_PLUGINS - registered
        disabled_core = {p for p in CORE_PLUGINS if p in registered and not arch.get_plugin(p).enabled}
    except Exception as e:
        return _quick_check("plugin_registry", False, f"Registry load failed: {e}", start)

    issues = []
    warnings_list = []
    if missing_core:
        # Some "core" modules (brain, memory) may not be plugin-registered yet
        warnings_list.append(f"missing core plugins: {', '.join(missing_core)}")
    if disabled_core:
        issues.append(f"disabled core: {', '.join(disabled_core)}")
    total = len(registered)
    if total < 5:
        issues.append(f"only {total} plugins registered (expected >= 5)")

    if issues:
        return _quick_check("plugin_registry", False, "; ".join(issues), start)
    msg = f"{total} plugins registered"
    if warnings_list:
        msg += f"; WARNING: {'; '.join(warnings_list)}"
    return _quick_check("plugin_registry", True, msg, start)


def check_being_state() -> Any:
    """Validate being subsystem state is within expected ranges."""
    start = time.time()
    get_being = _import_being()
    if get_being is None:
        return _quick_check("being_state", False, "Cannot import being module", start)

    try:
        being = get_being()
        s = being.state
        issues = []
        for field_name in ("energy", "intensity", "curiosity", "attachment"):
            val = getattr(s, field_name, None)
            if val is None:
                issues.append(f"{field_name}=None")
            elif not (0.0 <= val <= 1.0):
                issues.append(f"{field_name}={val:.2f} out of range")
        if not s.mood:
            issues.append("mood is empty")
        msg = "; ".join(issues) if issues else f"mood={s.mood}, energy={s.energy:.0%}"
        healthy = len(issues) == 0
        return _quick_check("being_state", healthy, msg, start)
    except Exception as e:
        return _quick_check("being_state", False, f"Being check failed: {e}", start)


def check_shadow_state() -> Any:
    """Validate shadow subsystem state."""
    start = time.time()
    get_shadow = _import_shadow()
    if get_shadow is None:
        return _quick_check("shadow_state", False, "Cannot import shadow module", start)

    try:
        shadow = get_shadow()
        st = shadow.get_state()
        issues = []
        for field_name in ("depth", "integration_level", "projection_strength", "enantiodromia_risk", "golden_shadow_ratio"):
            val = getattr(st, field_name, None)
            if val is None:
                issues.append(f"{field_name}=None")
            elif not (0.0 <= val <= 1.0):
                issues.append(f"{field_name}={val:.2f} out of range")
        msg = "; ".join(issues) if issues else (
            f"depth={st.depth:.0%}, integration={st.integration_level:.0%}, "
            f"dominant={st.dominant_archetype or 'none'}"
        )
        healthy = len(issues) == 0
        return _quick_check("shadow_state", healthy, msg, start)
    except Exception as e:
        return _quick_check("shadow_state", False, f"Shadow check failed: {e}", start)


def check_homeostasis_state() -> Any:
    """Validate homeostatic needs are within bounds and not in crisis."""
    start = time.time()
    get_homeostasis = _import_homeostasis()
    if get_homeostasis is None:
        return _quick_check("homeostasis_state", False, "Cannot import homeostasis module", start)

    try:
        reg = get_homeostasis()
        issues = []
        critical = []
        for name, need in reg.needs.items():
            if not (0.0 <= need.current <= 1.0):
                issues.append(f"{name}={need.current:.2f} out of range")
            if need.current < need.critical_low or need.current > need.critical_high:
                critical.append(name)
        if critical:
            issues.append(f"CRITICAL needs: {', '.join(critical)}")
        msg = "; ".join(issues) if issues else f"{len(reg.needs)} needs stable"
        healthy = len(issues) == 0
        return _quick_check("homeostasis_state", healthy, msg, start)
    except Exception as e:
        return _quick_check("homeostasis_state", False, f"Homeostasis check failed: {e}", start)


def check_chroma_health() -> Any:
    """Verify ChromaDB directory exists and is accessible."""
    start = time.time()
    DATA_DIR, _, CHROMA_DIR = _import_config()
    if CHROMA_DIR is None:
        return _quick_check("chroma_health", True, "CHROMA_DIR not configured (optional)", start)

    chroma_path = Path(CHROMA_DIR)
    if not chroma_path.exists():
        return _quick_check("chroma_health", False, f"ChromaDB directory missing: {chroma_path}", start)
    if not os.access(chroma_path, os.W_OK):
        return _quick_check("chroma_health", False, f"ChromaDB directory not writable: {chroma_path}", start)

    # Try to actually connect if chromadb is installed
    try:
        import chromadb
        client = chromadb.PersistentClient(path=str(chroma_path))
        # A lightweight heartbeat equivalent
        client.heartbeat()
        return _quick_check("chroma_health", True, f"ChromaDB responsive at {chroma_path}", start)
    except ImportError:
        return _quick_check("chroma_health", True, f"Directory OK (chromadb not installed)", start)
    except Exception as e:
        return _quick_check("chroma_health", False, f"ChromaDB connection failed: {e}", start)


def check_disk_space() -> Any:
    """Ensure the data root partition has adequate free space."""
    start = time.time()
    DATA_DIR, _, _ = _import_config()
    path = Path(DATA_DIR) if DATA_DIR else Path.home()
    try:
        stat = os.statvfs(path)
        free_gb = (stat.f_bavail * stat.f_frsize) / (1024 ** 3)
        total_gb = (stat.f_blocks * stat.f_frsize) / (1024 ** 3)
        pct_free = free_gb / total_gb * 100 if total_gb else 0
        if free_gb < 1.0:
            return _quick_check("disk_space", False, f"CRITICAL: only {free_gb:.1f} GB free", start)
        if pct_free < 10:
            return _quick_check("disk_space", True, f"WARNING: {free_gb:.1f} GB free ({pct_free:.0f}%)", start)
        return _quick_check("disk_space", True, f"{free_gb:.1f} GB free ({pct_free:.0f}%)", start)
    except Exception as e:
        return _quick_check("disk_space", False, f"Cannot check disk: {e}", start)


def check_environment() -> Any:
    """Check required environment configuration."""
    start = time.time()
    warnings_list = []
    # Optional but useful keys
    for key in ("DRIFT_OS_ROOT", "DRIFT_PRIMARY_MODEL"):
        if not os.getenv(key):
            warnings_list.append(f"{key} not set")
    # API keys: at least one should be present for full functionality
    has_api = any(
        os.getenv(k) for k in ("API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY", "GROQ_API_KEY")
    )
    if not has_api:
        warnings_list.append("No API key found (offline/local-only mode)")
    if warnings_list:
        return _quick_check("environment", True, f"WARNING: {'; '.join(warnings_list)}", start)
    return _quick_check("environment", True, "Environment OK", start)


# ── MOUSE Vanguard checks ─────────────────────────────────────────────────────


def _mouse_home() -> Optional[Path]:
    script_dir = Path(__file__).resolve().parent
    mouse_home = script_dir / ".mouse_vanguard"
    return mouse_home if mouse_home.exists() else None


def check_mouse_config() -> Any:
    """Validate MOUSE Vanguard configuration."""
    start = time.time()
    mouse_home = _mouse_home()
    if mouse_home is None:
        return _quick_check("mouse_config", True, "MOUSE not initialized yet (optional)", start)

    config_path = mouse_home / "config.json"
    if not config_path.exists():
        return _quick_check("mouse_config", True, "WARNING: config.json missing (will use defaults)", start)

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        api_url = cfg.get("api_url", "")
        if not api_url.startswith("http"):
            return _quick_check("mouse_config", False, f"Invalid api_url: {api_url}", start)
        return _quick_check("mouse_config", True, f"api_url={api_url}", start)
    except Exception as e:
        return _quick_check("mouse_config", False, f"Config unreadable: {e}", start)


def check_mouse_ollama() -> Any:
    """Check if MOUSE's configured Ollama endpoint is reachable."""
    start = time.time()
    mouse_home = _mouse_home()
    if mouse_home is None:
        return _quick_check("mouse_ollama", True, "MOUSE not initialized (optional)", start)

    config_path = mouse_home / "config.json"
    url = "http://localhost:11434/api/generate"
    if config_path.exists():
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                url = json.load(f).get("api_url", url)
        except Exception:
            pass

    try:
        from urllib import request
        base = url.rsplit("/", 2)[0] if "/api/" in url else url.rsplit("/", 1)[0]
        req = request.Request(f"{base}/api/tags", method="GET")
        with request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            models = [m["name"] for m in data.get("models", [])]
        msg = f"Reachable. {len(models)} model(s)" + (f": {', '.join(models[:3])}" if models else "")
        return _quick_check("mouse_ollama", True, msg, start)
    except Exception as e:
        return _quick_check("mouse_ollama", False, f"Not reachable ({url}): {e}", start)


def check_mouse_memory() -> Any:
    """Check MOUSE memory store health."""
    start = time.time()
    mouse_home = _mouse_home()
    if mouse_home is None:
        return _quick_check("mouse_memory", True, "MOUSE not initialized (optional)", start)

    mem_dir = mouse_home / "memories"
    if not mem_dir.exists():
        return _quick_check("mouse_memory", True, "WARNING: memory dir missing (will be created)", start)

    try:
        files = list(mem_dir.glob("*.json"))
        total_entries = 0
        for f in files:
            try:
                with open(f, "r", encoding="utf-8") as fh:
                    total_entries += len(json.load(fh))
            except Exception:
                pass
        return _quick_check("mouse_memory", True, f"{len(files)} file(s), {total_entries} entr{'y' if total_entries == 1 else 'ies'}", start)
    except Exception as e:
        return _quick_check("mouse_memory", False, f"Memory check failed: {e}", start)


# ── Helper ────────────────────────────────────────────────────────────────────

def _quick_check(name: str, healthy: bool, message: str, start: float):
    """Build a HealthCheck result with timing."""
    HealthCheck, _ = _import_resilience()
    latency_ms = (time.time() - start) * 1000
    if HealthCheck is None:
        class _Fallback:
            def __init__(self, n, h, m, l):
                self.name = n
                self.healthy = h
                self.message = m
                self.latency_ms = l
                self.timestamp = datetime.now().isoformat()
        return _Fallback(name, healthy, message, latency_ms)
    return HealthCheck(name=name, healthy=healthy, latency_ms=latency_ms, message=message)


# ── Fix helpers ───────────────────────────────────────────────────────────────

def _fix_missing_dirs() -> List[str]:
    """Create missing data directories."""
    DATA_DIR, SQLITE_DIR, CHROMA_DIR = _import_config()
    fixes = []
    for label, path in [("data", DATA_DIR), ("sqlite", SQLITE_DIR), ("chroma", CHROMA_DIR)]:
        if path is None:
            continue
        p = Path(path)
        if not p.exists():
            try:
                p.mkdir(parents=True, exist_ok=True)
                fixes.append(f"Created {label} dir: {p}")
            except Exception as e:
                fixes.append(f"Failed to create {label} dir: {e}")
    return fixes


def _fix_missing_tables() -> List[str]:
    """Trigger subsystem initialization to create missing tables."""
    fixes = []
    try:
        from infj_bot.core.cognitive_architecture import CognitiveArchitecture
        CognitiveArchitecture()
        fixes.append("Initialized cognitive_architecture schema")
    except Exception as e:
        fixes.append(f"cognitive_architecture init failed: {e}")
    try:
        from infj_bot.core.being import get_being
        get_being()
        fixes.append("Initialized being schema")
    except Exception as e:
        fixes.append(f"being init failed: {e}")
    try:
        from infj_bot.core.shadow import get_shadow
        get_shadow()
        fixes.append("Initialized shadow schema")
    except Exception as e:
        fixes.append(f"shadow init failed: {e}")
    try:
        from infj_bot.core.homeostasis import get_homeostasis
        get_homeostasis()
        fixes.append("Initialized homeostasis schema")
    except Exception as e:
        fixes.append(f"homeostasis init failed: {e}")
    return fixes


# ── Main entry point ──────────────────────────────────────────────────────────

def build_runner() -> SelfCheckRunner:
    """Create a runner with all standard checks registered."""
    runner = SelfCheckRunner()
    runner.register("data_directories", check_data_directories)
    runner.register("sqlite_databases", check_sqlite_databases)
    runner.register("required_tables", check_required_tables)
    runner.register("plugin_registry", check_plugin_registry)
    runner.register("being_state", check_being_state)
    runner.register("shadow_state", check_shadow_state)
    runner.register("homeostasis_state", check_homeostasis_state)
    runner.register("chroma_health", check_chroma_health)
    runner.register("disk_space", check_disk_space)
    runner.register("environment", check_environment)
    runner.register("mouse_config", check_mouse_config)
    runner.register("mouse_ollama", check_mouse_ollama)
    runner.register("mouse_memory", check_mouse_memory)
    return runner


def main():
    parser = argparse.ArgumentParser(description="DRIFT comprehensive self-check")
    parser.add_argument("--json", action="store_true", help="Output JSON report")
    parser.add_argument("--format", choices=["text", "json"], default="text", help="Report format")
    parser.add_argument("--fix", action="store_true", help="Attempt to fix minor issues (create dirs, init schemas)")
    parser.add_argument("--verbose", "-v", action="store_true", help="Print per-check progress")
    parser.add_argument("--check", action="append", dest="checks", help="Run only named check(s)")
    parser.add_argument("--list-checks", action="store_true", help="List available checks and exit")
    args = parser.parse_args()

    if args.list_checks:
        runner = build_runner()
        for name in runner._checks:
            print(name)
        sys.exit(0)

    if args.fix:
        print("[Self-Check] Attempting fixes...")
        fixes = _fix_missing_dirs()
        fixes.extend(_fix_missing_tables())
        for f in fixes:
            print(f"  {f}")
        print("")

    runner = build_runner()
    results, severity = runner.run(names=args.checks, verbose=args.verbose)

    fmt = "json" if args.json else args.format
    if fmt == "json":
        print(runner.report_json())
    else:
        print(runner.report_text())

    sys.exit(severity)


if __name__ == "__main__":
    main()
