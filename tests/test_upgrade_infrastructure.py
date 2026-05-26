"""Tests for the DRIFT upgrade infrastructure.

Covers:
- run_logger.py — SQLite logging, WAL mode, batch commits
- experiment_control.py — freeze flags, config validation, run lifecycle
- continuity_vector.py — five-axis continuity scoring, baseline normalization
- dmu_scoring.py — additive MPS, two-stage retrieval, score components
"""

from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path

# Ensure project root is importable
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# ── run_logger tests ────────────────────────────────────────────────


class TestRunLogger:
    def test_singleton(self):
        from infj_bot.core.run_logger import RunLogger

        # Use a temp db to avoid conflicts
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            db_path = tmp.name
        try:
            a = RunLogger.get_instance(db_path)
            b = RunLogger.get_instance(db_path)
            assert a is b
            a.close()
        finally:
            os.unlink(db_path)

    def test_log_run_start_and_event(self):
        from infj_bot.core.run_logger import RunLogger

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            db_path = tmp.name
        try:
            logger = RunLogger.get_instance(db_path)
            logger.log_run_start("run_001", {"mode": "baseline"}, "abc123")
            logger.log_event("run_001", 0, "state_snapshot", {"mood": 0.7})
            logger.log_event("run_001", 1, "memory_selection", {"selected": []})
            logger.flush()

            import sqlite3

            conn = sqlite3.connect(db_path)
            runs = conn.execute("SELECT * FROM runs").fetchall()
            events = conn.execute("SELECT * FROM events").fetchall()
            conn.close()

            assert len(runs) == 1
            assert runs[0][0] == "run_001"
            assert len(events) == 2
            assert events[0][2] == "state_snapshot"
            logger.close()
        finally:
            os.unlink(db_path)
            RunLogger._instance = None

    def test_log_run_end(self):
        from infj_bot.core.run_logger import RunLogger

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            db_path = tmp.name
        try:
            logger = RunLogger.get_instance(db_path)
            logger.log_run_start("run_002", {}, "hash")
            logger.log_run_end("run_002")

            import sqlite3

            conn = sqlite3.connect(db_path)
            events = conn.execute(
                "SELECT event_type FROM events WHERE run_id='run_002'"
            ).fetchall()
            conn.close()

            assert any(e[0] == "run_end" for e in events)
            logger.close()
        finally:
            os.unlink(db_path)
            RunLogger._instance = None


# ── experiment_control tests ────────────────────────────────────────


class TestExperimentControl:
    def test_start_end_run(self):
        from infj_bot.core.experiment_control import ExperimentControl

        control = ExperimentControl()
        control.start_run("test_run", {"mode": "baseline"})
        assert control.run_id == "test_run"
        assert control.mode == "baseline"
        control.end_run()
        assert control.run_id is None

    def test_double_start_raises(self):
        from infj_bot.core.experiment_control import ExperimentControl

        control = ExperimentControl()
        control.start_run("run_a", {})
        try:
            control.start_run("run_b", {})
            assert False, "Should have raised RuntimeError"
        except RuntimeError:
            pass
        control.end_run()

    def test_is_active_freeze(self):
        from infj_bot.core.experiment_control import ExperimentControl

        control = ExperimentControl()
        control.start_run("run", {"freeze_memory": True, "freeze_state": False})
        assert not control.is_active("memory")
        assert control.is_active("state")
        control.end_run()

    def test_ablation_discipline_violation(self):
        from infj_bot.core.experiment_control import ExperimentControl

        control = ExperimentControl()
        bad_config = {
            "mode": "ablation",
            "freeze_mutation": False,
            "freeze_self_modify": False,
            "freeze_novelty": True,
        }
        try:
            control.start_run("bad", bad_config)
            assert False, "Should have raised ValueError"
        except ValueError as exc:
            assert "ablation mode violation" in str(exc).lower()

    def test_guard_context_manager(self):
        from infj_bot.core.experiment_control import ExperimentControl

        control = ExperimentControl()
        control.start_run("run", {"freeze_memory": True})
        with control.guard("memory") as active:
            assert not active
        control.end_run()


# ── continuity_vector tests ─────────────────────────────────────────


