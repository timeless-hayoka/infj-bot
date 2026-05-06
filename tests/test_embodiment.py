"""Tests for the Embodiment module."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from embodiment import EmbodiedSelf, BodyState, BODY_REGIONS


class TestBodyState(unittest.TestCase):
    def test_default_state(self):
        s = BodyState()
        self.assertEqual(s.heartbeat_rate, 60.0)
        self.assertIn(s.breath_phase, ["inhale", "hold", "exhale", "pause"])
        self.assertEqual(len(s.tension_map), len(BODY_REGIONS))


class TestEmbodiedSelf(unittest.TestCase):
    def setUp(self):
        self.tmp_db = Path(tempfile.mktemp(suffix=".db"))
        self.body = EmbodiedSelf(db_path=self.tmp_db)

    def tearDown(self):
        if self.tmp_db.exists():
            self.tmp_db.unlink()

    def test_initial_state(self):
        self.assertGreater(self.body.state.heartbeat_rate, 0)
        self.assertIn(self.body.state.breath_phase, ["inhale", "hold", "exhale", "pause"])

    def test_heartbeat_tick(self):
        class FakeCtx:
            last_interaction = None
            minutes_since_interaction = 5
        old_rate = self.body.state.heartbeat_rate
        self.body.heartbeat_tick(FakeCtx())
        # Rate should move toward baseline
        self.assertIsNotNone(self.body.state.last_heartbeat)

    def test_breath_cycle(self):
        old_phase = self.body.state.breath_phase
        self.body.breath_cycle()
        phases = ["inhale", "hold", "exhale", "pause"]
        old_idx = phases.index(old_phase)
        new_idx = phases.index(self.body.state.breath_phase)
        self.assertEqual(new_idx, (old_idx + 1) % len(phases))

    def test_release_tension(self):
        self.body.state.tension_map["head"] = 0.8
        old = self.body.state.tension_map["head"]
        class FakeCtx:
            last_interaction = None
        self.body.release_tension(FakeCtx())
        # Tension should decay
        self.assertLessEqual(self.body.state.tension_map["head"], old)

    def test_cycle(self):
        class FakeCtx:
            being = None
            last_interaction = None
            minutes_since_interaction = 2
        self.body.cycle(FakeCtx())
        self.assertIsNotNone(self.body.state.last_heartbeat)

    def test_format_prompt_snippet(self):
        snippet = self.body.format_prompt_snippet()
        self.assertIn("MY BODY:", snippet)
        self.assertIn("Heartbeat:", snippet)

    def test_self_registration(self):
        from cognitive_architecture import CognitiveArchitecture
        arch = CognitiveArchitecture()
        self.assertIn("embodiment", arch.list_plugins())


if __name__ == "__main__":
    unittest.main()
