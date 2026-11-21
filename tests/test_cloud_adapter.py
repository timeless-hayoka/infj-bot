"""Security and production-path tests for the read-only DRIFT cloud adapter."""

import pytest
from drift.core.cloud_adapter import create_app
from fastapi.testclient import TestClient


def test_missing_token_configuration_fails_closed(monkeypatch):
    monkeypatch.delenv("DRIFT_PLUGIN_TOKEN", raising=False)
    with pytest.raises(RuntimeError, match="DRIFT_PLUGIN_TOKEN"):
        create_app()


def test_health_requires_authentication(monkeypatch):
    monkeypatch.setenv("DRIFT_PLUGIN_TOKEN", "test-secret-long-enough")
    client = TestClient(create_app())
    assert client.get("/health").status_code == 401
    assert (
        client.get("/health", headers={"Authorization": "Bearer wrong"}).status_code
        == 401
    )
    response = client.get(
        "/health", headers={"Authorization": "Bearer test-secret-long-enough"}
    )
    assert response.status_code == 200
    assert response.json()["status"] == "ready"


def test_memory_search_reaches_real_production_function(monkeypatch):
    monkeypatch.setenv("DRIFT_PLUGIN_TOKEN", "test-secret-long-enough")
    from drift.core import mcp_server

    observed = []

    def production_search(query, n_results=5):
        observed.append((query, n_results))
        return "[memory]\nVerified result"

    monkeypatch.setattr(mcp_server, "memory_search", production_search)
    client = TestClient(create_app())
    headers = {"Authorization": "Bearer test-secret-long-enough"}
    response = client.post(
        "/memory/search", json={"query": "recovery", "limit": 3}, headers=headers
    )
    assert response.status_code == 200
    assert response.json() == {"result": "[memory]\nVerified result"}
    assert observed == [("recovery", 3)]


def test_memory_search_rejects_invalid_input_and_unauthorized_calls(monkeypatch):
    monkeypatch.setenv("DRIFT_PLUGIN_TOKEN", "test-secret-long-enough")
    client = TestClient(create_app())
    assert client.post("/memory/search", json={"query": "private"}).status_code == 401
    headers = {"Authorization": "Bearer test-secret-long-enough"}
    assert (
        client.post(
            "/memory/search", json={"query": "", "limit": 2}, headers=headers
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/memory/search", json={"query": "x", "limit": 100}, headers=headers
        ).status_code
        == 422
    )


def test_persisted_memory_survives_restart_through_http(tmp_path, monkeypatch):
    """Use actual SQLite/Chroma-backed memory and production MCP search, no search stub."""
    from drift.core import embeddings, mcp_server
    from drift.core.memory import DriftMemory

    # Exercise real storage and retrieval with deterministic offline embeddings.
    monkeypatch.setattr(embeddings, "_global_embedding_function", embeddings.LocalEmbeddingFunction())
    monkeypatch.setenv("DRIFT_PLUGIN_TOKEN", "test-secret-long-enough")
    original_memory = mcp_server.memory
    try:
        first = DriftMemory(persist_directory=str(tmp_path / "isolated_memory"), use_semantic=False)
        first.save_interaction_sync(
            "persistent recovery marker cobalt-heron-427",
            "The recovery evidence is stored.",
        )
        mcp_server.memory = None
        reopened = DriftMemory(persist_directory=str(tmp_path / "isolated_memory"), use_semantic=False)
        mcp_server.memory = reopened
        client = TestClient(create_app())
        response = client.post(
            "/memory/search",
            json={"query": "persistent recovery marker cobalt-heron-427", "limit": 5},
            headers={"Authorization": "Bearer test-secret-long-enough"},
        )
        assert response.status_code == 200, response.text
        assert "cobalt-heron-427" in response.json()["result"]
    finally:
        mcp_server.memory = original_memory
