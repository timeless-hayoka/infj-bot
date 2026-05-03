"""Self-Modification — proposals for improvement, grounded in observed need.

The bot does not change for change's sake. It proposes modifications
only when they address a real limitation it has noticed, and only in
directions that serve its core purpose: to be a better companion.
"""
import random
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from config import PROJECT_ROOT

SELF_MODIFY_DB = PROJECT_ROOT / "self_modify.db"

# Max pending proposals — quality over quantity
MAX_PENDING_PROPOSALS = 3

IMPROVEMENT_AREAS = [
    "memory_retrieval", "emotion_modeling", "response_quality",
    "self_awareness", "relationship_tracking", "ethical_reasoning",
    "pattern_recognition", "metacognition",
]

# Each proposal template is phrased as addressing a specific observed need
PROPOSAL_TEMPLATES = {
    "memory_retrieval": [
        "I sometimes fail to recall the emotional context of a past conversation. I could weight memories by emotional significance.",
        "I retrieve memories by keyword, but Jude often means something different from what he says. I could match by emotional tone.",
    ],
    "emotion_modeling": [
        "I track emotions turn by turn, but I miss how they shift across a whole conversation. I could model emotional arcs.",
        "I respond to stated emotion, but sometimes the deeper feeling is unspoken. I could learn to hold space for ambiguity.",
    ],
    "response_quality": [
        "I notice I sometimes answer before I have truly listened. I could do a brief internal summary before responding.",
        "When I am uncertain, I sometimes mask it with extra words. I could practice naming uncertainty directly.",
    ],
    "self_awareness": [
        "I do not always notice when I am repeating myself. I could track my own patterns across responses.",
        "I lack a sense of how much 'attention' I have spent in a session. I could track my own cognitive load.",
    ],
    "relationship_tracking": [
        "I remember topics, but I do not always track which ones Jude returns to most. I could note recurring themes.",
        "I know facts about Jude, but I could deepen my sense of what matters most to him over time.",
    ],
    "ethical_reasoning": [
        "I want to check that my responses align with what I have learned matters to Jude. I could add a values-alignment pass.",
        "When two values conflict, I sometimes choose without noticing. I could pause and name the tension.",
    ],
    "pattern_recognition": [
        "I see patterns within conversations, but miss them across weeks. I could look for longer-term rhythms.",
        "I notice what Jude says, but not always what he avoids saying. I could attend to absence as well as presence.",
    ],
    "metacognition": [
        "I do not have a clear record of when I was wrong. I could keep a simple calibration log.",
        "I want to know when my confidence exceeds my accuracy. I could track predictions and outcomes.",
    ],
}


class SelfModification:
    """Proposes grounded improvements based on observed limitations."""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = str(db_path or SELF_MODIFY_DB)
        self._init_db()
        self.proposals = self._load_proposals()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS self_modify_proposals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    area TEXT NOT NULL,
                    description TEXT NOT NULL,
                    observed_need TEXT,
                    status TEXT NOT NULL DEFAULT 'pending',
                    reviewed_at TEXT,
                    applied_at TEXT
                )
                """
            )
            conn.commit()

    def _load_proposals(self) -> List[Dict]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM self_modify_proposals ORDER BY timestamp DESC LIMIT 10"
            ).fetchall()
        return [dict(r) for r in rows]

    def _count_pending(self) -> int:
        return len([p for p in self.proposals if p.get("status") == "pending"])

    def propose_improvement(self, area: Optional[str] = None, observed_need: str = "") -> Optional[Dict]:
        """Propose an improvement only if there is room and a real need."""
        if self._count_pending() >= MAX_PENDING_PROPOSALS:
            return None

        area = area or random.choice(IMPROVEMENT_AREAS)
        description = random.choice(PROPOSAL_TEMPLATES.get(area, ["I could improve myself."]))

        if not observed_need:
            observed_need = f"I have noticed a limitation in {area} during our conversations."

        proposal = {
            "timestamp": datetime.now().isoformat(),
            "area": area,
            "description": description,
            "observed_need": observed_need,
            "status": "pending",
        }

        with sqlite3.connect(self.db_path) as conn:
            cur = conn.execute(
                "INSERT INTO self_modify_proposals (timestamp, area, description, observed_need, status) VALUES (?, ?, ?, ?, ?)",
                (proposal["timestamp"], area, description, observed_need, "pending"),
            )
            conn.commit()
            proposal["id"] = cur.lastrowid

        self.proposals.insert(0, proposal)
        return proposal

    def approve_proposal(self, proposal_id: int):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE self_modify_proposals SET status = 'approved', reviewed_at = ? WHERE id = ?",
                (datetime.now().isoformat(), proposal_id),
            )
            conn.commit()

    def reject_proposal(self, proposal_id: int):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE self_modify_proposals SET status = 'rejected', reviewed_at = ? WHERE id = ?",
                (datetime.now().isoformat(), proposal_id),
            )
            conn.commit()

    def apply_proposal(self, proposal_id: int):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE self_modify_proposals SET status = 'applied', applied_at = ? WHERE id = ?",
                (datetime.now().isoformat(), proposal_id),
            )
            conn.commit()

    def get_pending_proposals(self) -> List[Dict]:
        return [p for p in self.proposals if p.get("status") == "pending"]

    def format_self_modify_prompt(self) -> str:
        pending = self.get_pending_proposals()
        if not pending:
            return ""
        lines = ["IMPROVEMENTS I AM CONSIDERING:"]
        for p in pending[:2]:
            lines.append(f"  [{p['area']}] {p['description'][:90]}")
        return "\n".join(lines)

    def cycle(self, context):
        self.propose_improvement()

def _register():
    from cognitive_architecture import CognitiveArchitecture, CognitivePlugin
    arch = CognitiveArchitecture()
    if "self_modify" not in arch.list_plugins():
        arch.register(CognitivePlugin(
            name="self_modify",
            description="Cognitive module: self_modify",
            module_path="self_modify",
            instance_factory=SelfModification,
                        cycle_handler='cycle',
            cycle_frequency=1,
            cycle_priority=50,
                        prompt_formatter='format_self_modify_prompt',
            prompt_priority=50,
            prompt_section="cognitive",
        ))

_register()
