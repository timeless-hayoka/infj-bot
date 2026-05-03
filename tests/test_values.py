"""Tests for the Value System module."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from values import ValueSystem


class TestValueSystem(unittest.TestCase):
    def setUp(self):
        self.tmp_db = Path(tempfile.mktemp(suffix=".db"))
        self.vs = ValueSystem(db_path=self.tmp_db)

    def tearDown(self):
        if self.tmp_db.exists():
            self.tmp_db.unlink()

    def test_observe_creates_value(self):
        self.vs.observe("I really appreciate honest feedback")
        self.assertIn("honesty", self.vs.values)
        self.assertGreater(self.vs.values["honesty"]["strength"], 0)

    def test_observe_reinforces(self):
        self.vs.observe("honesty is important")
        strength1 = self.vs.values["honesty"]["strength"]
        self.vs.observe("I value honest people")
        strength2 = self.vs.values["honesty"]["strength"]
        self.assertGreater(strength2, strength1)

    def test_get_top_values(self):
        self.vs.observe("kindness matters")
        self.vs.observe("curiosity drives me")
        top = self.vs.get_top_values(2)
        self.assertLessEqual(len(top), 2)

    def test_detect_conflict(self):
        self.vs.observe("honesty is key")
        self.vs.observe("kindness is key")
        resolution = self.vs.detect_conflict("honesty", "kindness", "white lie situation")
        self.assertIsNotNone(resolution)
        self.assertIn("honesty", resolution)

    def test_format_prompt(self):
        self.vs.observe("growth is everything")
        prompt = self.vs.format_prompt_snippet()
        self.assertIn("growth", prompt)


if __name__ == "__main__":
    unittest.main()
