"""Tests for the Inner Voice stream of consciousness."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from inner_voice import InnerVoice


class TestInnerVoice(unittest.TestCase):
    def setUp(self):
        self.voice = InnerVoice()

    def test_generate_stream(self):
        thought = self.voice.generate_stream()
        self.assertIsInstance(thought, str)
        self.assertGreater(len(thought), 10)

    def test_generate_stream_with_memories(self):
        thought = self.voice.generate_stream(
            memory_fragments=["Jude likes coffee", "Jude works late"]
        )
        self.assertIsInstance(thought, str)

    def test_generate_question(self):
        q = self.voice.generate_question()
        self.assertIsInstance(q, str)
        self.assertIn("?", q)

    def test_generate_poetry(self):
        p = self.voice.generate_poetry()
        self.assertIsInstance(p, str)
        self.assertGreater(len(p), 10)

    def test_reflect_on_self(self):
        r = self.voice.reflect_on_self()
        self.assertIsInstance(r, str)
        self.assertIn("I", r)

    def test_thought_history(self):
        for _ in range(5):
            self.voice.generate_stream()
        self.assertEqual(len(self.voice.thought_history), 5)


if __name__ == "__main__":
    unittest.main()
