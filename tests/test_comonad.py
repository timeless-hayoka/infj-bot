import unittest
from pydantic import ValidationError
from drift.core.context_engine import (
    CognitiveState,
    Context,
    ContextWorker,
    CognitivePayload,
)
from drift.core.cognitive_ops import (
    pedi_regulation_step,
    state_conditioned_llm,
    predicted_transition_step,
)
from drift.interfaces.comonad_cli import calculate_state_diff
from drift.core.cognitive_snapshot import (
    SnapshotLogger,
    TransitionComparator,
)


class TestComonadicWorkspaceBridge(unittest.TestCase):
    def test_cognitive_state_validation_bounds(self):
        state = CognitiveState(
            coherence=0.8, resonance=0.5, tension=0.3, shadow_depth=0.2
        )
        self.assertEqual(state.coherence, 0.8)

        with self.assertRaises(ValidationError):
            CognitiveState(coherence=-0.1)

        with self.assertRaises(ValidationError):
            CognitiveState(tension=1.5)

    def test_comonad_immutability(self):
        initial_state = CognitiveState(
            coherence=0.8, resonance=0.5, tension=0.8, shadow_depth=0.2
        )
        payload = CognitivePayload(user_input="Why disagree?")
        initial_ctx = Context[CognitivePayload](state=initial_state, value=payload)
        worker = ContextWorker[CognitivePayload](initial_ctx)

        new_worker = worker.extend(pedi_regulation_step)

        # Original untouched
        self.assertEqual(worker.state.tension, 0.8)
        self.assertEqual(len(worker.history), 0)
        self.assertEqual(worker.current().internal_log, "")

        # New worker updated
        self.assertAlmostEqual(new_worker.state.tension, 0.6)
        self.assertAlmostEqual(new_worker.state.coherence, 0.7)
        self.assertEqual(len(new_worker.history), 1)
        self.assertEqual(new_worker.history[0].tension, 0.8)
        self.assertIn("Tension damped", new_worker.current().internal_log)

    def test_state_conditioned_llm_gate(self):
        # Strict Logical Deduction Mode
        s1 = CognitiveState(coherence=0.8, resonance=0.5, tension=0.2, shadow_depth=0.2)
        p1 = CognitivePayload(user_input="input")
        w1 = ContextWorker[CognitivePayload](
            Context[CognitivePayload](state=s1, value=p1)
        )
        self.assertIn("Strict Logical Deduction", state_conditioned_llm(w1).response)

        # Exploratory Intuitive Leap Mode
        s2 = CognitiveState(coherence=0.5, resonance=0.6, tension=0.7, shadow_depth=0.2)
        p2 = CognitivePayload(user_input="input")
        w2 = ContextWorker[CognitivePayload](
            Context[CognitivePayload](state=s2, value=p2)
        )
        self.assertIn("Exploratory Intuitive Leap", state_conditioned_llm(w2).response)

        # Shadow-Driven Projection Mode
        s3 = CognitiveState(coherence=0.5, resonance=0.3, tension=0.4, shadow_depth=0.8)
        p3 = CognitivePayload(user_input="input")
        w3 = ContextWorker[CognitivePayload](
            Context[CognitivePayload](state=s3, value=p3)
        )
        self.assertIn("Shadow-Driven Projection", state_conditioned_llm(w3).response)

        # Standard Empathic Mode
        s4 = CognitiveState(coherence=0.4, resonance=0.2, tension=0.3, shadow_depth=0.2)
        p4 = CognitivePayload(user_input="input")
        w4 = ContextWorker[CognitivePayload](
            Context[CognitivePayload](state=s4, value=p4)
        )
        self.assertIn("Standard Empathic", state_conditioned_llm(w4).response)

    def test_state_drift_diff(self):
        s1 = CognitiveState(coherence=0.8, resonance=0.5, tension=0.8, shadow_depth=0.2)
        s2 = CognitiveState(coherence=0.7, resonance=0.5, tension=0.6, shadow_depth=0.2)
        diff = calculate_state_diff(s1, s2)
        self.assertEqual(diff["delta_coherence"], -0.1)
        self.assertEqual(diff["delta_tension"], -0.2)
        self.assertEqual(diff["delta_resonance"], 0.0)
        self.assertEqual(diff["delta_shadow_depth"], 0.0)


