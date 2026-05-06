"""Tests for the cognitive orchestrator — event bus, phased cycles, conflict detection."""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from cognitive_orchestrator import (
    CognitiveEventBus,
    CognitiveOrchestrator,
    ConflictDetector,
    PromptConflict,
)
from cognitive_architecture import CognitiveArchitecture


class TestEventBus:
    def test_publish_and_subscribe(self):
        bus = CognitiveEventBus()
        received = []
        bus.subscribe("test_event", lambda e: received.append(e))
        bus.publish("test_event", {"data": 42}, source="test")
        assert len(received) == 1
        assert received[0]["payload"]["data"] == 42

    def test_multiple_subscribers(self):
        bus = CognitiveEventBus()
        a, b = [], []
        bus.subscribe("multi", lambda e: a.append(1))
        bus.subscribe("multi", lambda e: b.append(1))
        bus.publish("multi")
        assert len(a) == 1
        assert len(b) == 1

    def test_get_recent_filters(self):
        bus = CognitiveEventBus()
        bus.publish("alpha", {"x": 1})
        bus.publish("beta", {"x": 2})
        bus.publish("alpha", {"x": 3})
        recent = bus.get_recent(event_type="alpha", limit=2)
        assert len(recent) == 2
        assert all(e["type"] == "alpha" for e in recent)

    def test_history_limit(self):
        bus = CognitiveEventBus()
        bus._max_history = 5
        for i in range(10):
            bus.publish("fill", {"i": i})
        assert len(bus._history) == 5

    def test_handler_exception_isolated(self):
        bus = CognitiveEventBus()
        bus.subscribe("fail", lambda e: (_ for _ in ()).throw(ValueError("boom")))
        bus.subscribe("fail", lambda e: bus._history.append({"recovered": True}))
        # Should not raise; bad handler is logged and isolated
        bus.publish("fail")


class TestConflictDetector:
    def test_detects_direct_vs_gentle(self):
        detector = ConflictDetector()
        sections = {
            "core": ["be direct and challenge Jude's assumptions."],
            "cognitive": ["be gentle and hold space for vulnerability."],
        }
        conflicts = detector.detect(sections)
        assert len(conflicts) > 0
        assert any("directness vs gentleness" in c.conflict_type for c in conflicts)

    def test_no_conflict_when_aligned(self):
        detector = ConflictDetector()
        sections = {
            "core": ["Be present and listen deeply."],
            "cognitive": ["Offer quiet support and steady presence."],
        }
        conflicts = detector.detect(sections)
        assert len(conflicts) == 0

    def test_resolve_returns_sections(self):
        detector = ConflictDetector()
        sections = {
            "core": ["Be direct."],
            "cognitive": ["Be gentle."],
        }
        conflicts = detector.detect(sections)
        resolved = detector.resolve(conflicts, sections, {})
        assert "core" in resolved


class TestOrchestrator:
    @pytest.fixture
    def fresh_orch(self):
        CognitiveArchitecture.reset_instance()
        orch = CognitiveOrchestrator()
        yield orch
        CognitiveArchitecture.reset_instance()

    def test_phase_status_lists_plugins(self, fresh_orch):
        status = fresh_orch.get_phase_status()
        assert "perception" in status
        assert "reflection" in status
        # At least temporal should be registered
        assert any("temporal" in p for p in status.values())

    def test_run_cycle_creates_turn_log(self, fresh_orch):
        class MockCtx:
            iteration = 1
            being = None
            memory = None
            state = None
            brain = None
            minutes_since_interaction = 0.0
            last_interaction_time = None
        log = fresh_orch.run_cycle(MockCtx())
        assert log.turn_number == 1
        assert isinstance(log.phases, dict)

    def test_system_report_contains_architecture(self, fresh_orch):
        report = fresh_orch.get_system_report()
        assert "COGNITIVE SYSTEM REPORT" in report
        assert "Registered plugins" in report

    def test_assemble_prompt_returns_tuple(self, fresh_orch):
        class MockState:
            mode = "companion"
            prefs = None
        class MockMemory:
            def retrieve_context(self, query):
                return []
        prompt, emotion, dissonance = fresh_orch.assemble_prompt(
            "hello", MockState(), MockMemory()
        )
        assert isinstance(prompt, str)
        assert "hello" in prompt
        assert "emotion" in emotion or "label" in emotion
