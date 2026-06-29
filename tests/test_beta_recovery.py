import unittest
from unittest.mock import MagicMock
from pathlib import Path
import tempfile

# Ensure paths are correctly resolved
import sys
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import drift.core.being as being_module
import drift.core.homeostasis as homeo_module
from drift.core.brain import DriftBrain
from drift.core.being import Being
from drift.core.homeostasis import HomeostaticRegulator


class TestBetaRecovery(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        db = Path(self._tmpdir.name) / "being.db"
        self._old_being = being_module._being_instance
        self._old_homeo = homeo_module._homeostasis_instance
        self.being = Being(db_path=db)
        being_module._being_instance = self.being
        self.homeo = HomeostaticRegulator(db_path=Path(self._tmpdir.name) / "homeo.db")
        homeo_module._homeostasis_instance = self.homeo
        self.brain = DriftBrain()

    def tearDown(self):
        being_module._being_instance = self._old_being
        homeo_module._homeostasis_instance = self._old_homeo
        self._tmpdir.cleanup()

    def test_beta_recovery_on_short_response(self):
        # 1. Set baseline energy
        self.being.state.energy = 0.70
        self.homeo.update_need("energy", 0.70)
        
        # 2. Mock _generate to return a light response (20 chars)
        self.brain._generate = MagicMock(return_value="Ok, sounds good to me.")

        # 3. Trigger a turn
        reply = self.brain.agent_turn("hello")

        # 4. Verify reply and energy recovery (light rest should raise energy)
        self.assertEqual(reply, "Ok, sounds good to me.")
        self.assertGreater(self.being.state.energy, 0.70)

        # 5. Homeostasis should reflect the same direction (synced or decay-adjusted)
        energy_need = self.homeo.needs["energy"]
        self.assertGreaterEqual(energy_need.current, 0.65)

    def test_standard_drain_on_long_response(self):
        # 1. Set baseline energy
        self.being.state.energy = 0.70
        self.homeo.update_need("energy", 0.70)

        # 2. Mock _generate to return a long response (250 chars)
        # 250 characters exceeds the 200 character light rest threshold
        long_response = "This is a much longer response designed to exceed the two hundred character threshold that marks light rest recovery. " * 3
        self.brain._generate = MagicMock(return_value=long_response)

        # 3. Trigger a turn
        reply = self.brain.agent_turn("tell me a long story")

        # 4. Verify energy level has decreased below 0.70
        self.assertLess(self.being.state.energy, 0.70)
        
        # 5. Verify the homeostasis need is also synced and has decreased
        energy_need = self.homeo.needs["energy"]
        self.assertLess(energy_need.current, 0.70)

if __name__ == "__main__":
    unittest.main()
