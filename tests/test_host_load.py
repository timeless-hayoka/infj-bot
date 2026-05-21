"""Tests for host_load sampling and stress mapping."""

import os

from infj_bot.core.host_load import stress_from_cpu_mem, sample_host_load


def test_stress_mapping():
    assert stress_from_cpu_mem(0.0, 0.0) == 0.0
    assert stress_from_cpu_mem(100.0, 100.0) == 1.0
    mid = stress_from_cpu_mem(50.0, 50.0)
    assert 0.4 < mid < 0.6


def test_sample_returns_shape():
    os.environ.pop("INFJ_DISABLE_HOST_LOAD", None)
    sample_host_load(force=True)
    s = sample_host_load(force=True)
    assert "ok" in s
    assert "stress" in s
    if s.get("ok"):
        assert 0.0 <= s["stress"] <= 1.0
        assert s.get("cpu_percent") is not None


def test_disabled_env():
    os.environ["INFJ_DISABLE_HOST_LOAD"] = "1"
    try:
        out = sample_host_load(force=True)
        assert out.get("ok") is False
        assert out.get("reason") == "disabled"
    finally:
        os.environ.pop("INFJ_DISABLE_HOST_LOAD", None)
