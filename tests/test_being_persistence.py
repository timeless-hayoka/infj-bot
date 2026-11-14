"""Regression tests for live state in prompts and snapshots."""

import json
import sqlite3

import pytest
from drift.core.being import Being
from drift.core.cognitive_architecture import CognitiveArchitecture, LoopStep

from drift.core import being_snapshot, embodiment, homeostasis


@pytest.fixture
def live_state(tmp_path, monkeypatch):
    monkeypatch.setattr(embodiment, "BODY_DB", tmp_path / "body.db")
    monkeypatch.setattr(homeostasis, "HOMEOSTASIS_DB", tmp_path / "needs.db")
    monkeypatch.setattr(homeostasis, "_homeostasis_instance", None)
    if hasattr(embodiment, "_embodiment_instance"):
        monkeypatch.setattr(embodiment, "_embodiment_instance", None)
    arch = CognitiveArchitecture()
    for name in ("embodiment", "homeostasis"):
        monkeypatch.setattr(arch.get_plugin(name), "instance", None)
    body = LoopStep(arch.get_plugin("embodiment")).instance
    regulator = homeostasis.get_homeostasis()
    return Being(tmp_path / "being.db"), body, regulator


def test_prompt_uses_live_body_and_regulator(live_state):
    being, body, regulator = live_state
    body.state.heartbeat_rate = 93
    regulator.needs["connection"].current = 0.07

    prompt = being.format_being_prompt()

    assert "Heartbeat: 93" in prompt
    assert "connection: 7%" in prompt


def test_snapshot_writes_live_numeric_needs(live_state, monkeypatch, tmp_path):
    being, _, regulator = live_state
    path = tmp_path / "snapshots.db"
    monkeypatch.setattr(
        being_snapshot, "_writer", being_snapshot.CognitiveSnapshotWriter(path)
    )
    regulator.needs["coherence"].current = 0.23
    regulator.needs["integration"].current = 0.31
    regulator.needs["energy"].current = 0.12

    being.evolve(interaction_happened=True)

    with sqlite3.connect(path) as conn:
        coherence, integration, energy, raw = conn.execute(
            "SELECT coherence, context_integrity, energy, raw_json FROM cognitive_snapshots"
        ).fetchone()
    assert (coherence, integration) == pytest.approx((0.23, 0.31))
    assert energy == pytest.approx(being.state.energy)
    assert json.loads(raw)["coherence"] == pytest.approx(0.23)


def test_optional_state_error_reports_type_without_sensitive_detail(
    live_state, monkeypatch, caplog
):
    being, _, _ = live_state

    def fail():
        raise sqlite3.OperationalError("synthetic private state value")

    monkeypatch.setattr(homeostasis, "get_homeostasis", fail)
    assert "Sense of self" in being.format_being_prompt()
    assert "Homeostasis state unavailable for prompt (OperationalError)" in caplog.text
    assert "synthetic private state value" not in caplog.text
