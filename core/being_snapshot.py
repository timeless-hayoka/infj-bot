"""
core/being_snapshot.py — Cognitive State Snapshot Writer
=========================================================
Adds SQLite persistence to CognitiveState so psc_live_telemetry.py
can read real session history.

being.py currently tracks CognitiveState in memory and writes a
key-value store to being_state. PSC needs wide-format snapshots:
one row per cycle with all 16 dimensions as columns.

Integration: call snapshot_cognitive_state() from being.py after
each state update (in update_state(), tick(), or the orchestration loop).

This module is READ/WRITE. It creates a separate table (cognitive_snapshots)
and never touches the existing being_state key-value table.

Usage:
    from core.being_snapshot import CognitiveSnapshotWriter

    writer = CognitiveSnapshotWriter()  # auto-creates table
    writer.write(current_cognitive_state_dict)
"""

from __future__ import annotations

import os
import sqlite3
import logging
import json
from datetime import datetime, timezone
from dataclasses import asdict
from typing import Union

logger = logging.getLogger("drift.being_snapshot")

# Match the DB path being.py uses — override via env var
try:
    from drift.core.config import BEING_DB

    _DEFAULT_BEING_DB = str(BEING_DB)
except Exception:
    _DEFAULT_BEING_DB = "being.db"
BEING_DB_PATH = os.environ.get("DRIFT_BEING_DB", _DEFAULT_BEING_DB)

# PSC dimension names — must match psc_scaled.py DIMENSION_POLARITY keys
# Map from DRIFT's internal CognitiveState field names to PSC dimension names
FIELD_MAP = {
    # CognitiveState fields → PSC dimension names
    # Adjust these mappings to match your actual CognitiveState dataclass fields
    "mood": "alignment",
    "energy": "energy",
    "curiosity": "situational_awareness",
    "attachment": "memory_coherence",
    "focus": "focus",
    "insights_formed": "task_progress",
    "shadow_depth": "threat_pressure",  # high shadow = high threat
    # AgencyState fields
    "volition": "confidence",
    "autonomy_drive": "resilience",
    "purpose_alignment": "alignment",
    # Homeostasis fields
    "coherence": "coherence",
    "integration": "context_integrity",
    "connection": "clarity",
    "growth": "stability",
    "autonomy": "resilience",
    "integrity": "memory_coherence",
}


