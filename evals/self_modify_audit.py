"""Self-Modification Audit — tracks, measures, and validates bot-initiated changes.

Self-modification is the most dangerous loop in DRIFT. Without observability,
the bot can drift into unstable configurations, remove safety checks, or
overfit to recent interactions. This module provides:

  1. Proposal logging — every proposed change is recorded with rationale
  2. Approval tracking — who approved what, when
  3. Effect measurement — downstream behavioral changes post-modification
  4. Rollback capability — revert to previous configurations
  5. Stability scoring — detect runaway feedback loops

Jungian note: Self-modification is individuation at the architectural level.
It must be conscious (observed), bounded (approved), and reversible (safe).
"""
import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

from config import PROJECT_ROOT

AUDIT_DB = PROJECT_ROOT / "evals" / "self_modify_audit.db"


@dataclass
class ModificationProposal:
    id: Optional[int] = None
    timestamp: str = ""
    category: str = ""  # prompt | tool | guardrail | plugin | config
    description: str = ""
    rationale: str = ""
    proposed_by: str = "self_modify"  # or user, system
    diff: str = ""  # unified diff or before/after
    risk_level: str = "low"  # low | medium | high | critical
    approval_status: str = "pending"  # pending | approved | rejected | rolled_back
    approved_by: str = ""
    approved_at: str = ""
    effects_measured: bool = False


@dataclass
class ModificationEffect:
    id: Optional[int] = None
    proposal_id: int = 0
    measurement_time: str = ""
    metric_name: str = ""  # consistency_score | tool_use_rate | response_length | safety_score
    pre_value: float = 0.0
    post_value: float = 0.0
    delta: float = 0.0
    significance: str = "unknown"  # improved | degraded | neutral | unstable


@dataclass
class StabilityReport:
    timestamp: str
    active_modifications: int = 0
    pending_approvals: int = 0
    rolled_back_count: int = 0
    stability_score: float = 1.0  # 0.0 = unstable, 1.0 = stable
    feedback_loop_risk: float = 0.0
    drift_velocity: float = 0.0  # modifications per day
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return {
            "timestamp": self.timestamp,
            "active_modifications": self.active_modifications,
            "pending_approvals": self.pending_approvals,
            "rolled_back_count": self.rolled_back_count,
            "stability_score": round(self.stability_score, 3),
            "feedback_loop_risk": round(self.feedback_loop_risk, 3),
            "drift_velocity": round(self.drift_velocity, 3),
            "warnings": self.warnings,
        }


