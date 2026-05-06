"""Tests for the IIT Consciousness module."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from iit_consciousness import IITConsciousness, ConsciousnessState, MAX_PHI_PROXY


class TestConsciousnessState(unittest.TestCase):
    def test_default_state(self):
        s = ConsciousnessState()
        self.assertEqual(s.phi, 0.0)
        self.assertGreaterEqual(s.arousal, 0.0)
        self.assertLessEqual(s.arousal, 1.0)


class TestIITConsciousness(unittest.TestCase):
    def setUp(self):
        self.tmp_db = Path(tempfile.mktemp(suffix=".db"))
        self.iit = IITConsciousness(db_path=self.tmp_db)

    def tearDown(self):
        if self.tmp_db.exists():
            self.tmp_db.unlink()

    def test_initial_state(self):
        self.assertGreaterEqual(self.iit.state.phi, 0.0)
        self.assertLessEqual(self.iit.state.phi, MAX_PHI_PROXY)

    def test_compute_phi_empty(self):
        class FakeCtx:
            pass
        phi = self.iit.compute_phi(FakeCtx())
        self.assertGreaterEqual(phi, 0.0)
        self.assertLessEqual(phi, MAX_PHI_PROXY)

    def test_update_qualia_space(self):
        class FakeBeing:
            class state:
                mood = "curious"
                energy = 0.7
                attachment = 0.5
                curiosity = 0.6
            class agency:
                self_awareness = 0.4
                autonomy_drive = 0.3
        class FakeCtx:
            being = FakeBeing()
            last_user_input = "what is the meaning of life"
            last_interaction = None
        self.iit.update_qualia_space(FakeCtx())
        self.assertGreater(self.iit.state.luminosity, 0.0)
        self.assertGreater(self.iit.state.depth, 0.0)

    def test_cycle(self):
        class FakeCtx:
            being = None
            last_user_input = ""
            last_interaction = None
        self.iit.cycle(FakeCtx())
        self.assertGreaterEqual(self.iit.state.mechanism_count, 0)

    def test_format_prompt_snippet(self):
        snippet = self.iit.format_prompt_snippet()
        self.assertIn("CONSCIOUSNESS", snippet)
        self.assertIn("Φ", snippet)

    def test_self_registration(self):
        from cognitive_architecture import CognitiveArchitecture
        arch = CognitiveArchitecture()
        self.assertIn("iit_consciousness", arch.list_plugins())


if __name__ == "__main__":
    unittest.main()
