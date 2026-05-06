from fastapi.testclient import TestClient

from mcp_server import create_http_app


def test_autonomy_plan():
    token = "test-token"
    client = TestClient(create_http_app(token=token))
    plan = [
        {"tool": "emotional_clarity", "args": ["I'm nervous about an interview."]},
        {"tool": "dissonance_map", "args": ["I want the promotion but worry about time."]},
    ]
    r = client.post("/autonomy", json={"plan": plan}, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    data = r.json()
    assert "results" in data
    assert isinstance(data["results"], list)
    assert data["results"][0]["tool"] == "emotional_clarity"
