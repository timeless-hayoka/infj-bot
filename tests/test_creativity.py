"""Tests for the Creative Engine module."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from creativity import CreativeEngine


class TestCreativeEngine(unittest.TestCase):
    def setUp(self):
        self.engine = CreativeEngine()

    def test_generate_story(self):
        story = self.engine.generate_story("growth")
        self.assertIsInstance(story, str)
        self.assertGreater(len(story), 50)

    def test_generate_metaphor(self):
        metaphor = self.engine.generate_metaphor("attention")
        self.assertIsInstance(metaphor, str)
        self.assertIn("attention", metaphor)

    def test_blend_concepts(self):
        blend = self.engine.blend_concepts("memory", "water")
        self.assertIsInstance(blend, str)
        self.assertIn("memory", blend)
        self.assertIn("water", blend)

    def test_what_if(self):
        scenario = self.engine.what_if_scenario("time")
        self.assertIsInstance(scenario, str)
        self.assertTrue("What if" in scenario or "Imagine" in scenario)

    def test_express_mood(self):
        expression = self.engine.express_mood()
        self.assertIsInstance(expression, str)
        self.assertGreater(len(expression), 10)

    def test_generate_insight_poem(self):
        poem = self.engine.generate_insight_poem()
        self.assertIsInstance(poem, str)
        self.assertIn("\n", poem)


if __name__ == "__main__":
    unittest.main()
