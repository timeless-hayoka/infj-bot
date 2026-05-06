from fastapi.testclient import TestClient

from mcp_server import create_http_app


def test_health():
    client = TestClient(create_http_app())
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json().get("status") == "ok"


def test_emotional_clarity():
    client = TestClient(create_http_app())
    r = client.post("/invoke/emotional_clarity", json={"args": ["I'm feeling anxious and tired."]})
    assert r.status_code == 200
    result = r.json().get("result")
    assert result is not None
    assert "Emotional reading" in result


def test_dissonance_map():
    client = TestClient(create_http_app())
    r = client.post("/invoke/dissonance_map", json={"args": ["I want to move but I'm afraid of losing stability."]})
    assert r.status_code == 200
    assert isinstance(r.json().get("result"), str)
