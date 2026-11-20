from __future__ import annotations

import asyncio
import sqlite3
import subprocess
import threading
from pathlib import Path

import pytest


def test_liveness_does_not_initialize_memory(monkeypatch):
    from drift.interfaces import api

    monkeypatch.setattr(api, "memory", None)

    def unexpected_initialization():
        raise AssertionError("liveness must not initialize semantic memory")

    monkeypatch.setattr(api, "_get_memory", unexpected_initialization)

    payload = api._health_snapshot()

    assert payload["ok"] is True
    assert payload["memory_status"] == "not_initialized"
    assert payload["memory_count"] is None


def test_liveness_does_not_query_initialized_memory(monkeypatch):
    from drift.interfaces import api

    class SlowMemory:
        def count(self):
            raise AssertionError("liveness must not query a persistence backend")

    monkeypatch.setattr(api, "memory", SlowMemory())

    payload = api._health_snapshot()

    assert payload["ok"] is True
    assert payload["memory_status"] == "initialized"
    assert payload["memory_count"] is None


def test_readiness_timeout_does_not_block_event_loop(monkeypatch):
    from drift.interfaces import api

    release = threading.Event()
    worker_daemon_flags = []
    monkeypatch.setattr(api, "memory", None)
    monkeypatch.setattr(
        api, "_memory_readiness_event", threading.Event(), raising=False
    )
    monkeypatch.setattr(api, "_memory_readiness_thread", None, raising=False)
    monkeypatch.setattr(api, "_memory_readiness_error", None, raising=False)

    def blocked_memory_initialization():
        worker_daemon_flags.append(threading.current_thread().daemon)
        release.wait(timeout=0.25)

    monkeypatch.setattr(api, "_get_memory", blocked_memory_initialization)

    async def exercise():
        readiness = asyncio.create_task(api._readiness_snapshot(timeout_s=0.01))
        await asyncio.sleep(0)
        event_loop_remained_responsive = True
        result = await readiness
        release.set()
        return event_loop_remained_responsive, result

    responsive, result = asyncio.run(exercise())

    assert responsive is True
    assert result["ok"] is False
    assert result["memory_status"] == "timeout"
    assert worker_daemon_flags == [True]


def test_repeated_readiness_timeouts_share_one_initializer(monkeypatch):
    from drift.interfaces import api

    release = threading.Event()
    calls = []
    monkeypatch.setattr(api, "memory", None)
    monkeypatch.setattr(
        api, "_memory_readiness_event", threading.Event(), raising=False
    )
    monkeypatch.setattr(api, "_memory_readiness_thread", None, raising=False)
    monkeypatch.setattr(api, "_memory_readiness_error", None, raising=False)

    def blocked_memory_initialization():
        calls.append(threading.get_ident())
        release.wait(timeout=0.25)

    monkeypatch.setattr(api, "_get_memory", blocked_memory_initialization)

    async def exercise():
        first = await api._readiness_snapshot(timeout_s=0.01)
        second = await api._readiness_snapshot(timeout_s=0.01)
        await asyncio.sleep(0.01)
        return first, second

    first, second = asyncio.run(exercise())
    release.set()

    assert first["memory_status"] == second["memory_status"] == "timeout"
    assert len(calls) == 1


def test_memory_write_rolls_back_sqlite_when_vector_write_fails(tmp_path):
    from drift.core.unified_memory import Event, MemoryManager

    manager = object.__new__(MemoryManager)
    manager.db_path = str(tmp_path / "memory.db")
    manager._init_sqlite()

    class FailingCollection:
        def add(self, **_kwargs):
            raise RuntimeError("synthetic vector-store failure")

    manager._collection = FailingCollection()

    with pytest.raises(RuntimeError, match="vector-store failure"):
        manager.remember_sync(Event(type="test", content="rollback me"), {})

    with sqlite3.connect(manager.db_path) as conn:
        count = conn.execute("SELECT COUNT(*) FROM episodic").fetchone()[0]
    assert count == 0


def test_installer_targets_current_anchor_repository():
    from interfaces.cli import _install_plan

    plan = _install_plan("laptop")

    assert plan["steps"][:2] == [
        "git clone --branch anchor --single-branch https://github.com/timeless-hayoka/infj-bot.git",
        "cd infj-bot",
    ]


def test_doctor_fixes_use_runtime_paths(monkeypatch, tmp_path):
    from interfaces import cli

    monkeypatch.setattr(cli.Path, "home", lambda: tmp_path)
    checks = [
        {"name": "Launcher", "ok": False},
        {"name": "Python", "ok": False},
        {"name": "Bash completion", "ok": False},
    ]

    fixes = cli._doctor_fixes(checks, ["drift.core.brain"], ["prometheus_client"])
    rendered = "\n".join(
        f"{fix.get('summary', '')}\n{fix.get('command', '')}" for fix in fixes
    )

    assert "/home/crexs" not in rendered
    assert str(cli.PROJECT_ROOT) in rendered
    assert str(tmp_path / ".local") in rendered


