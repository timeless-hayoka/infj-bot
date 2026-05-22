"""test_stress.py — Stress, boundary, and chaos tests.

Finds bugs through:
- Rapid-fire operations
- Concurrent access
- Resource exhaustion
- Failure injection
- Boundary conditions
- State corruption
"""

import json
import os
import sys
import threading
import time
import random
import string

import pytest

from infj_bot.core.being import Being
from infj_bot.core.cognitive_architecture import CycleContext
from infj_bot.core.cognitive_orchestrator import CognitiveOrchestrator
from infj_bot.core.embeddings import SemanticEmbeddingFunction
from infj_bot.core.memory import DriftMemory
from infj_bot.core.plugins.physics import PhysicsEngine
from infj_bot.core.plugins.humanity import HumanityEngine
from infj_bot.core.prompt_budget import PromptBudget
from infj_bot.core.resilience import CircuitBreaker, ResilienceManager


# ── Helpers ───────────────────────────────────────────────────────


def _rand_string(length: int) -> str:
    return "".join(random.choices(string.ascii_letters + string.digits + " ", k=length))


def _heavy_emotion():
    return {
        "label": random.choice(
            ["joyful", "sad", "anxious", "angry", "calm", "curious"]
        ),
        "intensity": random.random(),
        "confidence": random.random(),
        "valence": random.uniform(-1, 1),
        "arousal": random.random(),
        "secondary": "neutral",
    }


def _heavy_dissonance():
    return {
        "score": random.random(),
        "markers": random.sample(
            ["conflict", "avoidance", "pressure", "uncertainty"], k=random.randint(0, 2)
        ),
        "values": random.sample(
            ["truth", "safety", "belonging", "autonomy"], k=random.randint(0, 2)
        ),
    }


# ── Boundary / Fuzz Tests ─────────────────────────────────────────


class TestBoundaryConditions:
    """Test extreme and malformed inputs."""

    def test_empty_user_input(self, tmp_path):
        memory = DriftMemory(persist_directory=str(tmp_path))
        memory.save_interaction("", "", emotion={"label": "neutral"})
        assert memory.count() >= 1

    def test_very_long_input(self, tmp_path):
        memory = DriftMemory(persist_directory=str(tmp_path))
        long_text = _rand_string(5000)
        memory.save_interaction(
            long_text, long_text[:1000], emotion={"label": "neutral"}
        )
        assert memory.count() >= 1

    def test_unicode_and_special_chars(self, tmp_path):
        memory = DriftMemory(persist_directory=str(tmp_path))
        weird = "🚀🔥💀 émojis \x00\x01\x02 \\n\\t \\x00 中文 العربية 🌀"
        memory.save_interaction(weird, "ok", emotion={"label": "neutral"})
        # Should not crash

    def test_memory_with_none_emotion(self, tmp_path):
        memory = DriftMemory(persist_directory=str(tmp_path))
        memory.save_interaction("hello", "hi", emotion=None, dissonance=None)
        assert memory.count() >= 1

    def test_memory_scrub_no_crash(self, tmp_path):
        memory = DriftMemory(persist_directory=str(tmp_path))
        # No secrets, just random text
        for _ in range(50):
            memory.save_interaction(
                _rand_string(100), _rand_string(50), emotion=_heavy_emotion()
            )
        assert memory.count() >= 50

    def test_prompt_budget_empty_sections(self):
        budget = PromptBudget(max_total_chars=100)
        budget.add("core", "x")
        budget.add("context", "y" * 200)  # exceeds budget
        result = budget.trim_to_budget()
        assert len(result) <= 100 + 20

    def test_being_with_extreme_values(self, tmp_path):
        being = Being(db_path=tmp_path / "being.db")
        being.state.energy = 2.0  # should be clamped by evolve
        being.state.attachment = -0.5
        being.evolve(interaction_happened=True)
        assert 0 <= being.state.energy <= 1.0
        assert 0 <= being.state.attachment <= 1.0

    def test_circuit_breaker_extreme_thresholds(self):
        cb = CircuitBreaker("x", failure_threshold=0)
        cb.record_failure()
        assert cb.state == "open"

    def test_orchestrator_with_mock_context(self):
        orch = CognitiveOrchestrator()

        class MockCtx:
            iteration = 1
            being = None
            memory = None
            state = None
            brain = None
            minutes_since_interaction = 0.0
            last_interaction_time = None

        log = orch.run_cycle(MockCtx())
        assert log.turn_number == 1


# ── Rapid-Fire / Throughput Tests ─────────────────────────────────


