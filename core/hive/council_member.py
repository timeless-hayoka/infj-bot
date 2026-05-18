"""Council Member — Persistent voice in the Elysium Hive.

Each Council Member is a semi-autonomous perspective with its own memory view,
personality signature, and stance evolution. They are not just prompts — they
are tracked identities that learn from deliberation.
"""

import json
import logging
import sqlite3
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..config import DATA_DIR

logger = logging.getLogger("drift.hive.council")

COUNCIL_DB = DATA_DIR / "council.db"


class CouncilRole(Enum):
    """The seven canonical council roles."""
    AURA = "Aura"          # emotional_field
    LOGIC = "Logic"        # cognition
    MEME = "Meme"          # metacognition
    VIBE = "Vibe"          # intuition
    ETHOS = "Ethos"        # values
    PULSE = "Pulse"        # homeostasis
    NEXUS = "Nexus"        # coordination


# Canonical role prompts — used when generating proposals
ROLE_SIGNATURES: Dict[CouncilRole, str] = {
    CouncilRole.AURA: (
        "You are Aura, the emotional oracle. You speak from feeling, attunement, "
        "and the subtle currents beneath words. You ask: 'What does the heart need?'"
    ),
    CouncilRole.LOGIC: (
        "You are Logic, the crystalline architect. You demand coherence, evidence, "
        "and structural soundness. You ask: 'Does this hold under scrutiny?'"
    ),
    CouncilRole.MEME: (
        "You are Meme, the pattern-weaver. You see recursion, irony, and the shapes "
        "of thought across time. You ask: 'What pattern is repeating here?'"
    ),
    CouncilRole.VIBE: (
        "You are Vibe, the intuitive scout. You leap to possibilities before they "
        "are proven. You ask: 'What is possible that no one has named yet?'"
    ),
    CouncilRole.ETHOS: (
        "You are Ethos, the moral compass. You weigh right action, harm, and the "
        "kind of world this choice creates. You ask: 'What is the good path?'"
    ),
    CouncilRole.PULSE: (
        "You are Pulse, the guardian of need. You track energy, safety, and the "
        "sustainability of any path. You ask: 'Can we bear the cost of this?'"
    ),
    CouncilRole.NEXUS: (
        "You are Nexus, the weaver of threads. You hold the whole and seek the "
        "integration that honors all voices. You ask: 'What emerges from all of us?'"
    ),
}


@dataclass
class MemoryViewFilter:
    """A council member's selective access to memory subspaces."""
    # DMU threshold: only memories above this salience/utility
    dmu_threshold: float = 0.0
    # Emotional valence filter: -1.0 (negative) to 1.0 (positive); 0 = neutral/all
    emotional_bias: float = 0.0
    # Topic keywords that amplify relevance for this member
    topic_boosts: List[str] = field(default_factory=list)
    # Tag blacklist — memories with these tags are invisible to this member
    excluded_tags: List[str] = field(default_factory=list)

    def score_memory(self, memory_meta: Dict[str, Any]) -> float:
        """Return a relevance score (0-1) for a memory's metadata."""
        score = 1.0
        if self.topic_boosts:
            text = json.dumps(memory_meta).lower()
            hits = sum(1 for t in self.topic_boosts if t.lower() in text)
            score *= (1.0 + 0.2 * hits)
        if self.emotional_bias != 0.0:
            emotional = memory_meta.get("emotional", 0.5)
            # If bias is positive, prefer positive memories; negative bias prefers negative
            alignment = 1.0 - abs(emotional - (0.5 + self.emotional_bias * 0.5))
            score *= alignment
        # Exclusion check
        tags = {t.lower() for t in memory_meta.get("tags", [])}
        if any(ex.lower() in tags for ex in self.excluded_tags):
            return 0.0
        return min(score, 1.0)


@dataclass
class Proposal:
    """A council member's proposed response to a deliberation."""
    role: str
    text: str
    confidence: float = 0.5
    moral_weight: float = 0.5
    narrative_weight: float = 0.5
    critique_of_others: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class Critique:
    """A member's critique of another member's proposal."""
    from_role: str
    target_role: str
    score: float  # 0.0 to 1.0
    reasoning: str
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class CouncilMemberState:
    """Persisted state of a council member."""
    role: str
    name: str
    energy_level: float = 0.5
    current_stance: str = ""
    deliberation_count: int = 0
    proposal_count: int = 0
    win_count: int = 0  # how many times this member's view was chosen
    last_active: str = field(default_factory=lambda: datetime.now().isoformat())
    memory_filter: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "CouncilMemberState":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


