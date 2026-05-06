"""Tests for the Homeostasis module."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from homeostasis import HomeostaticRegulator, NEED_DEFINITIONS


class TestHomeostaticRegulator(unittest.TestCase):
    def setUp(self):
        self.tmp_db = Path(tempfile.mktemp(suffix=".db"))
        self.reg = HomeostaticRegulator(db_path=self.tmp_db)

    def tearDown(self):
        if self.tmp_db.exists():
            self.tmp_db.unlink()

    def test_initial_needs(self):
        for name in NEED_DEFINITIONS:
            self.assertIn(name, self.reg.needs)
            self.assertGreaterEqual(self.reg.needs[name].current, 0.0)
            self.assertLessEqual(self.reg.needs[name].current, 1.0)

    def test_update_need(self):
        self.reg.update_need("energy", 0.3)
        self.assertAlmostEqual(self.reg.needs["energy"].current, 0.3)

    def test_critical_detection(self):
        self.reg.update_need("energy", 0.05)
        self.assertIn("energy", self.reg._critical_needs())

    def test_suboptimal_detection(self):
        self.reg.update_need("energy", 0.3)  # below optimal for energy
        self.assertIn("energy", self.reg._suboptimal_needs())

    def test_allostatic_prediction(self):
        self.reg.needs["energy"].current = 0.5
        self.reg.needs["energy"].trend = -0.1
        pred = self.reg.compute_allostatic_prediction("energy", minutes_ahead=10)
        self.assertLess(pred, 0.5)

    def test_check_crisis(self):
        self.reg.update_need("energy", 0.05)
        self.reg.update_need("connection", 0.05)
        self.reg.compute_allostatic_load()
        crisis = self.reg.check_crisis()
        self.assertTrue(crisis)
        self.assertTrue(self.reg.crisis_mode)

    def test_regulate(self):
        self.reg.update_need("energy", 0.05)
        class FakeCtx:
            pass
        self.reg.regulate(FakeCtx())
        # Regulation should move energy toward setpoint
        self.assertGreater(self.reg.needs["energy"].current, 0.05)

    def test_format_prompt_snippet_crisis(self):
        self.reg.update_need("energy", 0.05)
        self.reg.check_crisis()
        snippet = self.reg.format_prompt_snippet()
        self.assertIn("CRISIS", snippet)

    def test_format_prompt_snippet_normal(self):
        for name in NEED_DEFINITIONS:
            self.reg.update_need(name, NEED_DEFINITIONS[name]["setpoint"])
        snippet = self.reg.format_prompt_snippet()
        self.assertIn("optimal", snippet)

    def test_self_registration(self):
        from cognitive_architecture import CognitiveArchitecture
        arch = CognitiveArchitecture()
        self.assertIn("homeostasis", arch.list_plugins())


if __name__ == "__main__":
    unittest.main()
