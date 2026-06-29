"""Tests for Being spark train persistence (companion layer, off by default in ANCHOR mode)."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def spark_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("DRIFT_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DRIFT_COMPANION_ENABLED", "1")
    return tmp_path


def test_spark_history_round_trip(spark_env: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("DRIFT_OS_ROOT", str(spark_env))
    monkeypatch.setattr("drift.core.being.DATA_DIR", spark_env)

    from drift.core.being import Being, SparkTrain

    being = Being()
    train = SparkTrain(being)
    train.spark_history.append({"impulse": "test insight", "score": 0.7})
    train._save_spark_history()

    path = spark_env / "spark_history.json"
    assert path.is_file()
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, list)
    assert payload[-1]["impulse"] == "test insight"

    reloaded = SparkTrain(being)
    assert reloaded.spark_history
    assert reloaded.spark_history[-1]["impulse"] == "test insight"