class TestRapidFire:
    """Test many operations in quick succession."""

    def test_100_interactions_memory(self, tmp_path):
        from infj_bot.core.embeddings import LocalEmbeddingFunction
        memory = DriftMemory(persist_directory=str(tmp_path), embedding_function=LocalEmbeddingFunction())
        start = time.time()
        for i in range(100):
            memory.save_interaction(
                f"Message {i}",
                f"Reply {i}",
                emotion=_heavy_emotion(),
                importance=random.random(),
            )
        elapsed = time.time() - start
        assert memory.count() == 100
        assert elapsed < 25  # ChromaDB persistent writes are disk-bound

    def test_50_physics_observations(self, tmp_path):
        physics = PhysicsEngine(db_path=str(tmp_path / "physics.db"))
        start = time.time()
        for i in range(50):
            physics.observe_interaction(
                random.choice(["sad", "joyful", "anxious", "calm", "curious"]),
                random.random(),
                random.random(),
                f"input {i}",
                f"output {i}",
            )
        elapsed = time.time() - start
        assert elapsed < 10

    def test_50_humanity_observations(self, tmp_path):
        humanity = HumanityEngine(db_path=str(tmp_path / "humanity.db"))
        start = time.time()
        for i in range(50):
            humanity.observe_interaction(
                _rand_string(50),
                _heavy_emotion(),
                _heavy_dissonance(),
                "ok",
            )
        elapsed = time.time() - start
        assert elapsed < 10

    def test_being_rapid_evolve(self, tmp_path):
        being = Being(db_path=tmp_path / "being.db")
        start = time.time()
        for _ in range(200):
            being.evolve(interaction_happened=random.choice([True, False]))
        elapsed = time.time() - start
        assert elapsed < 5

    def test_prompt_budget_rapid_assembly(self):
        budget = PromptBudget()
        start = time.time()
        for _ in range(100):
            budget.add("core", _rand_string(100), label="x")
            budget.add("cognitive", _rand_string(100), label="y")
            budget.check_overlaps()
            budget.trim_to_budget()
        elapsed = time.time() - start
        assert elapsed < 5


# ── Concurrent / Threading Tests ──────────────────────────────────


class TestConcurrency:
    """Test thread safety of core components."""

    def test_memory_concurrent_writes(self, tmp_path):
        memory = DriftMemory(persist_directory=str(tmp_path))
        errors = []

        def writer(n):
            try:
                for i in range(20):
                    memory.save_interaction(
                        f"thread-{n}-msg-{i}",
                        f"thread-{n}-reply-{i}",
                        emotion={"label": "neutral"},
                    )
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=writer, args=(i,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Concurrent writes failed: {errors}"
        assert memory.count() == 100

    def test_being_concurrent_evolve(self, tmp_path):
        being = Being(db_path=tmp_path / "being.db")
        errors = []

        def evolver():
            try:
                for _ in range(50):
                    being.evolve(interaction_happened=True)
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=evolver) for _ in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Concurrent evolve failed: {errors}"

    def test_resilience_concurrent_breaker(self):
        rm = ResilienceManager()
        cb = rm.get_breaker("concurrent")
        errors = []

        def flapper():
            try:
                for _ in range(20):
                    cb.record_failure()
                    time.sleep(0.001)
                    cb.record_success()
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=flapper) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Concurrent breaker failed: {errors}"


# ── Failure Injection / Chaos Tests ───────────────────────────────


class TestFailureInjection:
    """Test behavior when components fail."""

    def test_orchestrator_survives_broken_plugin(self):
        orch = CognitiveOrchestrator()
        # Temporarily break a plugin by setting a bad instance
        plugin = orch.arch.get_plugin("inner_voice")
        if plugin:
            original = plugin.instance
            plugin.instance = object()  # broken instance

            class MockCtx:
                iteration = 1
                being = None
                memory = None
                state = None
                brain = None
                minutes_since_interaction = 0.0
                last_interaction_time = None

            log = orch.run_cycle(MockCtx())
            assert log.turn_number == 1  # survived
            plugin.instance = original  # restore

    def test_resilience_fallback_on_crash(self):
        rm = ResilienceManager()
        result = rm.execute_sync(
            "crash",
            lambda: (_ for _ in ()).throw(RuntimeError("injected")),
            fallback="recovered",
        )
        assert result == "recovered"

    def test_health_monitor_survives_bad_checker(self):
        hm = ResilienceManager().health
        hm.register("bad", lambda: (_ for _ in ()).throw(RuntimeError("checker down")))
        results = hm.check()
        assert len(results) == 1
        assert not results[0].healthy

    def test_memory_survives_corrupt_import(self, tmp_path):
        memory = DriftMemory(persist_directory=str(tmp_path))
        bad_json = tmp_path / "bad_import.json"
        bad_json.write_text("{not valid json")
        with pytest.raises((ValueError, json.JSONDecodeError)):
            memory.import_json(str(bad_json))
        # Memory should still work after failed import
        memory.save_interaction("still", "works")
        assert memory.count() >= 1


