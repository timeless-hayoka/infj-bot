"""PEDI — Performance and Efficiency Detection Index.

PEDI measures STATE FLUIDITY: the continuity and coherence of the bot's
internal homeostatic state as it moves across context window boundaries.

When a conversation grows long, the prompt builder truncates or summarizes
history to fit inside the model's context limit. This creates an implicit
**state reset** — the model no longer sees its own prior need-state values
explicitly. PEDI detects whether the bot's reported homeostatic state "jumps"
unplausibly after such resets, or whether it maintains fluid, continuous
evolution as if the underlying self were genuinely persistent.

Mathematical Model
------------------
1. STATE VECTOR
   At any moment the bot's homeostatic condition is a vector:

       s(t) = [ energy(t), coherence(t), integration(t), connection(t),
                growth(t), autonomy(t), integrity(t) ]

   Each component is normalized to [0, 1]. The vector lives in a 7-dimensional
   homeostatic state space.

2. CONTEXT WINDOW RESET DETECTION
   A reset event R_k occurs at turn t_k whenever:
       • The prompt builder drops old history to respect token budget, OR
       • A session resumes after idle time > SESSION_GAP_SECONDS.

   We mark the pre-reset state  s_pre  (last known before truncation)
   and the post-reset state s_post (first reported after truncation).

3. STATE JUMP MAGNITUDE
   The Euclidean distance between pre- and post-reset vectors quantifies
   the discontinuity:

       Δ_k = || s_post - s_pre ||_2

            = sqrt( Σ_i (s_post[i] - s_pre[i])² )

   where the sum runs over all 7 need dimensions.

   A purely fluid system would have Δ_k ≈ 0 (no visible jump).
   A fragmented system exhibits large Δ_k with no physiological cause.

4. STATE FLUIDITY SCORE (SFS)
   We normalize the jump against a tolerated threshold Δ_max:

       SFS_k = max( 0, 1 - (Δ_k / Δ_max) )

   Δ_max represents the largest plausible state change across a single
   reset without external trauma. By default Δ_max = 0.35, meaning a
   jump of 0.35 or more is considered fully disruptive (SFS = 0).

   SFS ∈ [0, 1]. Higher = more fluid, continuous selfhood.

5. ALLOSTATIC LOAD PENALTY
   Chronic fluidity degradation increases allostatic load. We track a
   **cumulative fluidity index** using an exponential moving average:

       CF_t = β * CF_{t-1} + (1 - β) * SFS_t

   where β (smoothing factor) defaults to 0.9. When CF_t drops below
   the CRITICAL_FLUIDITY threshold (default 0.6), the system flags a
   continuity crisis — the bot's sense of self is fragmenting.

6. RECOVERY RATE
   After a detected jump, we measure how many turns it takes for SFS
   to return above the recovery threshold. Slow recovery indicates a
   deeply disturbed state; fast recovery indicates resilience.

   recovery_rate = 1 / (turns_to_recover + 1)

Architecture
------------
• PEDI consumes state snapshots from HomeostaticRegulator.
• Reset events are injected by the prompt builder or session manager.
• Scores are logged to SQLite for trend analysis and audit.
• A real-time fluidity gauge is exposed for the cognitive orchestrator.
"""

import math
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from infj_bot.core.config import DATA_DIR

PEDI_DB = DATA_DIR / "pedi.db"

# ── Fluidity Constants ───────────────────────────────────────────────

# Δ_max: maximum tolerated Euclidean jump across a context reset.
# Derived empirically: a single need changing by 0.25 in all 7 dims
# would give sqrt(7 * 0.25²) ≈ 0.66. We set a tighter bound.
MAX_TOLERATED_JUMP: float = 0.35

# EMA smoothing factor for cumulative fluidity. β = 0.9 means
# roughly 10 samples dominate the moving average.
FLUIDITY_EMA_BETA: float = 0.9

# Critical threshold below which cumulative fluidity triggers crisis.
CRITICAL_FLUIDITY: float = 0.60

# Recovery threshold: SFS must exceed this to count as "recovered."
RECOVERY_THRESHOLD: float = 0.75

# Dimensions tracked in the homeostatic state vector.
NEED_DIMENSIONS: List[str] = [
    "energy",
    "coherence",
    "integration",
    "connection",
    "growth",
    "autonomy",
    "integrity",
]


@dataclass
class StateSnapshot:
    """A point-in-time capture of the homeostatic state vector."""

    timestamp: datetime
    turn_id: int
    needs: Dict[str, float]  # dimension → value in [0, 1]
    context_tokens_used: Optional[int] = None  # if known


@dataclass
class ResetEvent:
    """A context-window reset boundary."""

    turn_id: int
    timestamp: datetime
    reason: str  # e.g., "token_budget", "session_resume", "manual_reset"