def test_persistence_defaults_use_canonical_sqlite_directory():
    from drift.core.unified_memory import default_memory_db_path

    from drift import config_adapter
    from drift.core import homeostasis

    assert Path(homeostasis.HOMEOSTASIS_DB) == Path(config_adapter.HOMEOSTASIS_DB)
    assert default_memory_db_path() == config_adapter.SQLITE_DIR / "unified_memory.db"


def test_cognitive_architecture_connection_closes_after_context(tmp_path):
    from drift.core.cognitive_architecture import _sqlite_connection

    with _sqlite_connection(str(tmp_path / "architecture.db")) as conn:
        conn.execute("CREATE TABLE state (value TEXT)")

    with pytest.raises(sqlite3.ProgrammingError, match="closed database"):
        conn.execute("SELECT * FROM state")


def test_legacy_sqlite_migration_never_overwrites_canonical_data(tmp_path):
    from drift.config_adapter import migrate_legacy_sqlite_database

    legacy = tmp_path / "legacy.db"
    canonical = tmp_path / "sqlite" / "canonical.db"
    with sqlite3.connect(legacy) as conn:
        conn.execute("CREATE TABLE state (value TEXT)")
        conn.execute("INSERT INTO state VALUES ('legacy')")

    assert migrate_legacy_sqlite_database(legacy, canonical) is True
    with sqlite3.connect(canonical) as conn:
        assert conn.execute("SELECT value FROM state").fetchone()[0] == "legacy"

    with sqlite3.connect(canonical) as conn:
        conn.execute("UPDATE state SET value = 'canonical'")
    assert migrate_legacy_sqlite_database(legacy, canonical) is False
    with sqlite3.connect(canonical) as conn:
        assert conn.execute("SELECT value FROM state").fetchone()[0] == "canonical"


def test_checked_in_deployment_files_are_host_portable():
    root = Path(__file__).resolve().parents[1]
    compose = (root / "docker-compose.yml").read_text(encoding="utf-8")
    cursor = (root / ".cursor/mcp.json").read_text(encoding="utf-8")
    web_app = (root / "interfaces/web_app.py").read_text(encoding="utf-8")

    for text in (compose, cursor, web_app):
        assert "/home/crexs" not in text
        assert "/media/crexs" not in text

    assert "your-project:region:drift-db" not in compose


def test_runtime_logs_default_to_canonical_log_directory():
    import inspect

    from drift.core.cognitive_governor import CognitiveGovernor

    from drift import config_adapter
    from drift.core import brain, security_defense, trajectory

    expected = config_adapter.LOGS_DIR.resolve()

    assert security_defense.SECURITY_AUDIT_PATH.parent.resolve() == expected
    assert brain._traj_logger.log_path.parent.resolve() == expected
    trace_default = (
        inspect.signature(trajectory.StateTrajectoryLogger)
        .parameters["log_path"]
        .default
    )
    assert Path(trace_default).parent.resolve() == expected
    assert CognitiveGovernor()._calibration_log.parent.resolve() == expected


def test_quality_checks_and_npm_test_are_real_gates():
    root = Path(__file__).resolve().parents[1]
    quality = (root / ".github/workflows/quality.yml").read_text(encoding="utf-8")
    package = (root / "package.json").read_text(encoding="utf-8")

    assert "bandit -r . -f json -o bandit-report.json || true" not in quality
    assert (
        "detect-secrets scan --baseline .secrets.baseline --all-files . || true"
        not in quality
    )
    assert "--warn-redundant-casts || true" not in quality
    assert '"test": "echo \\"Error: no test specified\\" && exit 1"' not in package


def test_github_contribution_timeout_returns_unavailable(monkeypatch):
    from drift.trinity import http_api

    calls = []
    monkeypatch.setattr(http_api.shutil, "which", lambda _command: "/usr/bin/gh")

    def timeout(command, **_kwargs):
        calls.append(command)
        raise subprocess.TimeoutExpired(command, timeout=0.01)

    monkeypatch.setattr(http_api.subprocess, "run", timeout)

    snapshot = http_api._github_contribution_snapshot()

    assert snapshot["source"] == "unavailable"
    assert snapshot["open_prs"] == 0
    assert snapshot["merged_prs"] == 0
    assert snapshot["issues_filed"] == 0
    assert len(calls) == 1


def test_github_contribution_command_failure_returns_unavailable(monkeypatch):
    from types import SimpleNamespace

    from drift.trinity import http_api

    calls = []
    monkeypatch.setattr(http_api.shutil, "which", lambda _command: "/usr/bin/gh")

    def failed(command, **_kwargs):
        calls.append(command)
        return SimpleNamespace(returncode=1, stdout="", stderr="not authenticated")

    monkeypatch.setattr(http_api.subprocess, "run", failed)

    snapshot = http_api._github_contribution_snapshot()

    assert snapshot["source"] == "unavailable"
    assert len(calls) == 1
