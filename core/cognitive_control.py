"""Evidence-gated strategy selection for DRIFT."""
from __future__ import annotations
from collections import defaultdict
from dataclasses import dataclass

@dataclass(frozen=True)
class Decision:
    strategy: str | None
    reason: str

class CognitiveControl:
    """Session-local controller; only verified outcomes affect decisions."""

    def __init__(self, failure_threshold: int = 3):
        if failure_threshold < 1:
            raise ValueError("failure_threshold must be positive")
        self.failure_threshold = failure_threshold
        self._failures: dict[tuple[str, str], int] = defaultdict(int)
        self._successes: dict[tuple[str, str], int] = defaultdict(int)

    def observe(self, task: str, strategy: str, *, outcome: str, verified: bool) -> None:
        if not task.strip() or not strategy.strip():
            raise ValueError("task and strategy are required")
        if outcome not in {"success", "failure", "unknown"}:
            raise ValueError("unsupported outcome")
        if not verified or outcome == "unknown":
            return
        key = (task, strategy)
        if outcome == "success":
            self._successes[key] += 1
            self._failures[key] = 0
        else:
            self._failures[key] += 1

    def choose(self, task: str, candidates: list[str]) -> Decision:
        if not task.strip():
            raise ValueError("task is required")
        unique = list(dict.fromkeys(s for s in candidates if s.strip()))
        eligible = [s for s in unique if self._failures[(task, s)] < self.failure_threshold]
        if not eligible:
            return Decision(None, "no eligible strategy; request new evidence or alternatives")
        selected = max(eligible, key=lambda s: (self._successes[(task, s)], -self._failures[(task, s)]))
        return Decision(selected, "selected from verified outcome history")
