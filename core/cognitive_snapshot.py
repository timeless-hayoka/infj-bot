"""cognitive_snapshot.py — Observability and diagnostics for the comonadic pipeline.

Provides:
- SnapshotLogger: captures full ContextWorker state at each step
- TransitionComparator: evaluates predictor accuracy against actual transitions
"""

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

from infj_bot.core.context_engine import CognitiveState, ContextWorker, CognitivePayload


@dataclass
class CognitiveSnapshot:
    """A frozen frame of the cognitive pipeline at a single moment."""

    step_index: int
    timestamp: str
    state: CognitiveState
    user_input: str
    internal_log: str
    response: str
    history_depth: int
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "step_index": self.step_index,
            "timestamp": self.timestamp,
            "state": self.state.model_dump(),
            "user_input": self.user_input,
            "internal_log": self.internal_log,
            "response": self.response,
            "history_depth": self.history_depth,
            "metadata": self.metadata,
        }


class SnapshotLogger:
    """Logs full cognitive snapshots for later analysis.

    Usage:
        logger = SnapshotLogger(max_snapshots=50)
        logger.capture(pipeline, step=0)
        pipeline = pipeline.extend(some_op)
        logger.capture(pipeline, step=1)
        logger.write(Path("snapshots.jsonl"))
    """

    def __init__(self, max_snapshots: int = 50):
        self.snapshots: list[CognitiveSnapshot] = []
        self.max_snapshots = max_snapshots

    def capture(
        self,
        worker: ContextWorker[CognitivePayload],
        step: int,
        extra_metadata: Optional[dict] = None,
    ) -> None:
        """Extract a snapshot from the current worker."""
        payload = worker.current()
        snap = CognitiveSnapshot(
            step_index=step,
            timestamp=datetime.now().isoformat(),
            state=worker.state,
            user_input=payload.user_input,
            internal_log=payload.internal_log,
            response=payload.response,
            history_depth=len(worker.history),
            metadata=extra_metadata or {},
        )
        self.snapshots.append(snap)
        if len(self.snapshots) > self.max_snapshots:
            self.snapshots = self.snapshots[-self.max_snapshots :]

    def write(self, path: Path) -> None:
        """Append snapshots to a newline-delimited JSON file."""
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            for snap in self.snapshots:
                f.write(json.dumps(snap.to_dict(), default=str) + "\n")
        self.snapshots.clear()

    def clear(self) -> None:
        self.snapshots.clear()


@dataclass
class TransitionReport:
    """Result of comparing a predicted state transition against actual."""

    predicted: CognitiveState
    actual: CognitiveState
    delta_error: dict  # per-field difference between predicted and actual
    accuracy_score: float  # 0.0 (worst) → 1.0 (perfect)

    def to_dict(self) -> dict:
        return {
            "predicted": self.predicted.model_dump(),
            "actual": self.actual.model_dump(),
            "delta_error": self.delta_error,
            "accuracy_score": round(self.accuracy_score, 4),
        }


class TransitionComparator:
    """Evaluates how well a predictor function models real state transitions.

    Usage:
        comp = TransitionComparator()
        report = comp.compare(
            before_state,
            after_state,
            predictor=lambda s: s.model_copy(update={"tension": s.tension - 0.2})
        )
        print(report.accuracy_score)
    """

    def compare(
        self,
        before: CognitiveState,
        after: CognitiveState,
        predictor: Callable[[CognitiveState], CognitiveState],
    ) -> TransitionReport:
        predicted = predictor(before)

        delta_error = {
            "coherence": round(predicted.coherence - after.coherence, 4),
            "resonance": round(predicted.resonance - after.resonance, 4),
            "tension": round(predicted.tension - after.tension, 4),
            "shadow_depth": round(predicted.shadow_depth - after.shadow_depth, 4),
        }

        # Accuracy = 1 - normalised mean absolute error
        total_error = sum(abs(v) for v in delta_error.values())
        accuracy_score = max(0.0, 1.0 - total_error / 4.0)

        return TransitionReport(
            predicted=predicted,
            actual=after,
            delta_error=delta_error,
            accuracy_score=accuracy_score,
        )

    def evaluate_on_history(
        self,
        history: list[CognitiveState],
        predictor: Callable[[CognitiveState], CognitiveState],
    ) -> list[TransitionReport]:
        """Run comparison across an entire history chain."""
        reports = []
        for i in range(len(history) - 1):
            reports.append(self.compare(history[i], history[i + 1], predictor))
        return reports
