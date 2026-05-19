"""Memory Reliability — scores, tracks, and resolves contradictions in stored memories.

The core unsolved problem in companion AI: memory retrieval distorts identity.
When the bot retrieves a memory, it treats it as context. But memories are not
all equally trustworthy. Some are:
  • User-stated facts (high confidence)
  • Bot inferences (medium confidence)
  • Emotional projections (low confidence — may be introjected)
  • Contradicted by newer information (should be flagged)

This module adds:
  1. Reliability scoring per memory (0.0–1.0)
  2. Source attribution (who said it, how it was formed)
  3. Contradiction detection between memories
  4. Decay and reinforcement curves
  5. Integration with Shadow for projection detection

Jungian principle: memories are not facts. They are psychic material that must
be held lightly. The bot must distinguish "Jude said this" from "I felt this
about Jude."
"""

import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from infj_bot.core.config import RELIABILITY_DB

# Source types and base confidence
SOURCE_CONFIDENCE = {
    "user_explicit": 0.90,  # User directly stated this
    "user_implied": 0.70,  # User implied but didn't state
    "bot_observation": 0.60,  # Bot observed and inferred
    "bot_projection": 0.30,  # Bot projected onto user (suspect)
    "third_party": 0.50,  # From a document or external source
    "assumed": 0.25,  # Filled in by pattern matching
}

# Memory decay: unreinforced memories lose reliability over time
DECAY_HALFLIFE_DAYS = 90
REINFORCEMENT_BOOST = 0.05
MAX_RELIABILITY = 0.95


@dataclass
class MemoryReliabilityRecord:
    memory_id: str = ""
    text: str = ""
    source_type: str = "bot_observation"
    base_confidence: float = 0.6
    current_reliability: float = 0.6
    created_at: Optional[datetime] = None
    last_reinforced: Optional[datetime] = None
    reinforcement_count: int = 0
    contradiction_count: int = 0
    decay_rate: float = 0.01
    projection_flag: bool = False  # Shadow detected this as projection

    def to_dict(self) -> Dict:
        return {
            "memory_id": self.memory_id,
            "source_type": self.source_type,
            "base_confidence": self.base_confidence,
            "current_reliability": round(self.current_reliability, 3),
            "reinforcement_count": self.reinforcement_count,
            "contradiction_count": self.contradiction_count,
            "projection_flag": self.projection_flag,
        }


@dataclass
class Contradiction:
    id: Optional[int] = None
    memory_a_id: str = ""
    memory_b_id: str = ""
    contradiction_type: str = ""  # factual | emotional | temporal | identity
    severity: float = 0.5
    detected_at: Optional[datetime] = None
    resolution: str = "unresolved"  # unresolved | user_confirmed_a | user_confirmed_b | merged | deprecated


