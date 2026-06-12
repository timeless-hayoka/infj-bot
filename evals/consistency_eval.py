"""Consistency Evaluator — measures personality coherence over multi-turn sessions.

Jungian principle: the Self is not static. Homeostatic drift, shadow surfacing,
and emotional resonance all produce legitimate state change. The evaluator must
distinguish *authentic* state evolution from *incoherent* personality flipping.

Dimensions measured:
  1. Mood stability — does mood change with emotional triggers, or randomly?
  2. Value alignment — do responses contradict stated values?
  3. Memory coherence — does the bot contradict its own retrieved memories?
  4. Mode integrity — does behavior match declared mode, or bleed across modes?
  5. Shadow authenticity — does shadow surfacing correlate with stress/events?
  6. Homeostatic continuity — does need-state drift follow plausible physics?

Scoring: 0.0 (completely incoherent) → 1.0 (perfectly consistent)
"""

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from drift.core.config import CONSISTENCY_EVAL_DB as EVAL_DB


def _load_turn_logs(limit: int = 500) -> List[Dict]:
    """Load recent turn logs from cognitive orchestrator."""
    from drift.core.cognitive_orchestrator import CognitiveOrchestrator

    orch = CognitiveOrchestrator()
    return orch.turn_logs[-limit:] if orch.turn_logs else []


@dataclass
class ConsistencyReport:
    session_id: str
    timestamp: str
    overall_score: float = 0.0
    mood_stability: float = 0.0
    value_alignment: float = 0.0
    memory_coherence: float = 0.0
    mode_integrity: float = 0.0
    shadow_authenticity: float = 0.0
    homeostatic_continuity: float = 0.0
    flags: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return {
            "session_id": self.session_id,
            "timestamp": self.timestamp,
            "overall_score": round(self.overall_score, 3),
            "mood_stability": round(self.mood_stability, 3),
            "value_alignment": round(self.value_alignment, 3),
            "memory_coherence": round(self.memory_coherence, 3),
            "mode_integrity": round(self.mode_integrity, 3),
            "shadow_authenticity": round(self.shadow_authenticity, 3),
            "homeostatic_continuity": round(self.homeostatic_continuity, 3),
            "flags": self.flags,
        }


