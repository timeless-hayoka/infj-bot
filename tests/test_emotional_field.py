"""Tests for the Emotional Field module."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from emotional_field import EmotionalField


class TestEmotionalField(unittest.TestCase):
    def setUp(self):
        self.tmp_db = Path(tempfile.mktemp(suffix=".db"))
        self.field = EmotionalField(db_path=self.tmp_db)

    def tearDown(self):
        if self.tmp_db.exists():
            self.tmp_db.unlink()

    def test_resonate_anxious(self):
        self.field.resonate("anxious", 0.8, "I'm worried about work")
        self.assertIn(self.field.state.primary, ["concerned", "peaceful", "contemplative"])
        self.assertEqual(self.field.state.last_user_emotion, "anxious")

    def test_resonate_joyful(self):
        self.field.resonate("joyful", 0.6, "I got the job!")
        self.assertIn(self.field.state.primary, ["excited", "peaceful", "present"])

    def test_decay(self):
        self.field.resonate("stressed", 0.9, "")
        initial = self.field.state.intensity
        self.field.decay()
        self.assertLess(self.field.state.intensity, initial)

    def test_format_prompt(self):
        self.field.resonate("sad", 0.5, "")
        prompt = self.field.format_prompt_snippet()
        self.assertIn("sad", prompt)
        self.assertIn("stance", prompt)

    def test_recent_events(self):
        self.field.resonate("curious", 0.4, "")
        events = self.field.get_recent_events()
        self.assertEqual(len(events), 1)


if __name__ == "__main__":
    unittest.main()
