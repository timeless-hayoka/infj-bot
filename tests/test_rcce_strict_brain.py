"""RCCE strict mode must not convert provider failures into scored answers.

Uses the real DriftBrain.think implementation with provider boundaries stubbed.
These are offline regression tests, NOT live-provider validation.
"""

from types import SimpleNamespace

import pytest

from drift.core import brain as brain_module
from drift.core.brain import DriftBrain


def _brain(monkeypatch, *, primary_fails=False, critic_fails=False):
    monkeypatch.setattr(brain_module, "DRIFT_USE_HF", False)
    monkeypatch.setattr(
        brain_module,
        "get_being",
        lambda: SimpleNamespace(state=SimpleNamespace(energy=1)),
    )
    bot = DriftBrain.__new__(DriftBrain)
    bot.sdk = "google.genai"
    bot.primary_model_name = "primary"
    bot.critic_model_name = "critic"
    bot.history = []
    bot._max_history = 6
    bot.scope = None
    bot.logger = SimpleNamespace(
        warning=lambda *a, **k: None, exception=lambda *a, **k: None
    )
    bot.chain_navigator = SimpleNamespace(
        get_prompt_block=lambda q: "",
        record_step=lambda **kw: None,
    )
    bot._enhanced_security_check = lambda *a, **k: SimpleNamespace(
        blocked=False, warn=False
    )
    bot.get_system_instruction = lambda q: "system"
    bot._current_request_budget = lambda: None
    bot._offline_fallback = lambda q, exc: "OFFLINE FALLBACK"

    def generate(model, *args, **kwargs):
        if (model == "primary" and primary_fails) or (
            model == "critic" and critic_fails
        ):
            raise ConnectionError("provider unavailable")
        return "primary answer" if model == "primary" else "critic-approved answer"

    bot._generate = generate
    return bot


def test_strict_mode_rejects_primary_provider_fallback(monkeypatch):
    bot = _brain(monkeypatch, primary_fails=True)
    assert bot.think("task") == "OFFLINE FALLBACK"
    with pytest.raises(RuntimeError, match="RCCE_INVALID: primary"):
        bot.think("task", rcce_strict=True)


def test_strict_mode_rejects_critic_unavailable_suffix(monkeypatch):
    bot = _brain(monkeypatch, critic_fails=True)
    assert "[critic unavailable:" in bot.think("task")
    with pytest.raises(RuntimeError, match="RCCE_INVALID: critic"):
        bot.think("task", rcce_strict=True)


def test_strict_mode_preserves_successful_production_route(monkeypatch):
    bot = _brain(monkeypatch)
    assert bot.think("task", rcce_strict=True) == "critic-approved answer"
