from __future__ import annotations

import importlib
import json
import stat
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient


def load_server(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    key_path = tmp_path / "anchor_signing_key.pem"
    monkeypatch.setenv("ANCHOR_SIGNING_KEY_PATH", str(key_path))
    monkeypatch.setenv("ANCHOR_PROJECT_ROOT", "/home/crexs/infj_bot")
    module = importlib.import_module("anchor_server")
    return importlib.reload(module)


def parse_sse_events(lines):
    events = []
    for line in lines:
        if isinstance(line, bytes):
            line = line.decode()
        if line.startswith("data: "):
            events.append(json.loads(line.removeprefix("data: ")))
    return events


def test_anchor_server_demo_run_streams_and_signs(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    server = load_server(monkeypatch, tmp_path)
    assert stat.S_IMODE(Path(server.SIGNING_KEY_PATH).stat().st_mode) == 0o600

    with TestClient(server.app) as client:
        root = client.get("/")
        assert root.status_code == 200
        assert root.json()["service"] == "anchor"

        pubkey = client.get("/pubkey")
        assert pubkey.status_code == 200
        assert pubkey.json()["algorithm"] == "ed25519"

        started = client.post("/runs", json={"mode": "demo"})
        assert started.status_code == 200
        run_id = started.json()["run_id"]

        with client.stream("GET", f"/runs/{run_id}/events") as stream:
            events = parse_sse_events(stream.iter_lines())

        types = [event["type"] for event in events]
        assert "run.started" in types
        assert "case.started" in types
        assert "stage.started" in types
        assert "finding.detected" in types
        assert "finding.correlated" in types
        assert "poc.result" in types
        assert "case.completed" in types
        assert "run.completed" in types
        assert types.index("run.started") < types.index("case.started") < types.index("finding.detected") < types.index("finding.correlated") < types.index("poc.result") < types.index("case.completed") < types.index("run.completed")

        evidence = client.post("/evidence/sign", json={"bundle": {"schema_version": "1.0", "kind": "anchor.evidence_bundle", "case_id": "demo"}})
        assert evidence.status_code == 200
        signed = evidence.json()["signed_bundle"]
        assert signed["signature"]["status"] == "SIGNED"
        assert signed["integrity"]["algorithm"] == "SHA-256"
        assert len(signed["integrity"]["digest"]) == 64
        assert signed["public_key"] == pubkey.json()["public_key"]


def test_anchor_server_replays_after_cursor_and_ingests_events(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    server = load_server(monkeypatch, tmp_path)

    with TestClient(server.app) as client:
        started = client.post("/runs", json={"mode": "demo"})
        run_id = started.json()["run_id"]

        with client.stream("GET", f"/runs/{run_id}/events") as stream:
            all_events = parse_sse_events(stream.iter_lines())

        assert len(all_events) >= 2
        first_event_id = all_events[0]["event_id"]
        second_event_id = all_events[1]["event_id"]

        with client.stream("GET", f"/runs/{run_id}/events?after={first_event_id}") as stream:
            replayed = parse_sse_events(stream.iter_lines())

        assert replayed
        assert replayed[0]["event_id"] == second_event_id
        assert replayed[0]["event_id"] != first_event_id

        ingest = client.post(
            f"/runs/{run_id}/ingest",
            json={"type": "case.started", "payload": {"case_id": "case_live", "contract": "Demo", "expected": ["SWC-107"]}},
        )
        assert ingest.status_code == 200

        case = client.get("/cases/case_live")
        assert case.status_code == 200
        assert case.json()["case_id"] == "case_live"
