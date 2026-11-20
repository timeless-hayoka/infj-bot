from __future__ import annotations

import json
from pathlib import Path

from drift.automation.mouse import v2 as mouse


def test_boot_uses_configured_file_size_limit(monkeypatch, tmp_path: Path) -> None:
    captured: dict[str, int] = {}

    def detect(*, max_files: int, max_size: int) -> mouse.ProjectContext:
        captured.update(max_files=max_files, max_size=max_size)
        return mouse.ProjectContext()

    monkeypatch.setattr(mouse.ProjectContext, "detect", detect)
    monkeypatch.setattr(mouse, "_get_hardware_diag", dict)
    config = mouse.PortableConfig(tmp_path / "config.json")
    config.data.update(max_project_files=7, max_file_size=1234)

    mouse.SymbioticAI(mouse.MemoryStore(tmp_path / "memory"), config)

    assert captured == {"max_files": 7, "max_size": 1234}


def test_memory_paths_do_not_collapse_distinct_projects(tmp_path: Path) -> None:
    store = mouse.MemoryStore(tmp_path)

    assert store._memory_path("/a/b") != store._memory_path("/ab")


def test_sync_export_stays_inside_sync_directory(monkeypatch, tmp_path: Path) -> None:
    sync_dir = tmp_path / "sync"
    sync_dir.mkdir()
    monkeypatch.setattr(mouse, "SYNC_DIR", sync_dir)
    store = mouse.MemoryStore(tmp_path / "memory")
    store.current_project = "../outside"

    exported = Path(store.export_sync()).resolve()

    assert exported.parent == sync_dir.resolve()
    assert exported.is_file()


def test_git_status_redacts_credentials_from_remote_urls(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(mouse, "_find_git_root", lambda *_args, **_kwargs: tmp_path)

    def run(command: list[str], **_kwargs):
        if command[:2] == ["git", "remote"]:
            return (
                0,
                "origin\thttps://alice:secret@example.com/org/repo.git (fetch)\n",  # pragma: allowlist secret
                "",
            )
        if command[:2] == ["git", "status"]:
            return 0, "", ""
        if command[:2] == ["git", "log"]:
            return 0, "abc123 test", ""
        return 0, "main", ""

    monkeypatch.setattr(mouse, "_run_shell", run)

    status = mouse._get_git_status()
    rendered = json.dumps(status)

    assert "secret" not in rendered
    assert "alice" not in rendered
    assert "https://example.com/org/repo.git" in rendered


def test_legacy_memory_migration_does_not_duplicate_items(tmp_path: Path) -> None:
    memory_dir = tmp_path / "memory"
    memory_dir.mkdir()
    legacy_item = mouse.MemoryItem(
        timestamp=1.0,
        category="note",
        content="legacy",
        project="/a/b",
    )
    (memory_dir / "ab.json").write_text(
        json.dumps([legacy_item.to_dict()]), encoding="utf-8"
    )
    store = mouse.MemoryStore(memory_dir)
    store.current_project = "/a/b"
    store.add("note", "new")

    restarted = mouse.MemoryStore(memory_dir)

    assert [item.content for item in restarted.items] == ["legacy", "new"]


def test_generation_failures_are_not_saved_as_memory(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        mouse.ProjectContext, "detect", lambda **_kwargs: mouse.ProjectContext()
    )
    monkeypatch.setattr(mouse, "_get_hardware_diag", dict)
    config = mouse.PortableConfig(tmp_path / "config.json")
    store = mouse.MemoryStore(tmp_path / "memory")
    assistant = mouse.SymbioticAI(store, config)

    class FailingClient:
        def generate(self, *_args, **_kwargs) -> str:
            return "[ERROR] Ollama request failed. Details: unavailable"

    assistant.client = FailingClient()

    response = assistant.chat("Help me debug this")

    assert response.startswith("[ERROR]")
    assert store.items == []