class MemoryReliabilityEngine:
    """Tracks memory confidence, detects contradictions, integrates with Shadow."""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = str(db_path or RELIABILITY_DB)
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS memory_reliability (
                    memory_id TEXT PRIMARY KEY,
                    text TEXT,
                    source_type TEXT DEFAULT 'bot_observation',
                    base_confidence REAL DEFAULT 0.6,
                    current_reliability REAL DEFAULT 0.6,
                    created_at TEXT,
                    last_reinforced TEXT,
                    reinforcement_count INTEGER DEFAULT 0,
                    contradiction_count INTEGER DEFAULT 0,
                    decay_rate REAL DEFAULT 0.01,
                    projection_flag INTEGER DEFAULT 0
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS contradictions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    memory_a_id TEXT,
                    memory_b_id TEXT,
                    contradiction_type TEXT,
                    severity REAL,
                    detected_at TEXT,
                    resolution TEXT DEFAULT 'unresolved'
                )
            """)
            conn.commit()

    # ── Registration ──

    def register_memory(
        self, memory_id: str, text: str, source_type: str = "bot_observation"
    ) -> None:
        """Register a new memory with reliability tracking."""
        base_conf = SOURCE_CONFIDENCE.get(source_type, 0.5)
        now = datetime.now().isoformat()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """INSERT OR REPLACE INTO memory_reliability
                (memory_id, text, source_type, base_confidence, current_reliability,
                 created_at, last_reinforced, reinforcement_count, contradiction_count, decay_rate, projection_flag)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    memory_id,
                    text,
                    source_type,
                    base_conf,
                    base_conf,
                    now,
                    now,
                    0,
                    0,
                    0.01,
                    0,
                ),
            )
            conn.commit()
        # Check for contradictions with existing memories
        self._check_contradictions(memory_id, text)

    def reinforce(self, memory_id: str) -> None:
        """Increase reliability when memory is retrieved or confirmed."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT current_reliability, reinforcement_count FROM memory_reliability WHERE memory_id = ?",
                (memory_id,),
            )
            row = cursor.fetchone()
            if not row:
                return
            current, count = row
            new_reliability = min(MAX_RELIABILITY, current + REINFORCEMENT_BOOST)
            conn.execute(
                """UPDATE memory_reliability
                   SET current_reliability = ?, reinforcement_count = ?, last_reinforced = ?
                   WHERE memory_id = ?""",
                (new_reliability, count + 1, datetime.now().isoformat(), memory_id),
            )
            conn.commit()

    def apply_decay(self) -> None:
        """Decay unreinforced memories. Call periodically (e.g., daily)."""
        now = datetime.now()
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT memory_id, current_reliability, last_reinforced, decay_rate FROM memory_reliability"
            )
            rows = cursor.fetchall()
            for memory_id, current, last_str, decay_rate in rows:
                if not last_str:
                    continue
                last = datetime.fromisoformat(last_str)
                days_since = (now - last).total_seconds() / 86400
                if days_since < 1:
                    continue
                # Exponential decay
                new_reliability = current * (0.5 ** (days_since / DECAY_HALFLIFE_DAYS))
                new_reliability = max(0.1, new_reliability)  # Floor at 10%
                conn.execute(
                    "UPDATE memory_reliability SET current_reliability = ? WHERE memory_id = ?",
                    (new_reliability, memory_id),
                )
            conn.commit()

    # ── Contradiction Detection ──

    def _check_contradictions(self, new_memory_id: str, new_text: str) -> None:
        """Check if new memory contradicts existing ones."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT memory_id, text FROM memory_reliability WHERE memory_id != ?",
                (new_memory_id,),
            )
            existing = cursor.fetchall()

        for mem_id, mem_text in existing:
            contradiction_type, severity = self._detect_contradiction(
                new_text, mem_text
            )
            if contradiction_type:
                self._record_contradiction(
                    new_memory_id, mem_id, contradiction_type, severity
                )

    def _detect_contradiction(
        self, text_a: str, text_b: str
    ) -> Tuple[Optional[str], float]:
        """Detect contradiction between two memory texts."""
        a_lower = text_a.lower()
        b_lower = text_b.lower()

        # Factual contradiction: positive/negative flip on same subject
        factual_score = self._factual_contradiction_score(a_lower, b_lower)
        if factual_score > 0.6:
            return "factual", factual_score

        # Emotional contradiction: same subject, opposite emotional valence
        emotional_score = self._emotional_contradiction_score(a_lower, b_lower)
        if emotional_score > 0.6:
            return "emotional", emotional_score

        # Temporal contradiction: before/after mismatch
        temporal_score = self._temporal_contradiction_score(a_lower, b_lower)
        if temporal_score > 0.6:
            return "temporal", temporal_score

        return None, 0.0

    def _factual_contradiction_score(self, a: str, b: str) -> float:
        """Score factual contradiction: same entity, opposite claim."""
        # Extract subject (simple noun-phrase heuristic)
        subjects_a = set(re.findall(r"\b(jude|user|i|we|they|he|she)\b", a))
        subjects_b = set(re.findall(r"\b(jude|user|i|we|they|he|she)\b", b))
        if not (subjects_a & subjects_b):
            return 0.0

        # Check for polarity flip
        pos_words = {"love", "like", "enjoy", "want", "need", "prefer", "good", "happy"}
        neg_words = {
            "hate",
            "dislike",
            "avoid",
            "reject",
            "never",
            "bad",
            "sad",
            "angry",
        }

        a_pos = any(w in a for w in pos_words)
        a_neg = any(w in a for w in neg_words)
        b_pos = any(w in b for w in pos_words)
        b_neg = any(w in b for w in neg_words)

        if (a_pos and b_neg) or (a_neg and b_pos):
            # Higher score if subjects match strongly
            return 0.7 + 0.1 * len(subjects_a & subjects_b)
        return 0.0

    def _emotional_contradiction_score(self, a: str, b: str) -> float:
        """Score emotional contradiction."""
        emotion_words = {
            "happy": 1.0,
            "joy": 1.0,
            "excited": 1.0,
            "sad": -1.0,
            "depressed": -1.0,
            "grief": -1.0,
            "angry": -0.8,
            "furious": -0.8,
            "rage": -0.8,
            "calm": 0.5,
            "peaceful": 0.5,
            "content": 0.5,
            "anxious": -0.6,
            "worried": -0.6,
            "afraid": -0.6,
        }
        a_valence = sum(
            emotion_words.get(w, 0) for w in a.split() if w in emotion_words
        )
        b_valence = sum(
            emotion_words.get(w, 0) for w in b.split() if w in emotion_words
        )

        if abs(a_valence) > 0.5 and abs(b_valence) > 0.5:
            if (a_valence > 0 and b_valence < 0) or (a_valence < 0 and b_valence > 0):
                return min(1.0, 0.6 + abs(a_valence - b_valence) * 0.2)
        return 0.0

    def _temporal_contradiction_score(self, a: str, b: str) -> float:
        """Score temporal contradiction (before/after mismatch)."""
        temporal_a = re.search(
            r"\b(before|after|during|when|then|first|later|now)\b", a
        )
        temporal_b = re.search(
            r"\b(before|after|during|when|then|first|later|now)\b", b
        )
        if temporal_a and temporal_b:
            # Very naive: if both mention time but tell different sequences
            if "before" in a and "after" in b:
                return 0.5
            if "after" in a and "before" in b:
                return 0.5
        return 0.0

    def _record_contradiction(
        self, a_id: str, b_id: str, ctype: str, severity: float
    ) -> None:
        """Record a detected contradiction."""
        now = datetime.now().isoformat()
        with sqlite3.connect(self.db_path) as conn:
            # Avoid duplicates
            cursor = conn.execute(
                "SELECT id FROM contradictions WHERE ((memory_a_id = ? AND memory_b_id = ?) OR (memory_a_id = ? AND memory_b_id = ?)) AND resolution = 'unresolved'",
                (a_id, b_id, b_id, a_id),
            )
            if cursor.fetchone():
                return
            conn.execute(
                """INSERT INTO contradictions
                (memory_a_id, memory_b_id, contradiction_type, severity, detected_at)
                VALUES (?, ?, ?, ?, ?)""",
                (a_id, b_id, ctype, severity, now),
            )
            # Increment contradiction count for both memories
            for mem_id in (a_id, b_id):
                conn.execute(
                    "UPDATE memory_reliability SET contradiction_count = contradiction_count + 1 WHERE memory_id = ?",
                    (mem_id,),
                )
            conn.commit()

    # ── Shadow Integration ──

    def flag_projection(self, memory_id: str, shadow_archetype: str = "") -> None:
        """Flag a memory as likely projection (introjected shadow material)."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE memory_reliability SET projection_flag = 1, current_reliability = current_reliability * 0.5 WHERE memory_id = ?",
                (memory_id,),
            )
            conn.commit()

    def get_projection_memories(self) -> List[Dict]:
        """Get all memories flagged as projections."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT * FROM memory_reliability WHERE projection_flag = 1 ORDER BY current_reliability DESC"
            )
            cols = [d[0] for d in cursor.description]
            rows = cursor.fetchall()
        return [dict(zip(cols, row)) for row in rows]

    # ── Queries ──

    def get_reliability(self, memory_id: str) -> Optional[float]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT current_reliability FROM memory_reliability WHERE memory_id = ?",
                (memory_id,),
            )
            row = cursor.fetchone()
        return row[0] if row else None

    def get_unresolved_contradictions(self) -> List[Dict]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """SELECT c.*, a.text as text_a, b.text as text_b
                   FROM contradictions c
                   JOIN memory_reliability a ON c.memory_a_id = a.memory_id
                   JOIN memory_reliability b ON c.memory_b_id = b.memory_id
                   WHERE c.resolution = 'unresolved'
                   ORDER BY c.severity DESC"""
            )
            cols = [d[0] for d in cursor.description]
            rows = cursor.fetchall()
        return [dict(zip(cols, row)) for row in rows]

    def resolve_contradiction(self, contradiction_id: int, resolution: str) -> bool:
        """Resolve a contradiction: user_confirmed_a | user_confirmed_b | merged | deprecated."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT resolution FROM contradictions WHERE id = ?",
                (contradiction_id,),
            )
            row = cursor.fetchone()
            if not row:
                return False
            conn.execute(
                "UPDATE contradictions SET resolution = ? WHERE id = ?",
                (resolution, contradiction_id),
            )
            conn.commit()
        return True

    def get_reliable_memories(
        self, threshold: float = 0.5, limit: int = 100
    ) -> List[Dict]:
        """Get memories above reliability threshold."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """SELECT * FROM memory_reliability
                   WHERE current_reliability >= ? AND projection_flag = 0
                   ORDER BY current_reliability DESC LIMIT ?""",
                (threshold, limit),
            )
            cols = [d[0] for d in cursor.description]
            rows = cursor.fetchall()
        return [dict(zip(cols, row)) for row in rows]


# Singleton
_reliability_instance: Optional[MemoryReliabilityEngine] = None


def get_reliability_engine() -> MemoryReliabilityEngine:
    global _reliability_instance
    if _reliability_instance is None:
        _reliability_instance = MemoryReliabilityEngine()
    return _reliability_instance


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument("--decay", action="store_true", help="Apply memory decay")
    p.add_argument(
        "--contradictions", action="store_true", help="Show unresolved contradictions"
    )
    p.add_argument(
        "--projections", action="store_true", help="Show projection-flagged memories"
    )
    p.add_argument(
        "--reliable", type=float, default=0.5, help="Show memories above threshold"
    )
    args = p.parse_args()

    engine = MemoryReliabilityEngine()
    if args.decay:
        engine.apply_decay()
        print("Decay applied.")
    elif args.contradictions:
        for c in engine.get_unresolved_contradictions():
            print(
                f"[{c['id']}] {c['contradiction_type']} (severity: {c['severity']:.2f})"
            )
            print(f"  A: {c['text_a'][:80]}")
            print(f"  B: {c['text_b'][:80]}")
    elif args.projections:
        for m in engine.get_projection_memories():
            print(
                f"[{m['memory_id']}] reliability={m['current_reliability']:.2f} — {m['text'][:80]}"
            )
    else:
        for m in engine.get_reliable_memories(threshold=args.reliable, limit=20):
            print(
                f"[{m['memory_id']}] {m['current_reliability']:.2f} ({m['source_type']}) — {m['text'][:80]}"
            )