class CognitiveSnapshotWriter:
    """
    Writes normalized cognitive state snapshots to cognitive_snapshots table.
    Thread-safe via connection-per-write pattern.
    """

    def __init__(self, db_path: str = BEING_DB_PATH):
        self.db_path = db_path
        self._ensure_table()

    def _ensure_table(self) -> None:
        """Create cognitive_snapshots table if it doesn't exist."""
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS cognitive_snapshots (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp       TEXT NOT NULL,
                session_id      TEXT,
                cycle           INTEGER,
                -- PSC dimensions (normalized 0.0–1.0)
                focus           REAL,
                coherence       REAL,
                stability       REAL,
                clarity         REAL,
                energy          REAL,
                alignment       REAL,
                confidence      REAL,
                resilience      REAL,
                situational_awareness REAL,
                task_progress   REAL,
                context_integrity REAL,
                memory_coherence  REAL,
                threat_pressure   REAL,
                error_pressure    REAL,
                latency_pressure  REAL,
                resource_pressure REAL,
                -- Raw source fields for debugging
                raw_json        TEXT
            )
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_snapshots_ts ON cognitive_snapshots(timestamp)"
        )
        conn.commit()
        conn.close()
        logger.debug(f"[snapshot] Table ready: {self.db_path}")

    def write(
        self,
        cognitive_state: Union[dict, object],
        session_id: str = "",
        cycle: int = 0,
        error_pressure: float = 0.0,
        latency_pressure: float = 0.0,
        resource_pressure: float = 0.0,
    ) -> None:
        """
        Write one cognitive state snapshot.

        Args:
            cognitive_state: CognitiveState dataclass or dict with field values.
                             Fields are mapped via FIELD_MAP to PSC dimension names.
            session_id:      Current session identifier (optional).
            cycle:           Orchestration cycle count (optional).
            error_pressure:  External pressure signal (from cognition.py dissonance score).
            latency_pressure: External pressure signal (from inference timing).
            resource_pressure: External pressure signal (CPU load, memory).
        """

        # Convert dataclass to dict if needed
        if hasattr(cognitive_state, "__dataclass_fields__"):
            state_dict = asdict(cognitive_state)
        elif isinstance(cognitive_state, dict):
            state_dict = cognitive_state
        else:
            logger.warning("[snapshot] Unknown state type, attempting vars()")
            state_dict = vars(cognitive_state)

        # Map to PSC dimensions (normalize all values to [0, 1])
        def _norm(val, lo=0.0, hi=1.0):
            try:
                return float(max(lo, min(hi, float(val))))
            except (TypeError, ValueError):
                return 0.5  # safe fallback for non-numeric

        dims = {}
        for field, psc_dim in FIELD_MAP.items():
            val = state_dict.get(field)
            if val is not None:
                dims[psc_dim] = _norm(val)

        # Invert shadow_depth → threat_pressure (high shadow = high threat)
        if "shadow_depth" in state_dict and state_dict["shadow_depth"] is not None:
            dims["threat_pressure"] = _norm(state_dict["shadow_depth"])

        conn = sqlite3.connect(self.db_path)
        conn.execute(
            """
            INSERT INTO cognitive_snapshots (
                timestamp, session_id, cycle,
                focus, coherence, stability, clarity, energy, alignment,
                confidence, resilience, situational_awareness, task_progress,
                context_integrity, memory_coherence,
                threat_pressure, error_pressure, latency_pressure, resource_pressure,
                raw_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                datetime.now(timezone.utc).isoformat(),
                session_id,
                cycle,
                dims.get("focus", 0.5),
                dims.get("coherence", 0.5),
                dims.get("stability", 0.5),
                dims.get("clarity", 0.5),
                dims.get("energy", 0.5),
                dims.get("alignment", 0.5),
                dims.get("confidence", 0.5),
                dims.get("resilience", 0.5),
                dims.get("situational_awareness", 0.5),
                dims.get("task_progress", 0.5),
                dims.get("context_integrity", 0.5),
                dims.get("memory_coherence", 0.5),
                dims.get("threat_pressure", 0.0),
                float(error_pressure),
                float(latency_pressure),
                float(resource_pressure),
                json.dumps(state_dict, default=str),
            ),
        )
        conn.commit()
        conn.close()
        logger.debug(f"[snapshot] Wrote cycle={cycle} session={session_id}")

    def get_recent(self, limit: int = 100) -> list[dict]:
        """Read the most recent snapshots (for testing/debugging)."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cur = conn.execute(
            "SELECT * FROM cognitive_snapshots ORDER BY timestamp DESC LIMIT ?",
            (limit,),
        )
        rows = [dict(r) for r in cur.fetchall()]
        conn.close()
        return list(reversed(rows))


# Convenience singleton — import and call directly
_writer: CognitiveSnapshotWriter | None = None


def snapshot_cognitive_state(
    state,
    session_id: str = "",
    cycle: int = 0,
    error_pressure: float = 0.0,
    latency_pressure: float = 0.0,
    resource_pressure: float = 0.0,
) -> None:
    """
    Module-level convenience function.
    Call this from being.py after each state update.

    Example integration in being.py:
        from core.being_snapshot import snapshot_cognitive_state

        def update_state(self, ...):
            # ... existing update logic ...
            snapshot_cognitive_state(
                self.state,
                session_id=self.session_id,
                cycle=self.cycle_count,
            )
    """
    global _writer
    if _writer is None:
        _writer = CognitiveSnapshotWriter()
    _writer.write(
        state,
        session_id=session_id,
        cycle=cycle,
        error_pressure=error_pressure,
        latency_pressure=latency_pressure,
        resource_pressure=resource_pressure,
    )
