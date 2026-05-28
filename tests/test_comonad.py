import unittest
from pydantic import ValidationError
from infj_bot.core.context_engine import CognitiveState, Context, ContextWorker
from infj_bot.core.cognitive_ops import pedi_regulation_step, state_conditioned_llm
from infj_bot.interfaces.comonad_cli import calculate_state_diff

class TestComonadicWorkspaceBridge(unittest.TestCase):
    def test_cognitive_state_validation_bounds(self):
        # Valid state initialization
        state = CognitiveState(coherence=0.8, resonance=0.5, tension=0.3, shadow_depth=0.2)
        self.assertEqual(state.coherence, 0.8)
        self.assertEqual(state.resonance, 0.5)

        # Invalid state underflow
        with self.assertRaises(ValidationError):
            CognitiveState(coherence=-0.1)

        # Invalid state overflow
        with self.assertRaises(ValidationError):
            CognitiveState(tension=1.5)

    def test_comonad_immutability(self):
        initial_state = CognitiveState(coherence=0.8, resonance=0.5, tension=0.8, shadow_depth=0.2)
        initial_ctx = Context[str](state=initial_state, value="Why disagree?")
        worker = ContextWorker[str](initial_ctx)

        # Extend with regulation step
        new_worker = worker.extend(pedi_regulation_step)

        # Assert original worker and state did NOT change
        self.assertEqual(worker.state.tension, 0.8)
        self.assertEqual(worker.state.coherence, 0.8)
        self.assertEqual(len(worker._ctx.history), 0)

        # Assert new worker has updated state and history populated
        self.assertAlmostEqual(new_worker.state.tension, 0.6)
        self.assertAlmostEqual(new_worker.state.coherence, 0.7)
        self.assertEqual(len(new_worker._ctx.history), 1)
        self.assertEqual(new_worker._ctx.history[0].tension, 0.8)

    def test_state_conditioned_llm_gate(self):
        # Strict Logical Deduction Mode
        s1 = CognitiveState(coherence=0.8, resonance=0.5, tension=0.2, shadow_depth=0.2)
        w1 = ContextWorker[str](Context[str](state=s1, value="input"))
        self.assertIn("Strict Logical Deduction", state_conditioned_llm(w1))

        # Exploratory Intuitive Leap Mode
        s2 = CognitiveState(coherence=0.5, resonance=0.6, tension=0.7, shadow_depth=0.2)
        w2 = ContextWorker[str](Context[str](state=s2, value="input"))
        self.assertIn("Exploratory Intuitive Leap", state_conditioned_llm(w2))

        # Shadow-Driven Projection Mode
        s3 = CognitiveState(coherence=0.5, resonance=0.3, tension=0.4, shadow_depth=0.8)
        w3 = ContextWorker[str](Context[str](state=s3, value="input"))
        self.assertIn("Shadow-Driven Projection", state_conditioned_llm(w3))

        # Standard Empathic Mode
        s4 = CognitiveState(coherence=0.4, resonance=0.2, tension=0.3, shadow_depth=0.2)
        w4 = ContextWorker[str](Context[str](state=s4, value="input"))
        self.assertIn("Standard Empathic", state_conditioned_llm(w4))

    def test_state_drift_diff(self):
        s1 = CognitiveState(coherence=0.8, resonance=0.5, tension=0.8, shadow_depth=0.2)
        s2 = CognitiveState(coherence=0.7, resonance=0.5, tension=0.6, shadow_depth=0.2)
        diff = calculate_state_diff(s1, s2)
        self.assertEqual(diff["delta_coherence"], -0.1)
        self.assertEqual(diff["delta_tension"], -0.2)
        self.assertEqual(diff["delta_resonance"], 0.0)
        self.assertEqual(diff["delta_shadow_depth"], 0.0)

if __name__ == "__main__":
    unittest.main()
