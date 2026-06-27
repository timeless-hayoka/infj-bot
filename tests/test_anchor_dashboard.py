from __future__ import annotations

import importlib
from pathlib import Path

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient

import interfaces.api as api_mod
from interfaces.api import app


def test_anchor_dashboard_renders_connected_panels() -> None:
    with TestClient(app) as client:
        response = client.get('/anchor')

    assert response.status_code == 200
    body = response.text
    for label in (
        'Release',
        'History',
        'Evidence Metrics',
        'Vault Visibility',
        'Contribution Tracking',
        'Observer',
    ):
        assert label in body
    assert '{{ANCHOR_RELEASE}}' not in body


def test_trinity_paths_endpoint_exposes_archive_paths() -> None:
    with TestClient(app) as client:
        response = client.get('/api/trinity/paths')

    assert response.status_code == 200
    data = response.json()
    assert 'cases_dir' in data
    assert 'ledger_path' in data
    assert 'logs_dir' in data



def test_anchor_snapshot_endpoint_exposes_combined_cockpit_payload() -> None:
    with TestClient(app) as client:
        response = client.get('/api/anchor/snapshot?limit=5')

    assert response.status_code == 200
    data = response.json()
    for key in ('identity', 'health', 'phi', 'paths', 'history', 'metrics', 'vault', 'contributions', 'observer'):
        assert key in data
    assert data['identity']['product'] == 'ANCHOR'
    assert 'cases_dir' in data['paths']
    assert 'runs' in data['history']
    assert 'claims_generated' in data['metrics']


def test_anchor_hunt_requires_login_and_unlocked_console_contains_updated_panels(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    secret_path = tmp_path / 'hunt_passphrase'
    monkeypatch.delenv('ANCHOR_HUNT_PASSWORD', raising=False)
    monkeypatch.setenv('ANCHOR_HUNT_SECRET_PATH', str(secret_path))
    monkeypatch.setenv('ANCHOR_HUNT_SESSION', 'unit-test-session')
    module = importlib.reload(api_mod)

    with TestClient(module.app) as client:
        locked = client.get('/anchor/hunt')
        assert locked.status_code == 200
        assert 'Enter the local passphrase' in locked.text
        assert 'Boot Sequence' not in locked.text

        generated = secret_path.read_text(encoding='utf-8').strip()
        assert generated

        bad = client.post('/anchor/hunt/login', json={'password': 'wrong'})
        assert bad.status_code == 401

        good = client.post('/anchor/hunt/login', json={'password': generated})
        assert good.status_code == 200
        cookie = good.headers.get('set-cookie', '')
        assert 'HttpOnly' in cookie
        assert 'SameSite=strict' in cookie or 'SameSite=Strict' in cookie

        unlocked = client.get('/anchor/hunt')
        assert unlocked.status_code == 200
        body = unlocked.text
        for label in ('Boot Sequence', 'Recon Feed', 'CVSS Calculator', 'Trinity Chat', 'Evidence & Provenance'):
            assert label in body
        assert 'TOOL UNAVAILABLE / NOT TESTED' in body

        session = client.get('/api/anchor/session')
        assert session.status_code == 200
        assert session.json()['authenticated'] is True

        chat = client.post('/api/trinity/chat', json={'message': 'summarize the run'})
        assert chat.status_code == 200
        reply = chat.json()['reply']
        assert 'ANCHOR' in reply
        assert 'plausible claim is not a finding' in reply.lower()

        rubric = client.post('/api/trinity/chat', json={'message': 'help me evaluate this finding'})
        assert rubric.status_code == 200
        rubric_reply = rubric.json()['reply']
        assert 'Scope, Mechanism, Reproduction, Impact, Next Step' in rubric_reply
        assert 'reproduced_real' in rubric_reply


def test_trinity_run_events_stream_is_case_scoped_and_read_only(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    secret_path = tmp_path / 'hunt_passphrase'
    monkeypatch.delenv('ANCHOR_HUNT_PASSWORD', raising=False)
    monkeypatch.setenv('ANCHOR_HUNT_SECRET_PATH', str(secret_path))
    monkeypatch.setenv('ANCHOR_HUNT_SESSION', 'unit-test-session-stream')
    module = importlib.reload(api_mod)

    with TestClient(module.app) as client:
        cases = client.get('/api/trinity/cases?limit=1').json()['cases']
        assert cases
        run_id = cases[0]['case_id']
        with client.stream('GET', f'/api/trinity/runs/{run_id}/events') as stream:
            chunks = list(stream.iter_lines())

    joined = '\n'.join(chunk.decode() if isinstance(chunk, bytes) else chunk for chunk in chunks if chunk)
    assert 'schema_version' in joined
    assert run_id in joined
    assert 'case_id' in joined
    assert 'event_type' in joined
    assert 'artifact_refs' in joined
