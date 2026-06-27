from __future__ import annotations

from types import SimpleNamespace

import pytest

from core.mcp_security import McpSecurityGuard


def test_mcp_security_guard_auth_and_rate_limit():
    guard = McpSecurityGuard(
        expected_token="secret-token",
        rate_limit_defaults={"default": (1, 60)},
    )

    principal = guard.authenticate(token="secret-token", source="http:test")
    assert principal.identity

    first = guard.check_rate_limit(principal, "todo_list")
    second = guard.check_rate_limit(principal, "todo_list")

    assert first.allowed is True
    assert second.allowed is False
    assert second.retry_after_seconds >= 0


def test_http_bridge_status_and_metrics(monkeypatch):
    from fastapi.testclient import TestClient
    from core.mcp_server import create_http_app

    app = create_http_app(token=None)
    client = TestClient(app)

    fake_being = SimpleNamespace(
        state=SimpleNamespace(
            pedi=SimpleNamespace(value=1.25),
            dii=SimpleNamespace(value=0.75),
            energy=0.5,
        )
    )
    monkeypatch.setattr("core.mcp_server.get_being", lambda: fake_being)

    status = client.get("/status")
    assert status.status_code == 200
    assert status.json()["auth_mode"] == "open"

    metrics = client.get("/metrics")
    assert metrics.status_code == 200
    assert metrics.headers["content-type"].startswith("text/plain")
