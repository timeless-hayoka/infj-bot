"""Tests for the Autonomous Explorer module."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from explorer import AutonomousExplorer


class TestAutonomousExplorer(unittest.TestCase):
    def setUp(self):
        self.tmp_db = Path(tempfile.mktemp(suffix=".db"))
        self.explorer = AutonomousExplorer(db_path=self.tmp_db)

    def tearDown(self):
        if self.tmp_db.exists():
            self.tmp_db.unlink()

    def test_queue_topic(self):
        self.explorer.queue_topic("quantum computing", priority=0.9)
        queue = self.explorer.get_queue()
        self.assertEqual(len(queue), 1)
        self.assertEqual(queue[0]["topic"], "quantum computing")

    def test_should_explore_high_curiosity(self):
        class FakeState:
            curiosity = 0.9
            energy = 0.8
        # Probabilistic — should return True at least sometimes
        results = [self.explorer.should_explore(FakeState()) for _ in range(50)]
        self.assertTrue(any(results))

    def test_should_explore_low_energy(self):
        class FakeState:
            curiosity = 0.9
            energy = 0.1
        self.assertFalse(self.explorer.should_explore(FakeState()))

    def test_pick_topic(self):
        topic = self.explorer.pick_topic_from_interests(["AI", "security", "philosophy"])
        self.assertIn(topic, ["AI", "security", "philosophy"])

    def test_format_discovery(self):
        d = {
            "topic": "test",
            "summary": "This is a test discovery summary.",
            "source": "http://example.com",
        }
        formatted = self.explorer.format_discovery(d)
        self.assertIn("test", formatted)


if __name__ == "__main__":
    unittest.main()
