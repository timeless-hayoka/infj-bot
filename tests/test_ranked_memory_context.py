"""Ensure ranked recall delivers canonical text and excludes stale vectors."""

import sqlite3

from drift.core.causal_wiring import retrieved_memory_keys_var
from drift.core.dmu import DMURetriever
from drift.core.memory import DriftMemory


def test_ranked_documents_reach_prompt_context(tmp_path, monkeypatch):
    memory = DriftMemory(persist_directory=str(tmp_path))
    memory.save_interaction_sync("synthetic question", "canonical response")
    memory.save_interaction_sync("forgotten question", "forgotten response")
    records = memory.unified_manager.get_recent_sync("interaction")
    stale, kept = [entry.unified_id for entry in records]
    with sqlite3.connect(memory.unified_manager.db_path) as conn:
        conn.execute("DELETE FROM episodic WHERE unified_id = ?", (stale,))
    monkeypatch.setattr(memory, "retrieve_context", lambda *_a, **_kw: "fallback")
    monkeypatch.setattr(
        DMURetriever,
        "retrieve",
        lambda *_a, **_kw: [
            {"id": stale, "document": "forgotten text"},
            {"id": kept, "document": "obsolete vector text"},
        ],
    )

    assert memory.retrieve_context_ranked("synthetic query") == (
        "Memory: user: synthetic question\nBot: canonical response"
    )
    assert retrieved_memory_keys_var.get() == [kept]