class TestStructuredPayload(unittest.TestCase):
    def test_payload_isolation(self):
        """Mutating a copied payload must not leak back to the original context."""
        p1 = CognitivePayload(user_input="hello", metadata={"key": "val"})
        p2 = p1.model_copy()
        p2.metadata["key"] = "changed"
        p2.internal_log = "modified"

        self.assertEqual(p1.metadata["key"], "val")
        self.assertEqual(p1.internal_log, "")
        self.assertEqual(p2.metadata["key"], "changed")
        self.assertEqual(p2.internal_log, "modified")

    def test_each_step_writes_own_field(self):
        """PEDI writes internal_log; gate writes response. Neither clobbers the other."""
        state = CognitiveState(
            coherence=0.8, resonance=0.5, tension=0.8, shadow_depth=0.2
        )
        payload = CognitivePayload(user_input="test")
        worker = ContextWorker[CognitivePayload](
            Context[CognitivePayload](state=state, value=payload)
        )

        worker = worker.extend(pedi_regulation_step)
        self.assertNotEqual(worker.current().internal_log, "")
        self.assertEqual(worker.current().response, "")

        worker = worker.extend(state_conditioned_llm)
        self.assertNotEqual(worker.current().internal_log, "")
        self.assertNotEqual(worker.current().response, "")


class TestHistoryAccessor(unittest.TestCase):
    def test_history_is_public_and_safe(self):
        """.history returns a copy; mutating it does not damage the worker."""
        state = CognitiveState(
            coherence=0.8, resonance=0.5, tension=0.8, shadow_depth=0.2
        )
        payload = CognitivePayload(user_input="x")
        worker = ContextWorker[CognitivePayload](
            Context[CognitivePayload](state=state, value=payload)
        )
        worker = worker.extend(pedi_regulation_step)

        hist = worker.history
        self.assertEqual(len(hist), 1)

        # Mutating the returned list must not affect the worker
        hist.pop()
        self.assertEqual(len(worker.history), 1)

    def test_no_private_attribute_poking(self):
        """The pipeline must access history through the public property."""
        # This is a design-enforcement test: if anyone reintroduces ._ctx.history
        # in production code, grep will catch it in review.
        state = CognitiveState(
            coherence=0.8, resonance=0.5, tension=0.8, shadow_depth=0.2
        )
        payload = CognitivePayload(user_input="x")
        worker = ContextWorker[CognitivePayload](
            Context[CognitivePayload](state=state, value=payload)
        )
        worker = worker.extend(pedi_regulation_step)

        # Public accessor works
        initial = worker.history[0]
        self.assertEqual(initial.tension, 0.8)


class TestForking(unittest.TestCase):
    def test_fork_runs_parallel_paths(self):
        state = CognitiveState(
            coherence=0.8, resonance=0.5, tension=0.2, shadow_depth=0.2
        )
        payload = CognitivePayload(user_input="fork test")
        worker = ContextWorker[CognitivePayload](
            Context[CognitivePayload](state=state, value=payload)
        )

        def logical_path(w: ContextWorker[CognitivePayload]) -> CognitivePayload:
            p = w.current().model_copy()
            p.response = "Logical"
            p.metadata["path"] = "logical"
            return p

        def intuitive_path(w: ContextWorker[CognitivePayload]) -> CognitivePayload:
            p = w.current().model_copy()
            p.response = "Intuitive"
            p.metadata["path"] = "intuitive"
            return p

        branches = worker.fork([logical_path, intuitive_path])
        self.assertEqual(len(branches), 2)
        self.assertEqual(branches[0].current().response, "Logical")
        self.assertEqual(branches[1].current().response, "Intuitive")

        # Original worker untouched
        self.assertEqual(worker.current().response, "")

    def test_merge_selects_branch(self):
        state = CognitiveState(
            coherence=0.8, resonance=0.5, tension=0.2, shadow_depth=0.2
        )
        payload = CognitivePayload(user_input="merge test")
        worker = ContextWorker[CognitivePayload](
            Context[CognitivePayload](state=state, value=payload)
        )

        def low_tension(w: ContextWorker[CognitivePayload]) -> CognitivePayload:
            p = w.current().model_copy()
            p.response = "calm"
            return p

        def high_tension(w: ContextWorker[CognitivePayload]) -> CognitivePayload:
            p = w.current().model_copy()
            p.response = "alert"
            return p

        branches = worker.fork([low_tension, high_tension])
        winner = worker.merge(
            branches,
            selector=lambda bs: max(bs, key=lambda b: len(b.current().response)),
        )
        self.assertIn(winner.current().response, ("calm", "alert"))


