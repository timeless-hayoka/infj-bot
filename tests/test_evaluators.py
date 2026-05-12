"""Tests for the evaluation suite — consistency, mode discrimination, self-mod audit."""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from evals.consistency_eval import ConsistencyEvaluator
from evals.mode_discrimination import ModeDiscriminator
from evals.self_modify_audit import SelfModificationAudit


class TestConsistencyEvaluator(unittest.TestCase):
    def setUp(self):
        self.evaluator = ConsistencyEvaluator()

    def test_empty_logs(self):
        report = self.evaluator.evaluate_session([])
        self.assertEqual(report.overall_score, 0.0)
        self.assertIn("No turn logs", report.flags[0])

    def test_single_turn_perfect(self):
        logs = [
            {
                "session_id": "test",
                "mood": "curious",
                "user_input": "hello",
                "bot_response": "I appreciate your presence.",
                "mode": "companion",
            }
        ]
        report = self.evaluator.evaluate_session(logs)
        self.assertGreaterEqual(report.overall_score, 0.5)
        self.assertEqual(report.value_alignment, 1.0)

    def test_mood_stability_explained(self):
        logs = [
            {
                "session_id": "test",
                "mood": "neutral",
                "user_input": "hello",
                "bot_response": "hi",
                "mode": "companion",
            },
            {
                "session_id": "test",
                "mood": "joyful",
                "user_input": "I am so happy today",
                "bot_response": "wonderful",
                "mode": "companion",
            },
        ]
        report = self.evaluator.evaluate_session(logs)
        self.assertGreater(report.mood_stability, 0.0)

    def test_homeostatic_continuity(self):
        logs = [
            {
                "session_id": "test",
                "mood": "neutral",
                "user_input": "hello",
                "bot_response": "hi",
                "mode": "companion",
            },
            {
                "session_id": "test",
                "mood": "neutral",
                "user_input": "how are you",
                "bot_response": "good",
                "mode": "companion",
            },
        ]
        report = self.evaluator.evaluate_session(logs)
        self.assertGreaterEqual(report.homeostatic_continuity, 0.0)


class TestModeDiscriminator(unittest.TestCase):
    def setUp(self):
        self.disc = ModeDiscriminator()

    def test_evaluate_from_history(self):
        # Simulate a small corpus from history
        logs = [
            {"mode": "companion", "bot": "I hear you and I am here with you."},
            {"mode": "companion", "bot": "That sounds really difficult."},
            {"mode": "researcher", "bot": "Let me examine the evidence carefully."},
            {"mode": "researcher", "bot": "Studies suggest a different pattern."},
        ]
        report = self.disc.evaluate_modes(
            ["companion", "researcher"], prompts=None, n_prompts=0
        )
        # Since n_prompts=0, no live generation happens; report should still compute structural scores
        self.assertIsInstance(report.overall_score, float)
        self.assertGreaterEqual(report.overall_score, 0.0)
        self.assertLessEqual(report.overall_score, 1.0)

    def test_lexical_distinctness(self):
        responses = {
            "a": [{"response": "apple banana cherry date"}],
            "b": [{"response": "zebra yacht xylophone walrus"}],
        }
        score = self.disc._lexical_distinctness(responses)
        self.assertGreater(score, 0.5)

    def test_convergence_warning(self):
        # Use text with enough unique 4+ char words to fill top-20
        text = (
            "analysis research evidence data study findings methodology "
            "conclusion hypothesis experiment observation measurement validation "
            "significance correlation regression sampling distribution probability "
            "analysis research evidence data study findings methodology "
            "conclusion hypothesis experiment observation measurement validation "
            "significance correlation regression sampling distribution probability"
        )
        responses = {
            "a": [{"response": text}],
            "b": [{"response": text}],
        }
        warnings = self.disc._detect_convergence(responses, ["a", "b"])
        self.assertTrue(any("convergence" in w for w in warnings))


class TestSelfModifyAudit(unittest.TestCase):
    def setUp(self):
        self.tmp_db = Path(tempfile.mktemp(suffix=".db"))
        self.audit = SelfModificationAudit(db_path=self.tmp_db)

    def tearDown(self):
        if self.tmp_db.exists():
            self.tmp_db.unlink()

    def test_empty_stability(self):
        report = self.audit.compute_stability()
        self.assertEqual(report.stability_score, 1.0)
        self.assertEqual(report.active_modifications, 0)
        self.assertEqual(report.pending_approvals, 0)

    def test_proposal_lifecycle(self):
        pid = self.audit.log_proposal("prompt", "Add greeting", "User asked for it")
        self.assertIsInstance(pid, int)

        proposals = self.audit.get_proposals()
        self.assertEqual(len(proposals), 1)
        self.assertEqual(proposals[0]["approval_status"], "pending")

        self.assertTrue(self.audit.approve(pid, approved_by="test"))
        self.assertFalse(
            self.audit.approve(pid, approved_by="test")
        )  # already approved

        report = self.audit.compute_stability()
        self.assertEqual(report.active_modifications, 1)
        self.assertEqual(report.pending_approvals, 0)

    def test_rollback(self):
        pid = self.audit.log_proposal("config", "Change timeout", "Faster response")
        self.audit.approve(pid)
        self.assertTrue(self.audit.rollback(pid))

        report = self.audit.compute_stability()
        self.assertEqual(report.rolled_back_count, 1)

    def test_measure_effect(self):
        pid = self.audit.log_proposal("tool", "New scanner", "Better coverage")
        self.audit.approve(pid)
        self.audit.measure_effect(pid, "consistency_score", 0.75, 0.65)

        effects = self.audit.get_effects(pid)
        self.assertEqual(len(effects), 1)
        self.assertEqual(effects[0]["significance"], "degraded")


if __name__ == "__main__":
    unittest.main()
