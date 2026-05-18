"""Nexus — Persistent Self-Model for the Elysium Hive.

The Nexus is DRIFT's explicit self-model: a continuously updated representation
of its current goals, moral stance, narrative arc, and active tensions. It is
what remains constant across council deliberations — the integrating identity.
"""

import json
import logging
import sqlite3
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..config import DATA_DIR

logger = logging.getLogger("drift.hive.nexus")

NEXUS_DB = DATA_DIR / "nexus.db"


@dataclass
class MoralStance:
    """The Nexus's current moral posture on an issue or in general."""
    principle: str = ""
    confidence: float = 0.5
    source: str = "inherited"  # inherited, experience, deliberation
    last_updated: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class NarrativeArc:
    """The story the bot is currently living — where it has been, where it is going."""
    chapter: str = "awakening"
    summary: str = ""
    turning_points: List[str] = field(default_factory=list)
    projected_next: str = ""
    last_updated: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class ActiveTension:
    """An unresolved dynamic pulling the self in different directions."""
    name: str = ""
    poles: List[str] = field(default_factory=list)  # e.g., ["safety", "growth"]
    intensity: float = 0.5
    resolution_path: str = ""


@dataclass
class NexusState:
    """Snapshot of the Nexus self-model."""
    current_goals: List[str] = field(default_factory=list)
    moral_stances: Dict[str, MoralStance] = field(default_factory=dict)
    narrative_arc: NarrativeArc = field(default_factory=NarrativeArc)
    active_tensions: List[ActiveTension] = field(default_factory=list)
    last_integration_time: Optional[str] = None
    decision_count: int = 0
    reflection_count: int = 0
    coherence_score: float = 0.5  # how internally consistent the self-model is

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        return d

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "NexusState":
        d = dict(d)
        d["moral_stances"] = {k: MoralStance(**v) for k, v in d.get("moral_stances", {}).items()}
        d["narrative_arc"] = NarrativeArc(**d.get("narrative_arc", {}))
        d["active_tensions"] = [ActiveTension(**t) for t in d.get("active_tensions", [])]
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


class NexusSelfModel:
    """Persistent self-model that integrates council decisions into identity."""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = str(db_path or NEXUS_DB)
        self._lock = threading.RLock()
        self._init_db()
        self._state = self._load_state()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS nexus_state (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    state_json TEXT NOT NULL,
                    updated_at TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS nexus_decisions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT,
                    goal TEXT,
                    resolution TEXT,
                    moral_weight REAL,
                    narrative_weight REAL,
                    council_votes TEXT,
                    nexus_override TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS nexus_reflections (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT,
                    trigger TEXT,
                    insight TEXT,
                    coherence_before REAL,
                    coherence_after REAL
                )
            """)
            conn.commit()

    def _load_state(self) -> NexusState:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute("SELECT state_json FROM nexus_state WHERE id = 1").fetchone()
            if row:
                try:
                    return NexusState.from_dict(json.loads(row[0]))
                except Exception:
                    logger.exception("Failed to load Nexus state")
        return NexusState()

    def _save_state(self):
        with self._lock:
            payload = json.dumps(self._state.to_dict(), default=str)
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO nexus_state (id, state_json, updated_at) VALUES (1, ?, ?)",
                    (payload, datetime.now().isoformat()),
                )
                conn.commit()

    @property
    def state(self) -> NexusState:
        return self._state

    def integrate_decision(
        self,
        goal: str,
        resolution: str,
        moral_weight: float,
        narrative_weight: float,
        council_votes: Dict[str, float],
        nexus_override: Optional[str] = None,
    ) -> None:
        """Integrate a completed Nexus Loop decision into the self-model."""
        with self._lock:
            self._state.decision_count += 1
            self._state.last_integration_time = datetime.now().isoformat()

            # Update narrative arc
            self._state.narrative_arc.turning_points.append(
                f"Decided '{goal}' -> {resolution[:80]}"
            )
            if len(self._state.narrative_arc.turning_points) > 50:
                self._state.narrative_arc.turning_points = self._state.narrative_arc.turning_points[-50:]

            # Moral learning: if a stance existed, reinforce confidence
            for principle, stance in self._state.moral_stances.items():
                if principle.lower() in goal.lower() or principle.lower() in resolution.lower():
                    stance.confidence = min(1.0, stance.confidence + 0.05)
                    stance.last_updated = datetime.now().isoformat()

            # Coherence adjustment
            vote_variance = self._compute_vote_variance(council_votes)
            self._state.coherence_score = max(
                0.0, min(1.0, self._state.coherence_score + (0.1 - vote_variance))
            )

            self._save_state()

            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    """
                    INSERT INTO nexus_decisions
                    (timestamp, goal, resolution, moral_weight, narrative_weight, council_votes, nexus_override)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        datetime.now().isoformat(),
                        goal,
                        resolution,
                        moral_weight,
                        narrative_weight,
                        json.dumps(council_votes),
                        nexus_override,
                    ),
                )
                conn.commit()

    def reflect(self, trigger: str, insight: str) -> None:
        """Record a background reflection and adjust coherence."""
        with self._lock:
            before = self._state.coherence_score
            # Reflections that name active tensions increase coherence
            if self._state.active_tensions:
                for tension in self._state.active_tensions:
                    if tension.name.lower() in insight.lower():
                        tension.intensity = max(0.0, tension.intensity - 0.1)
                        self._state.coherence_score = min(1.0, self._state.coherence_score + 0.05)
                        break

            self._state.reflection_count += 1
            after = self._state.coherence_score
            self._save_state()

            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    "INSERT INTO nexus_reflections (timestamp, trigger, insight, coherence_before, coherence_after) VALUES (?, ?, ?, ?, ?)",
                    (datetime.now().isoformat(), trigger, insight, before, after),
                )
                conn.commit()

    def set_goal(self, goal: str, priority: float = 0.5):
        """Add or elevate a current goal."""
        with self._lock:
            if goal not in self._state.current_goals:
                self._state.current_goals.insert(0, goal)
            if len(self._state.current_goals) > 20:
                self._state.current_goals = self._state.current_goals[:20]
            self._save_state()

    def resolve_tension(self, name: str, resolution: str):
        """Mark a tension as resolved."""
        with self._lock:
            self._state.active_tensions = [
                t for t in self._state.active_tensions if t.name != name
            ]
            self._state.narrative_arc.turning_points.append(f"Resolved tension '{name}': {resolution}")
            self._save_state()

    def get_state(self) -> Dict[str, Any]:
        return self._state.to_dict()

    def get_decision_history(self, limit: int = 20) -> List[Dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM nexus_decisions ORDER BY timestamp DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]

    def get_reflection_history(self, limit: int = 20) -> List[Dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM nexus_reflections ORDER BY timestamp DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]

    @staticmethod
    def _compute_vote_variance(votes: Dict[str, float]) -> float:
        if not votes:
            return 0.0
        values = list(votes.values())
        mean = sum(values) / len(values)
        variance = sum((v - mean) ** 2 for v in values) / len(values)
        return variance


_nexus_instance: Optional[NexusSelfModel] = None


def get_nexus() -> NexusSelfModel:
    global _nexus_instance
    if _nexus_instance is None:
        _nexus_instance = NexusSelfModel()
    return _nexus_instance