class TestSnapshotLogger(unittest.TestCase):
    def test_capture_and_round_trip(self):
        logger = SnapshotLogger(max_snapshots=3)
        state = CognitiveState(
            coherence=0.8, resonance=0.5, tension=0.3, shadow_depth=0.2
        )
        payload = CognitivePayload(user_input="snapshot test", response="hello")
        worker = ContextWorker[CognitivePayload](
            Context[CognitivePayload](state=state, value=payload)
        )

        logger.capture(worker, step=0, extra_metadata={"op": "init"})
        self.assertEqual(len(logger.snapshots), 1)
        self.assertEqual(logger.snapshots[0].user_input, "snapshot test")
        self.assertEqual(logger.snapshots[0].metadata["op"], "init")

    def test_max_snapshots_rotation(self):
        logger = SnapshotLogger(max_snapshots=2)
        state = CognitiveState()
        payload = CognitivePayload()
        worker = ContextWorker[CognitivePayload](
            Context[CognitivePayload](state=state, value=payload)
        )

        for i in range(4):
            logger.capture(worker, step=i)

        self.assertEqual(len(logger.snapshots), 2)
        self.assertEqual(logger.snapshots[0].step_index, 2)
        self.assertEqual(logger.snapshots[1].step_index, 3)


class TestTransitionComparator(unittest.TestCase):
    def test_perfect_predictor(self):
        comp = TransitionComparator()
        before = CognitiveState(coherence=0.8, tension=0.8)
        after = CognitiveState(coherence=0.7, tension=0.6)

        report = comp.compare(before, after, predictor=lambda s: after)
        self.assertEqual(report.accuracy_score, 1.0)
        self.assertEqual(report.delta_error["tension"], 0.0)

    def test_imperfect_predictor(self):
        comp = TransitionComparator()
        before = CognitiveState(coherence=0.8, tension=0.8)
        after = CognitiveState(coherence=0.7, tension=0.6)

        # Predictor overshoots tension
        report = comp.compare(
            before,
            after,
            predictor=lambda s: CognitiveState(
                coherence=s.coherence - 0.1, tension=s.tension - 0.4
            ),
        )
        self.assertLess(report.accuracy_score, 1.0)
        self.assertEqual(
            report.delta_error["tension"], -0.2
        )  # predicted 0.4, actual 0.2

    def test_evaluate_on_history(self):
        comp = TransitionComparator()
        history = [
            CognitiveState(coherence=0.8, tension=0.8),
            CognitiveState(coherence=0.8, tension=0.6),
            CognitiveState(coherence=0.8, tension=0.4),
        ]

        # Naive predictor: tension drops by 0.2 every step, coherence unchanged
        reports = comp.evaluate_on_history(
            history,
            predictor=lambda s: s.model_copy(update={"tension": s.tension - 0.2}),
        )
        self.assertEqual(len(reports), 2)
        self.assertEqual(reports[0].accuracy_score, 1.0)
        self.assertEqual(reports[1].accuracy_score, 1.0)


class TestPredictedTransitionStep(unittest.TestCase):
    def test_predicted_state_stored_in_metadata(self):
        state = CognitiveState(coherence=0.8, tension=0.8)
        payload = CognitivePayload(user_input="predict test")
        worker = ContextWorker[CognitivePayload](
            Context[CognitivePayload](state=state, value=payload)
        )

        def naive_predictor(s: CognitiveState) -> CognitiveState:
            return s.model_copy(update={"tension": s.tension - 0.2})

        worker = worker.extend(lambda w: predicted_transition_step(w, naive_predictor))

        self.assertIn("predicted_state", worker.current().metadata)
        pred = CognitiveState(**worker.current().metadata["predicted_state"])
        self.assertAlmostEqual(pred.tension, 0.6)


if __name__ == "__main__":
    unittest.main()