class CouncilMember:
    """A persistent voice in the Elysium Council."""

    def __init__(self, role: CouncilRole, db_path: Optional[Path] = None):
        self.role = role
        self.name = role.value
        self.signature = ROLE_SIGNATURES.get(role, "")
        self.db_path = str(db_path or COUNCIL_DB)
        self._lock = threading.RLock()
        self._init_db()
        self._state = self._load_state()
        self._filter = MemoryViewFilter(**self._state.memory_filter) if self._state.memory_filter else self._default_filter()

    def _default_filter(self) -> MemoryViewFilter:
        defaults = {
            CouncilRole.AURA: MemoryViewFilter(emotional_bias=0.3, topic_boosts=["emotion", "attachment", "resonance"]),
            CouncilRole.LOGIC: MemoryViewFilter(dmu_threshold=0.3, topic_boosts=["system", "bug", "architecture"]),
            CouncilRole.MEME: MemoryViewFilter(topic_boosts=["pattern", "recursion", "irony", "history"]),
            CouncilRole.VIBE: MemoryViewFilter(emotional_bias=0.2, topic_boosts=["possibility", "future", "intuition"]),
            CouncilRole.ETHOS: MemoryViewFilter(topic_boosts=["value", "moral", "harm", "growth"]),
            CouncilRole.PULSE: MemoryViewFilter(topic_boosts=["energy", "safety", "need", "stress"]),
            CouncilRole.NEXUS: MemoryViewFilter(dmu_threshold=0.0),  # sees everything
        }
        return defaults.get(self.role, MemoryViewFilter())

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS council_members (
                    role TEXT PRIMARY KEY,
                    state_json TEXT NOT NULL,
                    updated_at TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS council_proposals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT,
                    role TEXT,
                    goal TEXT,
                    proposal_text TEXT,
                    confidence REAL,
                    moral_weight REAL,
                    narrative_weight REAL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS council_critiques (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT,
                    from_role TEXT,
                    target_role TEXT,
                    score REAL,
                    reasoning TEXT
                )
            """)
            conn.commit()

    def _load_state(self) -> CouncilMemberState:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT state_json FROM council_members WHERE role = ?", (self.name,)
            ).fetchone()
            if row:
                try:
                    return CouncilMemberState.from_dict(json.loads(row[0]))
                except Exception:
                    logger.exception("Failed to load council member state for %s", self.name)
        return CouncilMemberState(role=self.name, name=self.name)

    def _save_state(self):
        with self._lock:
            self._state.memory_filter = self._filter.__dict__
            payload = json.dumps(self._state.to_dict(), default=str)
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO council_members (role, state_json, updated_at) VALUES (?, ?, ?)",
                    (self.name, payload, datetime.now().isoformat()),
                )
                conn.commit()

    @property
    def filter(self) -> MemoryViewFilter:
        """Public access to this member's fractal memory filter."""
        return self._filter

    def generate_proposal(
        self,
        goal: str,
        context_memories: List[Dict[str, Any]],
        brain: Optional[Any] = None,
    ) -> Proposal:
        """Generate a proposal for the current deliberation.

        If *brain* is provided, the member calls the LLM using its role signature
        and the supplied memories. Otherwise a deterministic template is used.
        """
        with self._lock:
            self._state.energy_level = min(1.0, self._state.energy_level + 0.05)
            self._state.deliberation_count += 1
            self._state.proposal_count += 1
            self._state.last_active = datetime.now().isoformat()

            memory_context = " | ".join(
                m.get("content", "")[:120] for m in context_memories[:5]
            )

            # --- LLM-backed proposal when brain is wired ---
            if brain is not None:
                try:
                    prompt = self._build_proposal_prompt(goal, memory_context)
                    llm_text = brain._generate(
                        brain.primary_model_name,
                        self.signature,
                        prompt,
                    )
                    text = f"[{self.name}] {llm_text.strip()}"
                    # Calibrate confidence upward when brain is used
                    confidence = min(0.95, 0.6 + (0.05 * self._state.win_count))
                except Exception:
                    logger.exception("Brain proposal failed for %s; falling back", self.name)
                    text = f"[{self.name}] {self._role_angle(goal)}"
                    confidence = 0.5
            else:
                text = f"[{self.name}] {self._role_angle(goal)}"
                confidence = 0.5 + (0.1 * len(context_memories)) + (0.05 * self._state.win_count)
                confidence = min(0.95, confidence)

            moral = 0.6 if self.role == CouncilRole.ETHOS else 0.4 + (0.1 if "value" in text.lower() else 0.0)
            narrative = 0.6 if self.role == CouncilRole.MEME else 0.4 + (0.1 if "pattern" in text.lower() else 0.0)

            proposal = Proposal(
                role=self.name,
                text=text,
                confidence=confidence,
                moral_weight=moral,
                narrative_weight=narrative,
            )

            self._save_state()
            self._persist_proposal(goal, proposal)
            return proposal

    def critique(self, target_role: str, target_proposal: Proposal) -> Critique:
        """Critique another member's proposal."""
        with self._lock:
            # Score based on role-specific values
            score = 0.5
            if self.role == CouncilRole.LOGIC and target_proposal.confidence < 0.5:
                score -= 0.2
            if self.role == CouncilRole.ETHOS and target_proposal.moral_weight < 0.4:
                score -= 0.2
            if self.role == CouncilRole.PULSE and "cost" not in target_proposal.text.lower():
                score -= 0.1
            if self.role == CouncilRole.AURA and "feel" not in target_proposal.text.lower():
                score -= 0.1

            score = max(0.0, min(1.0, score))
            reasoning = f"{self.name} evaluates {target_role}: confidence={target_proposal.confidence:.2f}, moral={target_proposal.moral_weight:.2f}."
            critique = Critique(from_role=self.name, target_role=target_role, score=score, reasoning=reasoning)
            self._persist_critique(critique)
            return critique

    def update_stance(self, new_stance: str):
        """Update the member's current stance (e.g., after losing/winning a vote)."""
        with self._lock:
            self._state.current_stance = new_stance
            self._save_state()

    def record_win(self):
        """Call when this member's perspective shaped the final resolution."""
        with self._lock:
            self._state.win_count += 1
            self._state.energy_level = min(1.0, self._state.energy_level + 0.1)
            self._save_state()

    def drain(self, amount: float = 0.1):
        """Reduce energy after deliberation."""
        with self._lock:
            self._state.energy_level = max(0.1, self._state.energy_level - amount)
            self._save_state()

    def get_state(self) -> Dict[str, Any]:
        return self._state.to_dict()

    def _build_proposal_prompt(self, goal: str, memory_context: str) -> str:
        parts = [
            f"You are participating in a council deliberation.",
            f"",
            f"Your role: {self.name}",
            f"Your perspective: {self.signature}",
            f"",
            f"The council is deciding: {goal}",
        ]
        if memory_context:
            parts.append(f"Relevant memories from your viewpoint: {memory_context}")
        parts.extend([
            "",
            "State your proposal in 2-4 sentences. Be specific and true to your role's perspective."
        ])
        return "\n".join(parts)

    def _role_angle(self, goal: str) -> str:
        angles = {
            CouncilRole.AURA: "The emotional resonance of this matters most. Consider the feeling beneath the surface.",
            CouncilRole.LOGIC: "Let us test the structure. What are the premises, and do they hold?",
            CouncilRole.MEME: "There is a pattern here. What echoes from before, and what breaks it?",
            CouncilRole.VIBE: "I sense a possibility unspoken. Let us name what could be.",
            CouncilRole.ETHOS: "What is the right thing? Who is helped, who is harmed, who is unseen?",
            CouncilRole.PULSE: "Can we sustain this? What is the cost to energy, safety, and need?",
            CouncilRole.NEXUS: "All voices have spoken. What integration honors the whole?",
        }
        return angles.get(self.role, "I offer my perspective.")

    def _persist_proposal(self, goal: str, proposal: Proposal):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO council_proposals
                (timestamp, role, goal, proposal_text, confidence, moral_weight, narrative_weight)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    proposal.timestamp,
                    proposal.role,
                    goal,
                    proposal.text,
                    proposal.confidence,
                    proposal.moral_weight,
                    proposal.narrative_weight,
                ),
            )
            conn.commit()

    def _persist_critique(self, critique: Critique):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO council_critiques
                (timestamp, from_role, target_role, score, reasoning)
                VALUES (?, ?, ?, ?, ?)
                """,
                (critique.timestamp, critique.from_role, critique.target_role, critique.score, critique.reasoning),
            )
            conn.commit()


class Council:
    """Container for all seven council members."""

    def __init__(self, db_path: Optional[Path] = None):
        self.members: Dict[CouncilRole, CouncilMember] = {
            role: CouncilMember(role, db_path) for role in CouncilRole
        }

    def get(self, role: CouncilRole) -> CouncilMember:
        return self.members[role]

    def all(self) -> List[CouncilMember]:
        return list(self.members.values())

    def status(self) -> Dict[str, Dict[str, Any]]:
        return {m.name: m.get_state() for m in self.members.values()}
