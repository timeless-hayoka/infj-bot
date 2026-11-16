"""Verified outcome bridge between LogicChain, cognitive control, and SQLite."""
from __future__ import annotations

import sqlite3
from pathlib import Path

from drift.core.cognitive_control import CognitiveControl
from drift.core.logic_chain import ChainNavigator


class CognitiveLearningBridge:
    def __init__(self, database: str | Path, navigator: ChainNavigator | None = None,
                 failure_threshold: int = 3):
        self.database = str(database)
        self.navigator = navigator or ChainNavigator()
        self.controller = CognitiveControl(failure_threshold)
        with self._connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS cognitive_outcomes (
                id INTEGER PRIMARY KEY, task TEXT NOT NULL, strategy TEXT NOT NULL,
                outcome TEXT NOT NULL CHECK(outcome IN ('success','failure')),
                scope TEXT NOT NULL DEFAULT 'global')""")
        self._replay()

    def _connect(self):
        return sqlite3.connect(self.database)

    def _replay(self):
        with self._connect() as db:
            rows = db.execute("SELECT task,strategy,outcome FROM cognitive_outcomes ORDER BY id").fetchall()
        for task, strategy, outcome in rows:
            self.controller.observe(task, strategy, outcome=outcome, verified=True)

    def choose(self, task: str, candidates: list[str]):
        return self.controller.choose(task, candidates)

    def record(self, task: str, strategy: str, outcome: str, *,
               verified: bool, scope: str = "global", evidence: str = "") -> bool:
        if not verified or outcome == "unknown":
            return False
        if outcome not in {"success", "failure"} or not evidence.strip():
            raise ValueError("verified outcomes require a valid status and evidence")
        if not task.strip() or not strategy.strip() or not scope.strip():
            raise ValueError("task, strategy and scope required")
        with self._connect() as db:
            db.execute("INSERT INTO cognitive_outcomes(task,strategy,outcome,scope) VALUES (?,?,?,?)",
                       (task, strategy, outcome, scope))
        self.controller.observe(task, strategy, outcome=outcome, verified=True)
        self.navigator.record_step(task, strategy, result=evidence, status=outcome,
                                   notes="verified evidence", scope=scope)
        return True