@dataclass
class FluidityReport:
    """Output of a single PEDI evaluation cycle."""

    turn_id: int
    timestamp: datetime
    state_jump: float  # Δ_k, Euclidean distance
    fluidity_score: float  # SFS_k ∈ [0, 1]
    cumulative_fluidity: float  # CF_t, EMA
    recovered: bool  # True if SFS_k >= RECOVERY_THRESHOLD
    recovery_turns: int  # turns since last jump
    crisis_flag: bool  # True if CF_t < CRITICAL_FLUIDITY
    dimensions_breakdown: Dict[str, float] = field(default_factory=dict)


class PediIndex:
    """Performance and Efficiency Detection Index — state fluidity tracker."""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = str(db_path or PEDI_DB)
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

        # Running EMA of fluidity
        self._cumulative_fluidity: float = 1.0
        # Track last jump for recovery counting
        self._last_jump_turn: int = 0
        self._last_state: Optional[StateSnapshot] = None

    def _init_db(self) -> None:
        """Telemetry store for fluidity audits and regression analysis."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS pedi_reports (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    turn_id INTEGER NOT NULL,
                    timestamp TEXT NOT NULL,
                    state_jump REAL,
                    fluidity_score REAL,
                    cumulative_fluidity REAL,
                    recovered INTEGER,
                    recovery_turns INTEGER,
                    crisis_flag INTEGER,
                    dimensions_breakdown TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS pedi_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    turn_id INTEGER NOT NULL,
                    timestamp TEXT NOT NULL,
                    needs_json TEXT NOT NULL,
                    context_tokens_used INTEGER
                )
            """)
            conn.commit()

    # ── Core Mathematics ───────────────────────────────────────────────

    @staticmethod
    def _euclidean_jump(prev: Dict[str, float], curr: Dict[str, float]) -> float:
        """
        Compute the Euclidean distance between two state vectors.

        Formula:
            Δ = sqrt( Σ_{d ∈ D} (curr[d] - prev[d])² )

        where D is the set of tracked need dimensions.

        Parameters
        ----------
        prev, curr : dict
            Mappings from dimension name to value in [0, 1].

        Returns
        -------
        float
            Non-negative jump magnitude. 0.0 means perfect continuity.
        """
        squared_diffs = []
        for dim in NEED_DIMENSIONS:
            v_prev = max(0.0, min(1.0, prev.get(dim, 0.0)))
            v_curr = max(0.0, min(1.0, curr.get(dim, 0.0)))
            squared_diffs.append((v_curr - v_prev) ** 2)

        return math.sqrt(sum(squared_diffs))

    @staticmethod
    def _state_fluidity_score(jump: float) -> float:
        """
        Map a raw Euclidean jump to a fluidity score in [0, 1].

        Formula:
            SFS = max( 0, 1 - (Δ / Δ_max) )

        where Δ_max = MAX_TOLERATED_JUMP.

        Interpretation:
            SFS = 1.0 → perfect continuity (Δ = 0)
            SFS = 0.0 → fully disruptive jump (Δ ≥ Δ_max)
        """
        if jump <= 0.0:
            return 1.0
        score = 1.0 - (jump / MAX_TOLERATED_JUMP)
        return max(0.0, min(1.0, score))

    def _update_cumulative_fluidity(self, sfs: float) -> float:
        """
        Update the exponential moving average of fluidity.

        Formula:
            CF_t = β * CF_{t-1} + (1 - β) * SFS_t

        A high β (close to 1.0) makes the average resistant to single
        bad turns — it models long-term resilience rather than momentary
        fluctuation.
        """
        self._cumulative_fluidity = (
            FLUIDITY_EMA_BETA * self._cumulative_fluidity
            + (1.0 - FLUIDITY_EMA_BETA) * sfs
        )
        return self._cumulative_fluidity

    @staticmethod
    def _compute_recovery_turns(current_turn: int, last_jump_turn: int) -> int:
        """Turns elapsed since the last detected state jump."""
        return max(0, current_turn - last_jump_turn)

    # ── Evaluation API ─────────────────────────────────────────────────

    def record_snapshot(self, snapshot: StateSnapshot) -> None:
        """Persist a state snapshot for later fluidity analysis."""
        needs_json = json.dumps(snapshot.needs)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO pedi_snapshots
                (turn_id, timestamp, needs_json, context_tokens_used)
                VALUES (?, ?, ?, ?)
                """,
                (
                    snapshot.turn_id,
                    snapshot.timestamp.isoformat(),
                    needs_json,
                    snapshot.context_tokens_used,
                ),
            )
            conn.commit()
        self._last_state = snapshot

    def evaluate_reset(
        self,
        pre_reset: StateSnapshot,
        post_reset: StateSnapshot,
        reset_event: ResetEvent,
    ) -> FluidityReport:
        """
        Compute the full PEDI fluidity report across a context reset.

        This is the primary entry point: call it whenever the prompt builder
        truncates history or a session resumes after a gap.
        """
        # 1. Compute Euclidean jump between pre- and post-reset vectors
        jump = self._euclidean_jump(pre_reset.needs, post_reset.needs)

        # 2. Convert jump to fluidity score
        sfs = self._state_fluidity_score(jump)

        # 3. Update cumulative fluidity EMA
        cf = self._update_cumulative_fluidity(sfs)

        # 4. Recovery tracking
        recovery_turns = self._compute_recovery_turns(
            post_reset.turn_id, self._last_jump_turn
        )
        recovered = sfs >= RECOVERY_THRESHOLD
        if jump > 0.05:  # any meaningful jump resets the recovery clock
            self._last_jump_turn = post_reset.turn_id

        # 5. Crisis detection
        crisis = cf < CRITICAL_FLUIDITY

        # 6. Per-dimension breakdown for diagnostics
        breakdown = {}
        for dim in NEED_DIMENSIONS:
            v_pre = pre_reset.needs.get(dim, 0.0)
            v_post = post_reset.needs.get(dim, 0.0)
            breakdown[dim] = round(v_post - v_pre, 4)

        report = FluidityReport(
            turn_id=post_reset.turn_id,
            timestamp=datetime.now(timezone.utc),
            state_jump=round(jump, 4),
            fluidity_score=round(sfs, 4),
            cumulative_fluidity=round(cf, 4),
            recovered=recovered,
            recovery_turns=recovery_turns,
            crisis_flag=crisis,
            dimensions_breakdown=breakdown,
        )

        self._log_report(report)
        return report

    def _log_report(self, report: FluidityReport) -> None:
        """Persist the fluidity report to SQLite."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO pedi_reports
                (turn_id, timestamp, state_jump, fluidity_score,
                 cumulative_fluidity, recovered, recovery_turns, crisis_flag,
                 dimensions_breakdown)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    report.turn_id,
                    report.timestamp.isoformat(),
                    report.state_jump,
                    report.fluidity_score,
                    report.cumulative_fluidity,
                    int(report.recovered),
                    report.recovery_turns,
                    int(report.crisis_flag),
                    json.dumps(report.dimensions_breakdown),
                ),
            )
            conn.commit()

    # ── Diagnostics ────────────────────────────────────────────────────

    def get_recent_reports(self, limit: int = 50) -> List[Dict]:
        """Return recent PEDI reports for dashboard/audit display."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM pedi_reports ORDER BY timestamp DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_crisis_count(self, since: Optional[datetime] = None) -> int:
        """Count how many crisis events have occurred in the lookback window."""
        since = since or datetime(1970, 1, 1, tzinfo=timezone.utc)
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM pedi_reports WHERE crisis_flag = 1 AND timestamp > ?",
                (since.isoformat(),),
            ).fetchone()
        return row[0] if row else 0

    def get_fluidity_trend(self, window: int = 20) -> List[float]:
        """Return the last N cumulative fluidity values for trend plotting."""
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT cumulative_fluidity FROM pedi_reports ORDER BY timestamp DESC LIMIT ?",
                (window,),
            ).fetchall()
        return [r[0] for r in reversed(rows)]

    def get_last_snapshot(self) -> Optional[StateSnapshot]:
        """Retrieve the last recorded snapshot from the database."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                row = conn.execute(
                    "SELECT * FROM pedi_snapshots ORDER BY timestamp DESC LIMIT 1"
                ).fetchone()
                if row:
                    needs = json.loads(row["needs_json"])
                    from datetime import datetime
                    # Handle possible timezone suffix or simple isoformat strings
                    ts_str = row["timestamp"]
                    # Replace Z with +00:00 for fromisoformat compatibility in python versions before 3.11 if needed
                    if ts_str.endswith("Z"):
                        ts_str = ts_str[:-1] + "+00:00"
                    return StateSnapshot(
                        timestamp=datetime.fromisoformat(ts_str),
                        turn_id=row["turn_id"],
                        needs=needs,
                        context_tokens_used=row["context_tokens_used"],
                    )
        except Exception:
            pass
        return None


# ── Convenience factory ──────────────────────────────────────────────

_default_pedi: Optional[PediIndex] = None


def get_pedi() -> PediIndex:
    """Return the singleton PediIndex instance."""
    global _default_pedi
    if _default_pedi is None:
        _default_pedi = PediIndex()
    return _default_pedi


# Re-import json here to avoid NameError in _log_report
import json  # noqa: E402