class TestContinuityVector:
    def test_compute_continuity_vector(self):
        from infj_bot.core.continuity_vector import compute_continuity_vector

        baselines = {
            "entity_overlap": {"mean": 0.5, "std": 0.2},
            "goal_overlap": {"mean": 0.4, "std": 0.15},
            "tone_similarity": {"mean": 0.6, "std": 0.1},
            "memory_reference_rate": {"mean": 0.3, "std": 0.25},
            "state_influence": {"mean": 0.2, "std": 0.05},
        }
        response_data = {
            "entity_overlap": 0.7,
            "goal_overlap": 0.4,
            "tone_similarity": 0.6,
            "memory_reference_rate": 0.3,
            "state_influence": 0.2,
        }
        cv = compute_continuity_vector(response_data, baselines)
        assert "normalized" in cv
        assert "raw" in cv
        # entity_overlap: (0.7 - 0.5) / 0.2 = 1.0
        assert abs(cv["normalized"]["entity_overlap"] - 1.0) < 0.01

    def test_collect_baseline(self):
        from infj_bot.core.continuity_vector import collect_baseline

        session_data = [
            {
                "entity_overlap": [0.4, 0.5, 0.6],
                "goal_overlap": [0.3, 0.4, 0.5],
                "tone_similarity": [0.5, 0.6, 0.7],
                "memory_reference_rate": [0.2, 0.3, 0.4],
                "state_influence": [0.1, 0.2, 0.3],
            },
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            _orig_path = Path("drift_baseline_stats.json")
            # Patch baseline path temporarily
            import infj_bot.core.continuity_vector as cv_mod

            old_path = cv_mod.BASELINE_PATH
            cv_mod.BASELINE_PATH = Path(tmpdir) / "drift_baseline_stats.json"
            try:
                stats = collect_baseline(session_data)
                assert "entity_overlap" in stats
                assert stats["entity_overlap"]["mean"] == 0.5
                assert cv_mod.BASELINE_PATH.exists()
            finally:
                cv_mod.BASELINE_PATH = old_path

    def test_validate_baselines_pass(self):
        from infj_bot.core.continuity_vector import validate_baselines

        stats = {
            "entity_overlap": {"mean": 0.5, "std": 0.2},
            "goal_overlap": {"mean": 0.4, "std": 0.15},
        }
        failed = validate_baselines(stats)
        assert failed == []

    def test_validate_baselines_fail_low_variance(self):
        from infj_bot.core.continuity_vector import validate_baselines

        stats = {
            "entity_overlap": {"mean": 0.5, "std": 0.0},
        }
        failed = validate_baselines(stats)
        assert "entity_overlap" in failed


# ── dmu_scoring tests ───────────────────────────────────────────────


class TestDMUScoring:
    def test_compute_mps_basic(self):
        from infj_bot.core.dmu_scoring import compute_mps, _DMUMemory

        mem = _DMUMemory(
            content="test memory",
            memory_id="m1",
            timestamp=time.time(),
            reinforcement_score=0.8,
            novelty_score=0.3,
            tags=["test"],
        )
        state = {"test": 0.5}
        score = compute_mps(mem, state)
        assert 0.0 <= score <= 1.0
        assert hasattr(mem, "score_components")
        assert "decay" in mem.score_components
        assert "reinf" in mem.score_components
        assert "final_mps" in mem.score_components

    def test_mps_components_sum_reasonably(self):
        from infj_bot.core.dmu_scoring import compute_mps, _DMUMemory

        mem = _DMUMemory(
            content="hello world",
            memory_id="m2",
            timestamp=time.time(),
            reinforcement_score=0.5,
            novelty_score=0.5,
            tags=["greeting"],
        )
        state = {"mood": 0.5}
        score = compute_mps(mem, state)
        comps = mem.score_components
        # All components should be in [0, 1]
        for key in [
            "decay",
            "reinf",
            "contextual",
            "recency_bias",
            "novelty",
            "state_align",
        ]:
            assert 0.0 <= comps[key] <= 1.0, f"{key} out of range: {comps[key]}"
        # Final MPS should be weighted sum
        expected = (
            0.25 * comps["decay"]
            + 0.20 * comps["reinf"]
            + 0.20 * comps["contextual"]
            + 0.15 * comps["recency_bias"]
            + 0.10 * comps["novelty"]
            + 0.10 * comps["state_align"]
        )
        assert abs(score - expected) < 0.001

    def test_mps_freeze_novelty(self):
        from infj_bot.core.dmu_scoring import compute_mps, _DMUMemory
        from infj_bot.core.experiment_control import ExperimentControl

        control = ExperimentControl()
        control.start_run("run", {"freeze_novelty": True})
        mem = _DMUMemory(
            content="test",
            memory_id="m3",
            timestamp=time.time(),
            reinforcement_score=0.5,
            novelty_score=0.9,
            tags=[],
        )
        compute_mps(mem, {"test": 0.5}, experiment_control=control)
        assert mem.score_components["novelty"] == 0.0
        control.end_run()

    def test_recency_weight(self):
        from infj_bot.core.dmu_scoring import _get_decaying_recency_weight

        recent = [("m1", 0), ("m2", 1), ("m1", 2)]
        w = _get_decaying_recency_weight("m1", recent)
        assert w >= 0.0

    def test_hard_gate_old_weak_memory(self):
        from infj_bot.core.dmu_scoring import _is_hard_gated, _DMUMemory

        old_mem = _DMUMemory(
            content="old",
            timestamp=time.time() - 40 * 24 * 3600,
            reinforcement_score=0.1,
        )
        assert _is_hard_gated(old_mem)

        fresh_mem = _DMUMemory(
            content="fresh", timestamp=time.time(), reinforcement_score=0.5
        )
        assert not _is_hard_gated(fresh_mem)

    def test_contextual_similarity_range(self):
        from infj_bot.core.dmu_scoring import _normalized_contextual_sim, _DMUMemory

        mem = _DMUMemory(content="hello world test memory")
        state = {"topic": "hello world"}
        sim = _normalized_contextual_sim(mem, state)
        assert 0.0 <= sim <= 1.0

    def test_state_alignment_range(self):
        from infj_bot.core.dmu_scoring import _state_alignment_score, _DMUMemory

        mem = _DMUMemory(content="test", tags=["mood", "energy"])
        state = {"mood": 0.5, "energy": 0.3}
        align = _state_alignment_score(mem, state)
        assert 0.0 <= align <= 1.0


# ── Main ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import traceback

    classes = [
        TestRunLogger,
        TestExperimentControl,
        TestContinuityVector,
        TestDMUScoring,
    ]

    passed = 0
    failed = 0
    for cls in classes:
        instance = cls()
        for name in dir(instance):
            if name.startswith("test_"):
                try:
                    getattr(instance, name)()
                    print(f"  PASS {cls.__name__}.{name}")
                    passed += 1
                except Exception as exc:
                    print(f"  FAIL {cls.__name__}.{name}: {exc}")
                    traceback.print_exc()
                    failed += 1

    print(f"\n{passed} passed, {failed} failed")
    sys.exit(0 if failed == 0 else 1)
