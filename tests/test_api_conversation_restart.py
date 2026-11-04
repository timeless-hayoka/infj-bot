"""HTTP conversation smoke test through DRIFT's real /api/chat endpoint.

A deterministic provider double avoids network/API costs. Prompt assembly, SQLite
preferences and persistent memory use production implementations in isolated state.
This does NOT certify live provider availability or natural-language memory recall.
"""

from fastapi.testclient import TestClient

from drift.core.commands import BotState
from drift.core.embeddings import LocalEmbeddingFunction
from drift.core.memory import DriftMemory
from drift.core.plugins.preferences import PreferenceStore


class RecordingProvider:
    def __init__(self):
        self.prompts = []

    def agent_turn(self, prompt, **kwargs):
        self.prompts.append(prompt)
        return "DRIFT_ACK"

    def evaluate_last(self, *args, **kwargs):
        return None


def test_chat_request_persists_and_uses_updated_preferences_after_restart(
    monkeypatch, tmp_path
):
    from drift.interfaces import api

    db = tmp_path / "preferences.db"
    memory_dir = tmp_path / "memory"
    prefs = PreferenceStore(db)
    prefs.promote_preference("response_mode", "concise")
    memory = DriftMemory(
        persist_directory=str(memory_dir),
        embedding_function=LocalEmbeddingFunction(),
        use_semantic=False,
    )
    provider = RecordingProvider()
    monkeypatch.setattr(api, "_get_brain", lambda: provider)
    monkeypatch.setattr(api, "_get_memory", lambda: memory)
    monkeypatch.setattr(api, "_get_doc_store", lambda: None)
    monkeypatch.setattr(api, "state", BotState(prefs=prefs))

    with TestClient(api.app) as client:
        first = client.post("/api/chat", json={"message": "Explain DNS."})
    assert first.status_code == 200, first.text
    assert first.json()["reply"] == "DRIFT_ACK"
    assert "[CONSTRAINT] response_mode=concise" in provider.prompts[0]
    assert memory.count() >= 1

    # Reopen the real SQLite store and persistent memory: simulated restart.
    restarted_prefs = PreferenceStore(db)
    restarted_prefs.promote_preference("response_mode", "detailed")
    restarted_memory = DriftMemory(
        persist_directory=str(memory_dir),
        embedding_function=LocalEmbeddingFunction(),
        use_semantic=False,
    )
    assert restarted_memory.count() >= 1
    monkeypatch.setattr(api, "_get_memory", lambda: restarted_memory)
    monkeypatch.setattr(api, "state", BotState(prefs=restarted_prefs))

    with TestClient(api.app) as client:
        followup = client.post("/api/chat", json={"message": "Explain it again."})
    assert followup.status_code == 200, followup.text
    assert followup.json()["reply"] == "DRIFT_ACK"
    assert "[CONSTRAINT] response_mode=detailed" in provider.prompts[-1]
    assert "[CONSTRAINT] response_mode=concise" not in provider.prompts[-1]
    assert restarted_memory.count() >= 2
