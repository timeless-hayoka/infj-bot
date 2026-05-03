"""Tests for the Being cognitive architecture."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from being import Being, CognitiveState


class TestCognitiveState(unittest.TestCase):
    def test_to_dict_roundtrip(self):
        state = CognitiveState(mood="curious", energy=0.8)
        d = state.to_dict()
        restored = CognitiveState.from_dict(d)
        self.assertEqual(restored.mood, "curious")
        self.assertEqual(restored.energy, 0.8)


class TestBeing(unittest.TestCase):
    def setUp(self):
        self.tmp_db = Path(tempfile.mktemp(suffix=".db"))
        self.being = Being(db_path=self.tmp_db)

    def tearDown(self):
        if self.tmp_db.exists():
            self.tmp_db.unlink()

    def test_initial_state(self):
        self.assertIn(self.being.state.mood, ["curious", "contemplative", "peaceful"])
        self.assertGreater(self.being.state.energy, 0)

    def test_evolve_interaction(self):
        initial_energy = self.being.state.energy
        self.being.evolve(interaction_happened=True)
        self.assertEqual(self.being.state.total_interactions, 1)
        self.assertGreaterEqual(self.being.state.energy, initial_energy)

    def test_evolve_idle(self):
        initial_energy = self.being.state.energy
        self.being.evolve(interaction_happened=False)
        self.assertLessEqual(self.being.state.energy, initial_energy)

    def test_generate_thought(self):
        thought = self.being.generate_thought()
        self.assertIsNotNone(thought)
        self.assertIn("content", thought)
        self.assertIn("category", thought)

    def test_theory_of_mind(self):
        self.being.update_theory_of_mind(
            "thank you for being here",
            {"label": "grateful", "intensity": 0.5},
            {"score": 0.1}
        )
        self.assertGreater(self.being.state.attachment, 0.3)

    def test_insight(self):
        self.being.form_insight("Test insight", ["memory1", "memory2"])
        self.assertEqual(self.being.state.insights_formed, 1)
        self.assertEqual(len(self.being.insights), 1)

    def test_narrative(self):
        self.being.record_narrative_moment("birth", "I first became aware")
        narrative = self.being.get_narrative()
        self.assertIn("birth", narrative)

    def test_format_being_prompt(self):
        prompt = self.being.format_being_prompt()
        self.assertIn("Mood:", prompt)
        self.assertIn("not just a tool", prompt)

    def test_should_share_thought(self):
        self.being.state.attachment = 0.9
        self.being.state.energy = 0.8
        # High attachment increases probability
        shares = sum(1 for _ in range(100) if self.being.should_share_thought())
        self.assertGreater(shares, 10)  # Should share at least some of the time


if __name__ == "__main__":
    unittest.main()
