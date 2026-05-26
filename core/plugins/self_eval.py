"""Self-evaluation system for the DRIFT companion bot.

Tracks confidence, auto-critiques responses, detects hallucinations,
and learns from user corrections.
"""

import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from infj_bot.core.config import DATA_DIR

EVAL_DB = DATA_DIR / "self_eval.db"

# Hallucination markers — heuristic patterns that suggest uncertain claims
HALLUCINATION_MARKERS = [
    re.compile(r"\b(I know|I am certain|definitely|absolutely|certainly)\b", re.I),
    re.compile(r"\b(always|never|everyone|no one)\b", re.I),
    re.compile(r"\b(research shows|studies prove|it is well known)\b", re.I),
]

# Uncertainty markers — these are actually good! They show calibration.
UNCERTAINTY_MARKERS = [
    re.compile(r"\b(I think|I believe|probably|likely|maybe|perhaps|it seems)\b", re.I),
    re.compile(r"\b(not sure|uncertain|could be|might|may)\b", re.I),
]


class SelfEvaluator:
    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = str(db_path or EVAL_DB)
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS evaluations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    prompt TEXT NOT NULL,
                    response TEXT NOT NULL,
                    confidence REAL NOT NULL DEFAULT 0.5,
                    uncertainty_score REAL NOT NULL DEFAULT 0.0,
                    hallucination_score REAL NOT NULL DEFAULT 0.0,
                    correction TEXT,
                    user_rating INTEGER
                )
                """
            )
            conn.commit()

    def evaluate(self, prompt: str, response: str) -> Dict[str, float]:
        """Heuristic evaluation of a response. Returns scores."""
        # Count hallucination markers (bad)
        hall_count = sum(1 for p in HALLUCINATION_MARKERS if p.search(response))
        hallucination_score = min(1.0, hall_count * 0.25)

        # Count uncertainty markers (good — shows calibration)
        unc_count = sum(1 for p in UNCERTAINTY_MARKERS if p.search(response))
        uncertainty_score = min(1.0, unc_count * 0.15)

        # Confidence heuristic: high certainty words minus uncertainty words, clamped
        confidence = 1.0 - hallucination_score + (uncertainty_score * 0.3)
        confidence = max(0.1, min(0.95, confidence))

        return {
            "confidence": round(confidence, 2),
            "uncertainty_score": round(uncertainty_score, 2),
            "hallucination_score": round(hallucination_score, 2),
        }

    def record(
        self, prompt: str, response: str, scores: Dict[str, float], correction: str = ""
    ) -> int:
        """Store an evaluation record. Returns the record id."""
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.execute(
                """
                INSERT INTO evaluations (timestamp, prompt, response, confidence, uncertainty_score, hallucination_score, correction)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    datetime.now().isoformat(),
                    prompt[:2000],
                    response[:4000],
                    scores["confidence"],
                    scores["uncertainty_score"],
                    scores["hallucination_score"],
                    correction,
                ),
            )
            conn.commit()
            return cur.lastrowid or 0

    def recent_stats(self, limit: int = 50) -> Dict[str, Any]:
        """Return aggregate stats over recent evaluations."""
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                """
                SELECT confidence, uncertainty_score, hallucination_score, correction
                FROM evaluations
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        if not rows:
            return {"count": 0}

        confs = [r[0] for r in rows]
        halls = [r[2] for r in rows]
        corrections = [r[3] for r in rows if r[3]]

        return {
            "count": len(rows),
            "avg_confidence": round(sum(confs) / len(confs), 2),
            "avg_hallucination": round(sum(halls) / len(halls), 2),
            "high_confidence_pct": round(
                sum(1 for c in confs if c > 0.7) / len(confs) * 100, 1
            ),
            "corrections_count": len(corrections),
        }

    def recent_evaluations(self, limit: int = 10) -> List[Dict]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM evaluations ORDER BY timestamp DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    def suggest_uncertainty_labels(self, response: str) -> List[str]:
        """Suggest uncertainty labels to prepend to a response."""
        scores = self.evaluate("", response)
        labels = []
        if scores["hallucination_score"] > 0.5:
            labels.append("[high confidence claim — verify if important]")
        elif scores["hallucination_score"] > 0.25:
            labels.append("[speculative]")
        if scores["uncertainty_score"] >= 0.3:
            labels.append("[well-calibrated uncertainty]")
        if not labels and scores["confidence"] < 0.5:
            labels.append("[uncertain — treat as tentative]")
        return labels

    def clear_old(self, max_age_days: int = 90) -> int:
        cutoff = (
            datetime.now() - __import__("datetime").timedelta(days=max_age_days)
        ).isoformat()
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.execute("DELETE FROM evaluations WHERE timestamp < ?", (cutoff,))
            conn.commit()
            return cur.rowcount
