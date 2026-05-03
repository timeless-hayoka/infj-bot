"""Tests for the Dreamer memory consolidation module."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dreamer import Dreamer


class TestDreamer(unittest.TestCase):
    def setUp(self):
        self.dreamer = Dreamer()

    def test_dream_with_memories(self):
        memories = [
            "Jude is struggling with work deadlines",
            "Jude wants to learn more about AI",
            "Jude feels overwhelmed but motivated",
        ]
        insight = self.dreamer.dream(memories)
        self.assertIsNotNone(insight)
        self.assertIsInstance(insight, str)
        self.assertGreater(len(insight), 10)

    def test_dream_empty_memories(self):
        insight = self.dreamer.dream([])
        self.assertIsNone(insight)

    def test_extract_themes(self):
        memories = ["I want to grow and learn", "work is hard but I persist"]
        themes = self.dreamer._extract_themes(memories)
        self.assertIn("growth", themes)

    def test_find_patterns(self):
        memories = ["I worry about deadlines", "I am anxious about the project", "work is stressful"]
        patterns = self.dreamer._find_patterns(memories)
        self.assertTrue(any("anxiety" in p for p in patterns))

    def test_generate_insight_struggle_growth(self):
        themes = ["struggle", "growth"]
        insight = self.dreamer._generate_insight(themes, [], "contemplative")
        self.assertIn("struggles", insight)

    def test_generate_dream_report(self):
        report = self.dreamer.generate_dream_report()
        self.assertIn("Dream", report)
        self.assertIn("consolidated", report)


if __name__ == "__main__":
    unittest.main()
