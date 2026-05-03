"""Tests for the self-evaluation system."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from self_eval import SelfEvaluator


class TestSelfEvaluator(unittest.TestCase):
    def setUp(self):
        self.tmp_db = Path(tempfile.mktemp(suffix=".db"))
        self.eval = SelfEvaluator(db_path=self.tmp_db)

    def tearDown(self):
        if self.tmp_db.exists():
            self.tmp_db.unlink()

    def test_evaluate_confident_response(self):
        response = "I am absolutely certain that this is correct."
        scores = self.eval.evaluate("", response)
        self.assertGreater(scores["hallucination_score"], 0.2)
        self.assertLess(scores["confidence"], 0.9)

    def test_evaluate_uncertain_response(self):
        response = "I think this might be the case, but I'm not sure."
        scores = self.eval.evaluate("", response)
        self.assertGreater(scores["uncertainty_score"], 0.1)
        self.assertGreater(scores["confidence"], 0.5)

    def test_record_and_stats(self):
        scores = self.eval.evaluate("prompt", "response")
        rid = self.eval.record("prompt", "response", scores, correction="too vague")
        self.assertGreater(rid, 0)
        stats = self.eval.recent_stats()
        self.assertEqual(stats["count"], 1)
        self.assertEqual(stats["corrections_count"], 1)

    def test_suggest_labels_high_hallucination(self):
        response = "I definitely know that everyone always does this."
        labels = self.eval.suggest_uncertainty_labels(response)
        self.assertTrue(any("speculative" in l or "high confidence" in l for l in labels))

    def test_suggest_labels_uncertain(self):
        response = "I think maybe this could work. Perhaps it seems likely, but I'm not sure."
        labels = self.eval.suggest_uncertainty_labels(response)
        self.assertTrue(any("well-calibrated" in l for l in labels))

    def test_clear_old(self):
        scores = self.eval.evaluate("p", "r")
        self.eval.record("p", "r", scores)
        removed = self.eval.clear_old(max_age_days=0)
        self.assertEqual(removed, 1)


if __name__ == "__main__":
    unittest.main()