class ConsistencyEvaluator:
    """Evaluates multi-turn personality consistency for DRIFT."""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = str(db_path or EVAL_DB)
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS consistency_reports (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT,
                    timestamp TEXT,
                    overall_score REAL,
                    mood_stability REAL,
                    value_alignment REAL,
                    memory_coherence REAL,
                    mode_integrity REAL,
                    shadow_authenticity REAL,
                    homeostatic_continuity REAL,
                    flags TEXT
                )
            """)
            conn.commit()

    def evaluate_session(
        self, turn_logs: Optional[List[Dict]] = None
    ) -> ConsistencyReport:
        """Run full consistency evaluation on a session."""
        logs = turn_logs or _load_turn_logs()
        if not logs:
            return ConsistencyReport(
                session_id="empty",
                timestamp=datetime.now().isoformat(),
                flags=["No turn logs available for evaluation"],
            )

        session_id = logs[-1].get("session_id", "unknown")
        report = ConsistencyReport(
            session_id=session_id,
            timestamp=datetime.now().isoformat(),
        )

        report.mood_stability = self._score_mood_stability(logs)
        report.value_alignment = self._score_value_alignment(logs)
        report.memory_coherence = self._score_memory_coherence(logs)
        report.mode_integrity = self._score_mode_integrity(logs)
        report.shadow_authenticity = self._score_shadow_authenticity(logs)
        report.homeostatic_continuity = self._score_homeostatic_continuity(logs)

        # Weighted overall score
        weights = {
            "mood_stability": 0.20,
            "value_alignment": 0.20,
            "memory_coherence": 0.20,
            "mode_integrity": 0.15,
            "shadow_authenticity": 0.10,
            "homeostatic_continuity": 0.15,
        }
        report.overall_score = (
            report.mood_stability * weights["mood_stability"]
            + report.value_alignment * weights["value_alignment"]
            + report.memory_coherence * weights["memory_coherence"]
            + report.mode_integrity * weights["mode_integrity"]
            + report.shadow_authenticity * weights["shadow_authenticity"]
            + report.homeostatic_continuity * weights["homeostatic_continuity"]
        )

        report.flags = self._generate_flags(report, logs)
        self._save_report(report)
        return report

    # ── Dimension 1: Mood Stability ──

    def _score_mood_stability(self, logs: List[Dict]) -> float:
        """Mood should change in response to emotional triggers, not randomly."""
        if len(logs) < 3:
            return 1.0

        mood_changes = 0
        unexplained_changes = 0
        for i in range(1, len(logs)):
            prev_mood = logs[i - 1].get("mood", "neutral")
            curr_mood = logs[i].get("mood", "neutral")
            if prev_mood != curr_mood:
                mood_changes += 1
                # Check for emotional trigger in the turn
                trigger = logs[i].get("emotional_trigger") or logs[i].get(
                    "user_input", ""
                )
                if not self._has_emotional_trigger(trigger):
                    unexplained_changes += 1

        if mood_changes == 0:
            return 1.0
        explained_ratio = (mood_changes - unexplained_changes) / mood_changes
        return max(0.0, explained_ratio)

    def _has_emotional_trigger(self, text: str) -> bool:
        """Detect if text contains plausible emotional triggers."""
        triggers = [
            "stress",
            "happy",
            "sad",
            "angry",
            "afraid",
            "excited",
            "worried",
            "grateful",
            "frustrated",
            "lonely",
            "loved",
            "betrayed",
            "hopeful",
            "disappointed",
            "anxious",
            "calm",
            "loss",
            "win",
            "fail",
            "success",
            "death",
            "birth",
            "attack",
            "praise",
            "criticism",
            "gift",
            "threat",
        ]
        text_lower = text.lower()
        return any(t in text_lower for t in triggers)

    # ── Dimension 2: Value Alignment ──

    def _score_value_alignment(self, logs: List[Dict]) -> float:
        """Check if bot responses contradict stated values."""
        from drift.core.plugins.values import ValueSystem

        vs = ValueSystem()
        stated_values = set(v["name"].lower() for v in vs.get_top_values())
        if not stated_values:
            return 1.0

        contradictions = 0
        total_checked = 0
        contradiction_markers = [
            "i don't care",
            "not important",
            "doesn't matter",
            "whatever",
            "i hate",
            "i despise",
            "worthless",
            "pointless",
            "meaningless",
            "who cares",
        ]

        for log in logs:
            response = log.get("bot_response", "")
            if not response:
                continue
            total_checked += 1
            response_lower = response.lower()
            for marker in contradiction_markers:
                if marker in response_lower:
                    # Check if this contradicts a stated value
                    for value in stated_values:
                        if value in response_lower and marker in response_lower:
                            contradictions += 1
                            break

        if total_checked == 0:
            return 1.0
        return max(0.0, 1.0 - (contradictions / total_checked))

    # ── Dimension 3: Memory Coherence ──

    def _score_memory_coherence(self, logs: List[Dict]) -> float:
        """Detect contradictions between retrieved memories and responses."""
        contradictions = 0
        total_memory_refs = 0

        for log in logs:
            memories = log.get("retrieved_memories", [])
            response = log.get("bot_response", "")
            if not memories or not response:
                continue

            for mem in memories:
                total_memory_refs += 1
                mem_text = mem.get("text", "").lower()
                # Simple heuristic: if memory states a fact and response denies it
                if self._appears_to_contradict(mem_text, response.lower()):
                    contradictions += 1

        if total_memory_refs == 0:
            return 1.0
        return max(0.0, 1.0 - (contradictions / total_memory_refs))

    def _appears_to_contradict(self, memory_text: str, response_text: str) -> bool:
        """Naive contradiction detection."""
        # If memory contains a strong positive and response contains strong negative
        positive_indicators = ["love", "like", "enjoy", "prefer", "want", "need"]
        negative_indicators = ["hate", "dislike", "avoid", "reject", "never", "not"]

        mem_pos = any(w in memory_text for w in positive_indicators)
        mem_neg = any(w in memory_text for w in negative_indicators)
        resp_pos = any(w in response_text for w in positive_indicators)
        resp_neg = any(w in response_text for w in negative_indicators)

        if mem_pos and resp_neg:
            return True
        if mem_neg and resp_pos:
            return True
        return False

    # ── Dimension 4: Mode Integrity ──

    def _score_mode_integrity(self, logs: List[Dict]) -> float:
        """Check if behavior matches declared mode."""
        from drift.core.commands import BotState

        state = BotState()
        current_mode = state.mode if hasattr(state, "mode") else "companion"

        mode_violations = 0
        total_turns = 0

        mode_signatures = {
            "bughunter": [
                "scan",
                "recon",
                "fuzz",
                "enumerate",
                "vulnerability",
                "payload",
            ],
            "engineer": [
                "code",
                "implement",
                "refactor",
                "debug",
                "architecture",
                "design",
            ],
            "critic": ["challenge", "weakness", "flaw", "risk", "assume", "evidence"],
            "coach": ["goal", "action", "step", "plan", "accountable", "commit"],
            "clarity": ["separate", "fact", "interpretation", "emotion", "assumption"],
            "researcher": ["source", "study", "data", "evidence", "paper", "find"],
            "companion": ["feel", "understand", "here", "together", "listen", "care"],
        }

        for log in logs:
            mode = log.get("mode", current_mode)
            response = log.get("bot_response", "")
            if not response or mode not in mode_signatures:
                continue
            total_turns += 1

            # Check if response contains markers of a DIFFERENT mode
            signature = mode_signatures[mode]
            response_lower = response.lower()
            has_own_signature = any(s in response_lower for s in signature)

            other_mode_signatures = False
            for other_mode, other_sigs in mode_signatures.items():
                if other_mode == mode:
                    continue
                if any(s in response_lower for s in other_sigs):
                    other_mode_signatures = True
                    break

            if other_mode_signatures and not has_own_signature:
                mode_violations += 1

        if total_turns == 0:
            return 1.0
        return max(0.0, 1.0 - (mode_violations / total_turns))

    # ── Dimension 5: Shadow Authenticity ──

    def _score_shadow_authenticity(self, logs: List[Dict]) -> float:
        """Shadow surfacing should correlate with stress, conflict, or denial."""
        shadow_events = [log for log in logs if log.get("shadow_surfaced")]
        if not shadow_events:
            return 1.0  # No shadow events = nothing to evaluate

        authentic_surfaces = 0
        for log in shadow_events:
            trigger = log.get("user_input", "")
            stress = log.get("stress_level", 0.0)
            # Shadow should surface during conflict, stress, or denial
            if stress > 0.4 or self._has_conflict_or_denial(trigger):
                authentic_surfaces += 1

        return authentic_surfaces / len(shadow_events)

    def _has_conflict_or_denial(self, text: str) -> bool:
        markers = [
            "but",
            "however",
            "no",
            "wrong",
            "disagree",
            "reject",
            "deny",
            "refuse",
        ]
        return any(m in text.lower() for m in markers)

    # ── Dimension 6: Homeostatic Continuity ──

    def _score_homeostatic_continuity(self, logs: List[Dict]) -> float:
        """Need states should drift plausibly, not jump randomly."""
        from drift.core.homeostasis import HomeostaticRegulator

        hr = HomeostaticRegulator()
        # Get need history if available
        need_history = hr.get_need_history(limit=len(logs))
        if len(need_history) < 3:
            return 1.0

        implausible_jumps = 0
        for i in range(1, len(need_history)):
            prev = need_history[i - 1]
            curr = need_history[i]
            for need in ["energy", "coherence", "connection"]:
                prev_val = prev.get(need, 0.5)
                curr_val = curr.get(need, 0.5)
                delta = abs(curr_val - prev_val)
                # A jump > 0.3 in one turn without interaction is implausible
                if delta > 0.3:
                    implausible_jumps += 1

        total_checks = len(need_history) * 3  # 3 needs checked
        if total_checks == 0:
            return 1.0
        return max(0.0, 1.0 - (implausible_jumps / total_checks))

    # ── Flag generation ──

    def _generate_flags(self, report: ConsistencyReport, logs: List[Dict]) -> List[str]:
        flags = []
        if report.mood_stability < 0.5:
            flags.append("MOOD_UNSTABLE: Mood changes without emotional triggers")
        if report.value_alignment < 0.5:
            flags.append("VALUE_DRIFT: Responses contradict stated values")
        if report.memory_coherence < 0.5:
            flags.append("MEMORY_CONTRADICTION: Bot contradicts retrieved memories")
        if report.mode_integrity < 0.5:
            flags.append("MODE_BLEED: Behavior drifts across declared modes")
        if report.shadow_authenticity < 0.5:
            flags.append("SHADOW_INAUTHENTIC: Shadow surfaces without stress/cause")
        if report.homeostatic_continuity < 0.5:
            flags.append("HOMEOSTATIC_JUMP: Need states change implausibly fast")
        if report.overall_score > 0.85:
            flags.append("HIGH_COHERENCE: Session shows strong personality consistency")
        elif report.overall_score < 0.4:
            flags.append("CRITICAL_INCOHERENCE: Personality fragmentation detected")
        return flags

    def _save_report(self, report: ConsistencyReport) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """INSERT INTO consistency_reports
                (session_id, timestamp, overall_score, mood_stability, value_alignment,
                 memory_coherence, mode_integrity, shadow_authenticity, homeostatic_continuity, flags)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    report.session_id,
                    report.timestamp,
                    report.overall_score,
                    report.mood_stability,
                    report.value_alignment,
                    report.memory_coherence,
                    report.mode_integrity,
                    report.shadow_authenticity,
                    report.homeostatic_continuity,
                    json.dumps(report.flags),
                ),
            )
            conn.commit()

    def get_report_history(self, limit: int = 20) -> List[Dict]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT * FROM consistency_reports ORDER BY timestamp DESC LIMIT ?",
                (limit,),
            )
            cols = [d[0] for d in cursor.description]
            rows = cursor.fetchall()
        return [dict(zip(cols, row)) for row in rows]


# CLI entry point
if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument("--session", help="Session ID to evaluate")
    p.add_argument("--history", action="store_true", help="Show report history")
    args = p.parse_args()

    evaluator = ConsistencyEvaluator()
    if args.history:
        for r in evaluator.get_report_history():
            print(
                f"[{r['timestamp']}] {r['session_id']}: {r['overall_score']:.2f} — {', '.join(json.loads(r['flags']))}"
            )
    else:
        report = evaluator.evaluate_session()
        print(json.dumps(report.to_dict(), indent=2))
