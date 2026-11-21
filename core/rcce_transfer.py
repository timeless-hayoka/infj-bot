"""RCCE-1 experimental reusable-strategy policy.

Separate from the production CognitiveLearningBridge. A shared principle label
must be assigned externally; the controller does not infer semantic equivalence.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from drift.core.cognitive_control import CognitiveControl, Decision


class PrincipleTransferPolicy:
    """Replay verified outcomes by explicit principle rather than exact task ID."""

    def __init__(self, database: str | Path, *, failure_threshold: int = 3):
        self.database = str(database)
        self.controller = CognitiveControl(failure_threshold)
        with sqlite3.connect(self.database) as db:
            db.execute("""CREATE TABLE IF NOT EXISTS rcce_principle_outcomes (
                id INTEGER PRIMARY KEY,
                task TEXT NOT NULL,
                principle TEXT NOT NULL,
                strategy TEXT NOT NULL,
                outcome TEXT NOT NULL CHECK(outcome IN ('success','failure')),
                evidence TEXT NOT NULL
            )""")
            rows = db.execute(
                "SELECT principle,strategy,outcome FROM rcce_principle_outcomes ORDER BY id"
            ).fetchall()
        for principle, strategy, outcome in rows:
            self.controller.observe(principle, strategy, outcome=outcome, verified=True)

    def record(
        self,
        *,
        task: str,
        principle: str,
        strategy: str,
        outcome: str,
        verified: bool,
        evidence: str,
    ) -> bool:
        if not verified:
            return False
        if not all(
            isinstance(v, str) and v.strip()
            for v in (task, principle, strategy, evidence)
        ):
            raise ValueError("task, principle, strategy and evidence required")
        if outcome not in {"success", "failure"}:
            raise ValueError("invalid outcome")
        with sqlite3.connect(self.database) as db:
            db.execute(
                "INSERT INTO rcce_principle_outcomes(task,principle,strategy,outcome,evidence) "
                "VALUES (?,?,?,?,?)",
                (task, principle, strategy, outcome, evidence),
            )
        self.controller.observe(principle, strategy, outcome=outcome, verified=True)
        return True

    def choose(self, *, principle: str, candidates: list[str]) -> Decision:
        if not isinstance(principle, str) or not principle.strip():
            raise ValueError("principle required")
        return self.controller.choose(principle, candidates)
