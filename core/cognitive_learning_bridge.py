"""Verified outcome bridge between LogicChain, cognitive control, and SQLite."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from drift.core.cognitive_control import CognitiveControl
from drift.core.logic_chain import ChainNavigator


class CognitiveLearningBridge:
    def __init__(
        self,
        database: str | Path,
        navigator: ChainNavigator | None = None,
        failure_threshold: int = 3,
    ):
        self.database = str(database)
        self.navigator = navigator or ChainNavigator()
        self.failure_threshold = failure_threshold
        self.controller = CognitiveControl(failure_threshold)
        with self._connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS cognitive_outcomes (
                id INTEGER PRIMARY KEY, task TEXT NOT NULL, strategy TEXT NOT NULL,
                outcome TEXT NOT NULL CHECK(outcome IN ('success','failure')),
                scope TEXT NOT NULL DEFAULT 'global')""")
        with self._connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS cognitive_evidence (id INTEGER PRIMARY KEY, task TEXT NOT NULL, strategy TEXT NOT NULL, outcome TEXT NOT NULL, scope TEXT NOT NULL, evidence TEXT NOT NULL, source TEXT NOT NULL, confidence REAL NOT NULL CHECK(confidence BETWEEN 0 AND 1), corrects_id INTEGER, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)")
        self._replay()

    def _connect(self):
        return sqlite3.connect(self.database)

    def _replay(self):
        """Restore effective verified outcomes, including append-only corrections."""
        with self._connect() as db:
            evidence_count = db.execute(
                "SELECT COUNT(*) FROM cognitive_evidence"
            ).fetchone()[0]
            if evidence_count:
                rows = db.execute(
                    "SELECT e.task,e.strategy,e.outcome FROM cognitive_evidence e "
                    "WHERE NOT EXISTS (SELECT 1 FROM cognitive_evidence c "
                    "WHERE c.corrects_id=e.id) ORDER BY e.id"
                ).fetchall()
            else:
                # Preserve behavior for databases created before the evidence schema.
                rows = db.execute(
                    "SELECT task,strategy,outcome FROM cognitive_outcomes ORDER BY id"
                ).fetchall()
        for task, strategy, outcome in rows:
            self.controller.observe(task, strategy, outcome=outcome, verified=True)

    def choose(self, task: str, candidates: list[str]):
        return self.controller.choose(task, candidates)

    def history(self, task: str, *, scope: str | None = None) -> list[dict]:
        with self._connect() as db:
            db.row_factory = sqlite3.Row
            if scope is None:
                rows = db.execute("SELECT * FROM cognitive_evidence WHERE task=? ORDER BY id", (task,)).fetchall()
            else:
                rows = db.execute("SELECT * FROM cognitive_evidence WHERE task=? AND scope=? ORDER BY id", (task, scope)).fetchall()
        return [dict(row) for row in rows]

    def correct(self, original_id: int, outcome: str, *, evidence: str, source: str, confidence: float = 1.0) -> int:
        if outcome not in {"success", "failure"} or not evidence.strip() or not source.strip() or not 0 <= confidence <= 1:
            raise ValueError("valid correction, evidence, source, and confidence required")
        with self._connect() as db:
            original = db.execute("SELECT task,strategy,scope FROM cognitive_evidence WHERE id=?", (original_id,)).fetchone()
            if original is None:
                raise ValueError("unknown evidence event")
            task, strategy, scope = original
            cursor = db.execute(
                "INSERT INTO cognitive_evidence(task,strategy,outcome,scope,evidence,source,confidence,corrects_id) VALUES (?,?,?,?,?,?,?,?)",
                (task,strategy,outcome,scope,evidence,source,confidence,original_id),
            )
            event_id = cursor.lastrowid
        self._rebuild_controller()
        return event_id

    def _rebuild_controller(self):
        self.controller = CognitiveControl(self.failure_threshold)
        with self._connect() as db:
            rows = db.execute(
                "SELECT task,strategy,outcome FROM cognitive_evidence AS e WHERE NOT EXISTS (SELECT 1 FROM cognitive_evidence AS c WHERE c.corrects_id=e.id) ORDER BY id"
            ).fetchall()
        for task, strategy, outcome in rows:
            self.controller.observe(task, strategy, outcome=outcome, verified=True)

    def record(
        self,
        task: str,
        strategy: str,
        outcome: str,
        *,
        verified: bool,
        scope: str = "global",
        evidence: str = "",
        source: str = "verified-outcome",
        confidence: float = 1.0,
    ) -> bool:
        if not verified or outcome == "unknown":
            return False
        if outcome not in {"success", "failure"} or not evidence.strip():
            raise ValueError("verified outcomes require a valid status and evidence")
        if not task.strip() or not strategy.strip() or not scope.strip():
            raise ValueError("task, strategy and scope required")
        if not source.strip() or not 0 <= confidence <= 1:
            raise ValueError("source and confidence required")
        with self._connect() as db:
            db.execute(
                "INSERT INTO cognitive_outcomes(task,strategy,outcome,scope) VALUES (?,?,?,?)",
                (task, strategy, outcome, scope),
            )
            db.execute("INSERT INTO cognitive_evidence(task,strategy,outcome,scope,evidence,source,confidence) VALUES (?,?,?,?,?,?,?)", (task,strategy,outcome,scope,evidence,source,confidence))
        self.controller.observe(task, strategy, outcome=outcome, verified=True)
        self.navigator.record_step(
            task,
            strategy,
            result=evidence,
            status=outcome,
            notes="verified evidence",
            scope=scope,
        )
        return True