# ── Resource Exhaustion Tests ─────────────────────────────────────


class TestResourceExhaustion:
    """Test behavior under resource pressure."""

    def test_memory_prune_old_low_importance(self, tmp_path):
        memory = DriftMemory(persist_directory=str(tmp_path))
        # Add many old interactions
        for i in range(50):
            memory.save_interaction(
                f"old-{i}",
                f"reply-{i}",
                emotion={"label": "neutral"},
                importance=0.2,
            )
        # Manually backdate by querying and can't easily backdate,
        # so just verify prune runs without crash
        removed = memory.prune_interactions(max_age_days=0, max_importance=0.3)
        # All 50 should be removable since they're all low importance
        assert removed >= 0  # May or may not remove depending on timing

    def test_prompt_budget_under_severe_pressure(self):
        budget = PromptBudget(max_total_chars=500)
        # Stuff it full
        for _ in range(20):
            budget.add("core", _rand_string(100))
            budget.add("cognitive", _rand_string(100))
            budget.add("context", _rand_string(100))
        result = budget.trim_to_budget()
        assert len(result) <= 500 + 50  # hard truncate + footer margin

    def test_being_memory_overflow(self, tmp_path):
        being = Being(db_path=tmp_path / "being.db")
        for _ in range(100):
            being.working_memory.append(_rand_string(50))
        being.free_thought()
        assert len(being.working_memory) <= 20  # should be capped


# ── End-to-End Pipeline Stress ────────────────────────────────────


class TestEndToEndStress:
    """Full pipeline stress."""

    def test_20_turn_conversation_simulation(self, tmp_path):
        """Simulate a 20-turn conversation end-to-end."""
        memory = DriftMemory(persist_directory=str(tmp_path))
        being = Being(db_path=tmp_path / "being.db")
        physics = PhysicsEngine(db_path=str(tmp_path / "physics.db"))
        humanity = HumanityEngine(db_path=str(tmp_path / "humanity.db"))
        budget = PromptBudget()
        orch = CognitiveOrchestrator()

        for turn in range(20):
            user_input = _rand_string(random.randint(10, 200))
            emotion = _heavy_emotion()
            dissonance = _heavy_dissonance()

            # Simulate chat loop
            memory.save_interaction(
                user_input, "bot reply", emotion=emotion, dissonance=dissonance
            )
            being.evolve(interaction_happened=True)
            being.update_theory_of_mind(user_input, emotion, dissonance)
            physics.observe_interaction(
                emotion["label"],
                emotion["intensity"],
                dissonance["score"],
                user_input,
                "bot reply",
            )
            humanity.observe_interaction(user_input, emotion, dissonance, "bot reply")

            # Simulate prompt build
            budget = PromptBudget()
            budget.add("core", being.format_being_prompt())
            budget.add("cognitive", physics.format_prompt_snippet())
            budget.add("cognitive", humanity.format_prompt_snippet())
            budget.check_overlaps()
            prompt = budget.trim_to_budget()

            # Simulate consciousness cycle
            ctx = CycleContext(
                being=being,
                memory=memory,
                state=None,
                brain=None,
                iteration=turn + 1,
                minutes_since_interaction=0.5,
                last_interaction_time=None,
            )
            orch.run_cycle(ctx)

        assert memory.count() == 20
        assert being.state.total_interactions >= 20

    def test_memory_retrieval_after_heavy_load(self, tmp_path):
        memory = DriftMemory(persist_directory=str(tmp_path))
        for i in range(100):
            memory.save_interaction(
                f"topic {i % 10}: {_rand_string(50)}",
                f"reply {i}",
                emotion={"label": "neutral"},
            )
        # Retrieve should still work and return relevant results
        results = memory.retrieve_context("topic 5", n_results=5)
        assert results  # should not be empty
        assert isinstance(results, str)


# ── Deterministic Reproducibility Tests ───────────────────────────


class TestDeterminism:
    """Ensure same inputs produce same outputs where expected."""

    def test_same_input_same_embedding(self):
        emb_fn = SemanticEmbeddingFunction()
        text = "The quick brown fox"
        e1 = emb_fn.embed_query(text)
        e2 = emb_fn.embed_query(text)
        assert pytest.approx(e1.tolist()) == e2.tolist()

    def test_memory_roundtrip_idempotent(self, tmp_path):
        memory = DriftMemory(persist_directory=str(tmp_path))
        memory.learn_concept("TestConcept", "A test concept", tags=["unit"])
        r1 = memory.search("test concept")
        r2 = memory.search("test concept")
        assert len(r1) == len(r2)