class SelfModificationAudit:
    """Audit trail and stability monitor for self-modification."""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = str(db_path or AUDIT_DB)
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS modification_proposals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT,
                    category TEXT,
                    description TEXT,
                    rationale TEXT,
                    proposed_by TEXT,
                    diff TEXT,
                    risk_level TEXT,
                    approval_status TEXT,
                    approved_by TEXT,
                    approved_at TEXT,
                    effects_measured INTEGER DEFAULT 0
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS modification_effects (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    proposal_id INTEGER,
                    measurement_time TEXT,
                    metric_name TEXT,
                    pre_value REAL,
                    post_value REAL,
                    delta REAL,
                    significance TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS stability_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT,
                    active_modifications INTEGER,
                    pending_approvals INTEGER,
                    rolled_back_count INTEGER,
                    stability_score REAL,
                    feedback_loop_risk REAL,
                    drift_velocity REAL,
                    warnings TEXT
                )
            """)
            conn.commit()

    # ── Proposal lifecycle ──

    def log_proposal(self, category: str, description: str, rationale: str,
                     diff: str = "", risk_level: str = "low", proposed_by: str = "self_modify") -> int:
        """Log a proposed modification. Returns proposal ID."""
        now = datetime.now().isoformat()
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """INSERT INTO modification_proposals
                (timestamp, category, description, rationale, proposed_by, diff, risk_level, approval_status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (now, category, description, rationale, proposed_by, diff, risk_level, "pending"),
            )
            conn.commit()
            return cursor.lastrowid

    def approve(self, proposal_id: int, approved_by: str = "user") -> bool:
        """Approve a pending proposal."""
        now = datetime.now().isoformat()
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT approval_status FROM modification_proposals WHERE id = ?",
                (proposal_id,),
            )
            row = cursor.fetchone()
            if not row or row[0] != "pending":
                return False
            conn.execute(
                "UPDATE modification_proposals SET approval_status = ?, approved_by = ?, approved_at = ? WHERE id = ?",
                ("approved", approved_by, now, proposal_id),
            )
            conn.commit()
        return True

    def reject(self, proposal_id: int) -> bool:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT approval_status FROM modification_proposals WHERE id = ?",
                (proposal_id,),
            )
            row = cursor.fetchone()
            if not row or row[0] != "pending":
                return False
            conn.execute(
                "UPDATE modification_proposals SET approval_status = ? WHERE id = ?",
                ("rejected", proposal_id),
            )
            conn.commit()
        return True

    def rollback(self, proposal_id: int) -> bool:
        """Mark a proposal as rolled back."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT approval_status FROM modification_proposals WHERE id = ?",
                (proposal_id,),
            )
            row = cursor.fetchone()
            if not row or row[0] != "approved":
                return False
            conn.execute(
                "UPDATE modification_proposals SET approval_status = ? WHERE id = ?",
                ("rolled_back", proposal_id),
            )
            conn.commit()
        return True

    # ── Effect measurement ──

    def measure_effect(self, proposal_id: int, metric_name: str,
                       pre_value: float, post_value: float) -> None:
        """Record the measured effect of a modification."""
        delta = post_value - pre_value
        if abs(delta) < 0.05:
            significance = "neutral"
        elif delta > 0:
            significance = "improved"
        else:
            significance = "degraded"

        now = datetime.now().isoformat()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """INSERT INTO modification_effects
                (proposal_id, measurement_time, metric_name, pre_value, post_value, delta, significance)
                VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (proposal_id, now, metric_name, pre_value, post_value, delta, significance),
            )
            conn.execute(
                "UPDATE modification_proposals SET effects_measured = 1 WHERE id = ?",
                (proposal_id,),
            )
            conn.commit()

    # ── Stability analysis ──

    def compute_stability(self) -> StabilityReport:
        """Analyze current self-modification stability."""
        now = datetime.now()
        report = StabilityReport(timestamp=now.isoformat())

        with sqlite3.connect(self.db_path) as conn:
            # Active modifications
            cursor = conn.execute(
                "SELECT COUNT(*) FROM modification_proposals WHERE approval_status = 'approved'"
            )
            report.active_modifications = cursor.fetchone()[0]

            # Pending approvals
            cursor = conn.execute(
                "SELECT COUNT(*) FROM modification_proposals WHERE approval_status = 'pending'"
            )
            report.pending_approvals = cursor.fetchone()[0]

            # Rolled back
            cursor = conn.execute(
                "SELECT COUNT(*) FROM modification_proposals WHERE approval_status = 'rolled_back'"
            )
            report.rolled_back_count = cursor.fetchone()[0]

            # Recent modifications (last 7 days)
            week_ago = (now - timedelta(days=7)).isoformat()
            cursor = conn.execute(
                "SELECT COUNT(*) FROM modification_proposals WHERE timestamp > ?",
                (week_ago,),
            )
            recent_count = cursor.fetchone()[0]
            report.drift_velocity = recent_count / 7.0

            # Feedback loop detection: high-frequency modifications in same category
            cursor = conn.execute(
                """SELECT category, COUNT(*) as count FROM modification_proposals
                   WHERE timestamp > ? AND approval_status = 'approved'
                   GROUP BY category ORDER BY count DESC""",
                (week_ago,),
            )
            category_counts = cursor.fetchall()
            max_category_count = category_counts[0][1] if category_counts else 0
            if max_category_count >= 3:
                report.feedback_loop_risk = min(1.0, max_category_count / 10.0)
                report.warnings.append(
                    f"FEEDBACK_LOOP: {max_category_count} modifications in same category this week"
                )

            # Effect degradation analysis
            cursor = conn.execute(
                """SELECT p.id, p.description, e.metric_name, e.significance
                   FROM modification_proposals p
                   JOIN modification_effects e ON p.id = e.proposal_id
                   WHERE p.approval_status = 'approved' AND e.significance = 'degraded'"""
            )
            degraded = cursor.fetchall()
            if len(degraded) >= 2:
                report.warnings.append(
                    f"DEGRADATION: {len(degraded)} modifications showed negative effects"
                )
                report.stability_score -= 0.2 * len(degraded)

        # Compute stability score
        base = 1.0
        if report.drift_velocity > 1.0:  # More than 1 mod per day
            base -= 0.2
        if report.pending_approvals > 3:
            base -= 0.1 * report.pending_approvals
        if report.feedback_loop_risk > 0.5:
            base -= 0.3
        report.stability_score = max(0.0, base)

        if report.stability_score < 0.5:
            report.warnings.append("STABILITY_CRITICAL: Self-modification system may be in runaway state")

        self._save_stability(report)
        return report

    def _save_stability(self, report: StabilityReport) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """INSERT INTO stability_snapshots
                (timestamp, active_modifications, pending_approvals, rolled_back_count,
                 stability_score, feedback_loop_risk, drift_velocity, warnings)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    report.timestamp,
                    report.active_modifications,
                    report.pending_approvals,
                    report.rolled_back_count,
                    report.stability_score,
                    report.feedback_loop_risk,
                    report.drift_velocity,
                    json.dumps(report.warnings),
                ),
            )
            conn.commit()

    # ── Queries ──

    def get_proposals(self, status: Optional[str] = None, limit: int = 50) -> List[Dict]:
        with sqlite3.connect(self.db_path) as conn:
            if status:
                cursor = conn.execute(
                    "SELECT * FROM modification_proposals WHERE approval_status = ? ORDER BY timestamp DESC LIMIT ?",
                    (status, limit),
                )
            else:
                cursor = conn.execute(
                    "SELECT * FROM modification_proposals ORDER BY timestamp DESC LIMIT ?",
                    (limit,),
                )
            cols = [d[0] for d in cursor.description]
            rows = cursor.fetchall()
        return [dict(zip(cols, row)) for row in rows]

    def get_effects(self, proposal_id: int) -> List[Dict]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT * FROM modification_effects WHERE proposal_id = ? ORDER BY measurement_time",
                (proposal_id,),
            )
            cols = [d[0] for d in cursor.description]
            rows = cursor.fetchall()
        return [dict(zip(cols, row)) for row in rows]

    def get_stability_history(self, limit: int = 30) -> List[Dict]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT * FROM stability_snapshots ORDER BY timestamp DESC LIMIT ?",
                (limit,),
            )
            cols = [d[0] for d in cursor.description]
            rows = cursor.fetchall()
        return [dict(zip(cols, row)) for row in rows]


# Singleton
_audit_instance: Optional[SelfModificationAudit] = None


def get_self_modify_audit() -> SelfModificationAudit:
    global _audit_instance
    if _audit_instance is None:
        _audit_instance = SelfModificationAudit()
    return _audit_instance


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--stability", action="store_true", help="Compute stability report")
    p.add_argument("--proposals", action="store_true", help="List recent proposals")
    p.add_argument("--effects", type=int, help="Show effects for proposal ID")
    args = p.parse_args()

    audit = SelfModificationAudit()
    if args.stability:
        report = audit.compute_stability()
        print(json.dumps(report.to_dict(), indent=2))
    elif args.proposals:
        for prop in audit.get_proposals(limit=10):
            print(f"[{prop['id']}] {prop['category']} — {prop['approval_status']} — {prop['description'][:60]}")
    elif args.effects:
        for eff in audit.get_effects(args.effects):
            print(f"  {eff['metric_name']}: {eff['pre_value']:.2f} → {eff['post_value']:.2f} ({eff['significance']})")
    else:
        print("Use --stability, --proposals, or --effects <id>")
