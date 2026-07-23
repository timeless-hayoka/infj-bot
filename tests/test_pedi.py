import os
import tempfile
import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock

from drift.metrics.pedi import (
    PediIndex,
    StateSnapshot,
    ResetEvent,
    NEED_DIMENSIONS,
    CRITICAL_FLUIDITY,
)
from drift.core.cognitive_orchestrator import CognitiveOrchestrator
from drift.core.commands import BotState


class TestPediIndex(unittest.TestCase):
    def setUp(self):
        # Create a temp database for PediIndex testing
        self.db_fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(self.db_fd)
        self.pedi = PediIndex(db_path=self.db_path)

    def tearDown(self):
        if os.path.exists(self.db_path):
            os.unlink(self.db_path)

    def test_record_and_get_last_snapshot(self):
        needs = {dim: 0.5 for dim in NEED_DIMENSIONS}
        snap = StateSnapshot(
            turn_id=1,
            timestamp=datetime.now(timezone.utc),
            needs=needs,
            context_tokens_used=100,
        )
        self.pedi.record_snapshot(snap)

        last_snap = self.pedi.get_last_snapshot()
        self.assertIsNotNone(last_snap)
        self.assertEqual(last_snap.turn_id, 1)
        self.assertEqual(last_snap.context_tokens_used, 100)
        for dim in NEED_DIMENSIONS:
            self.assertAlmostEqual(last_snap.needs[dim], 0.5)

    def test_zero_jump(self):
        needs = {dim: 0.5 for dim in NEED_DIMENSIONS}
        snap1 = StateSnapshot(
            turn_id=1,
            timestamp=datetime.now(timezone.utc),
            needs=needs,
            context_tokens_used=100,
        )
        snap2 = StateSnapshot(
            turn_id=2,
            timestamp=datetime.now(timezone.utc),
            needs=needs,
            context_tokens_used=120,
        )

        event = ResetEvent(
            turn_id=2, timestamp=datetime.now(timezone.utc), reason="test"
        )
        report = self.pedi.evaluate_reset(snap1, snap2, event)

        self.assertEqual(report.state_jump, 0.0)
        self.assertEqual(report.fluidity_score, 1.0)
        self.assertEqual(report.cumulative_fluidity, 1.0)
        self.assertTrue(report.recovered)
        self.assertFalse(report.crisis_flag)

    def test_max_jump(self):
        # Create states with maximum possible differences to trigger SFS = 0
        needs_min = {dim: 0.0 for dim in NEED_DIMENSIONS}
        needs_max = {dim: 1.0 for dim in NEED_DIMENSIONS}

        snap1 = StateSnapshot(
            turn_id=1,
            timestamp=datetime.now(timezone.utc),
            needs=needs_min,
            context_tokens_used=100,
        )
        snap2 = StateSnapshot(
            turn_id=2,
            timestamp=datetime.now(timezone.utc),
            needs=needs_max,
            context_tokens_used=120,
        )

        event = ResetEvent(
            turn_id=2, timestamp=datetime.now(timezone.utc), reason="test"
        )
        report = self.pedi.evaluate_reset(snap1, snap2, event)

        # Max Euclidean jump distance should be sqrt(len(NEED_DIMENSIONS) * 1.0^2)
        # SFS should collapse to 0.0 because the jump exceeds MAX_TOLERATED_JUMP
        self.assertEqual(report.fluidity_score, 0.0)

    def test_ema_smoothing(self):
        # Test cumulative fluidity updates: CF_t = 0.9 * CF_{t-1} + 0.1 * SFS_t
        needs_1 = {dim: 0.5 for dim in NEED_DIMENSIONS}
        snap1 = StateSnapshot(
            turn_id=1,
            timestamp=datetime.now(timezone.utc),
            needs=needs_1,
            context_tokens_used=100,
        )

        # Modify needs to cause a specific jump
        needs_2 = {dim: 0.6 for dim in NEED_DIMENSIONS}
        snap2 = StateSnapshot(
            turn_id=2,
            timestamp=datetime.now(timezone.utc),
            needs=needs_2,
            context_tokens_used=120,
        )

        # Baseline start: EMA = 1.0
        self.assertEqual(self.pedi._cumulative_fluidity, 1.0)

        event = ResetEvent(
            turn_id=2, timestamp=datetime.now(timezone.utc), reason="test"
        )
        report = self.pedi.evaluate_reset(snap1, snap2, event)

        # Expected EMA calculation
        expected_ema = 0.9 * 1.0 + 0.1 * report.fluidity_score
        self.assertAlmostEqual(report.cumulative_fluidity, expected_ema, places=4)

    def test_crisis_trigger(self):
        # Force consecutive low SFS to drop cumulative fluidity below CRITICAL_FLUIDITY
        needs_min = {dim: 0.0 for dim in NEED_DIMENSIONS}
        needs_max = {dim: 1.0 for dim in NEED_DIMENSIONS}

        snap_prev = StateSnapshot(
            turn_id=1,
            timestamp=datetime.now(timezone.utc),
            needs=needs_min,
            context_tokens_used=100,
        )

        # Trigger multiple resets with max jump
        for turn in range(2, 20):
            snap_curr = StateSnapshot(
                turn_id=turn,
                timestamp=datetime.now(timezone.utc),
                needs=needs_max if turn % 2 == 0 else needs_min,
                context_tokens_used=100,
            )
            event = ResetEvent(
                turn_id=turn, timestamp=datetime.now(timezone.utc), reason="test"
            )
            report = self.pedi.evaluate_reset(snap_prev, snap_curr, event)
            snap_prev = snap_curr

            if report.cumulative_fluidity < CRITICAL_FLUIDITY:
                self.assertTrue(report.crisis_flag)
                break
        else:
            self.fail("Failed to trigger critical fluidity crisis")

    def test_cognitive_orchestrator_integration(self):
        # Verify that snapshot is recorded on every assemble_prompt() call
        orchestrator = CognitiveOrchestrator()
        state = BotState(mode="companion")

        mock_memory = MagicMock()
        mock_memory.retrieve_context_ranked.return_value = ""
        mock_memory.retrieve_context.return_value = ""

        # Patch PediIndex db_path to use our test db path
        with patch("drift.metrics.pedi.get_pedi") as mock_get_pedi:
            mock_get_pedi.return_value = self.pedi

            # Run prompt assembly
            orchestrator.assemble_prompt("Hello", state, mock_memory)

            # Verify snapshot was written
            last_snap = self.pedi.get_last_snapshot()
            self.assertIsNotNone(last_snap)
            self.assertEqual(last_snap.turn_id, 0)

            # Run another turn to confirm increment
            state.turns = 1
            orchestrator.assemble_prompt("How are you", state, mock_memory)
            last_snap_2 = self.pedi.get_last_snapshot()
            self.assertEqual(last_snap_2.turn_id, 1)


# Helper patch class
class patch:
    def __init__(self, target):
        self.target = target
        self.mock = MagicMock()

    def __enter__(self):
        import importlib

        parts = self.target.split(".")
        module_path = ".".join(parts[:-1])
        member = parts[-1]
        self.module = importlib.import_module(module_path)
        self.original = getattr(self.module, member)
        setattr(self.module, member, self.mock)
        return self.mock

    def __exit__(self, exc_type, exc_val, exc_tb):
        parts = self.target.split(".")
        member = parts[-1]
        setattr(self.module, member, self.original)
