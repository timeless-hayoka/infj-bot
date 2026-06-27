from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_sync_logs():
    module_path = Path(__file__).resolve().parents[1] / "scripts" / "sync_logs.py"
    spec = importlib.util.spec_from_file_location("sync_logs", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_default_host_prefers_env_over_ssh_alias(tmp_path, monkeypatch):
    sync_logs = _load_sync_logs()
    ssh_dir = tmp_path / ".ssh"
    ssh_dir.mkdir()
    (ssh_dir / "config").write_text("Host droplet\n    HostName 203.0.113.10\n", encoding="utf-8")
    monkeypatch.setenv("DROPLET_HOST", "env-droplet")
    monkeypatch.setattr(sync_logs.Path, "home", lambda: tmp_path)
    assert sync_logs._default_host() == "env-droplet"


def test_default_host_falls_back_to_ssh_alias(tmp_path, monkeypatch):
    sync_logs = _load_sync_logs()
    ssh_dir = tmp_path / ".ssh"
    ssh_dir.mkdir()
    (ssh_dir / "config").write_text("Host droplet\n    HostName 203.0.113.10\n", encoding="utf-8")
    monkeypatch.delenv("DROPLET_HOST", raising=False)
    monkeypatch.delenv("DROPLET_SSH_HOST", raising=False)
    monkeypatch.delenv("SSH_HOST", raising=False)
    monkeypatch.setattr(sync_logs.Path, "home", lambda: tmp_path)
    assert sync_logs._default_host() == "droplet"
