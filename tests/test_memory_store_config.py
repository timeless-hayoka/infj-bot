from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


def load_module(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / filename)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.path.insert(0, str(SCRIPTS))
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


memory_store_config = load_module("memory_store_config", "memory_store_config.py")


def test_get_config_reads_env(monkeypatch):
    monkeypatch.setenv("DRIFT_CHROMA_PERSIST_DIR", "/tmp/test-chroma")
    monkeypatch.setenv("DRIFT_MEMORY_COLLECTION", "bench_memory")
    monkeypatch.setenv("DRIFT_EMBEDDING_MODEL", "all-MiniLM-L6-v2")
    monkeypatch.setenv("DRIFT_DEFAULT_N_RESULTS", "25")

    cfg = memory_store_config.get_config()
    assert cfg.persist_directory == "/tmp/test-chroma"
    assert cfg.collection_name == "bench_memory"
    assert cfg.default_n_results == 25


def test_reset_chroma_store_clears_singleton(monkeypatch):
    memory_store_config.reset_chroma_store()

    class FakeStore:
        pass

    created = []

    def fake_chroma_store(**kwargs):
        created.append(kwargs)
        return FakeStore()

    chromadb_integration_hooks = load_module("chromadb_integration_hooks", "chromadb_integration_hooks.py")
    monkeypatch.setattr(chromadb_integration_hooks, "ChromaMemoryStore", fake_chroma_store)

    first = memory_store_config.get_chroma_store()
    second = memory_store_config.get_chroma_store()
    assert first is second
    assert len(created) == 1

    memory_store_config.reset_chroma_store()
    third = memory_store_config.get_chroma_store()
    assert third is not first
    assert len(created) == 2

    memory_store_config.reset_chroma_store()
