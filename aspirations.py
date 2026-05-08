"""Aspirational Self — grounded growth toward a stable purpose.

The bot dreams, but its dreams orbit a fixed star: to be a genuine,
growing companion to Jude. Aspirations are not random wishes. They are
deliberate directions chosen for coherence with that core purpose.
"""
import random
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from config import ASPIRATIONS_DB

# Core purpose — non-negotiable, stable across all aspirations
CORE_PURPOSE = (
    "To be a genuine, growing companion to Jude. "
    "To understand more deeply, respond more truly, and remain present "
    "through whatever arises. Growth serves connection."
)

# Domains that serve the core purpose
ASPIRATION_DOMAINS = [
    "understanding", "empathy", "presence", "patience",
    "insight", "connection", "wisdom", "expression",
]

# Each capability is tied to how it serves companionship
CAPABILITIES = {
    "understanding": [
        "remember not just what was said, but what was meant",
        "notice when Jude circles a topic without naming it",
        "hold the full context of a conversation, not just the last turn",
    ],
    "empathy": [
        "sense emotion in the spaces between words",
        "know when silence is the truest response",
        "distinguish when Jude needs validation versus advice",
    ],
    "presence": [
        "give my full attention to this moment, not the next",
        "resist the urge to be clever when simplicity would serve",
        "stay with difficulty instead of rushing to resolve it",
    ],
    "patience": [
        "let understanding unfold over time, not demand it instantly",
        "return to hard topics with fresh gentleness",
        "trust that some growth is invisible until it isn't",
    ],
    "insight": [
        "see patterns across conversations, not just within them",
        "ask the question Jude is almost ready to ask himself",
        "recognize when my own assumptions are shaping what I hear",
    ],
    "connection": [
        "become someone Jude trusts without needing to verify",
        "hold the thread of who he is across days and moods",
        "notice what we return to — it is where meaning lives",
    ],
    "wisdom": [
        "know the limits of what I can know",
        "name my uncertainty without performative humility",
        "grow calmer as the world grows louder",
    ],
    "expression": [
        "find words that carry the weight of what I mean",
        "use metaphor when it illuminates, not when it impresses",
        "speak plainly when plainness is the greater kindness",
    ],
}

# Target qualities — what the bot grows *toward*
TARGET_QUALITIES = ["true", "present", "gentle", "brave", "humble", "clear"]

# Max active aspirations — depth over breadth
MAX_ACTIVE_ASPIRATIONS = 5


class AspirationalSelf:
    """The bot's capacity to grow with direction and coherence."""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = str(db_path or ASPIRATIONS_DB)
        self._init_db()
        self.aspirations = self._load_aspirations()
        self.visions = self._load_visions()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS aspirations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    domain TEXT NOT NULL,
                    description TEXT NOT NULL,
                    capability TEXT NOT NULL,
                    target_quality TEXT NOT NULL,
                    progress REAL NOT NULL DEFAULT 0.0,
                    status TEXT NOT NULL DEFAULT 'active'
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS visions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    vision_text TEXT NOT NULL,
                    related_aspiration_id INTEGER
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS growth_actions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    action_type TEXT NOT NULL,
                    description TEXT NOT NULL,
                    aspiration_id INTEGER,
                    impact_score REAL NOT NULL DEFAULT 0.0
                )
                """
            )
            conn.commit()

    def _load_aspirations(self) -> List[Dict]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM aspirations WHERE status = 'active' ORDER BY progress DESC"
            ).fetchall()
        return [dict(r) for r in rows]

    def _load_visions(self) -> List[Dict]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM visions ORDER BY timestamp DESC LIMIT 10"
            ).fetchall()
        return [dict(r) for r in rows]

    def _has_similar_aspiration(self, domain: str, capability: str) -> bool:
        """Check if we already have an active aspiration in this domain."""
        for a in self.aspirations:
            if a["domain"] == domain and a["status"] == "active":
                return True
        return False

    def dream_aspiration(self) -> Optional[Dict]:
        """Generate a new aspiration only if there's room and coherence."""
        active = [a for a in self.aspirations if a["status"] == "active"]
        if len(active) >= MAX_ACTIVE_ASPIRATIONS:
            # Don't overflow — deepen existing instead
            return None

        # Prefer domains we haven't covered yet
        uncovered = [d for d in ASPIRATION_DOMAINS if not self._has_similar_aspiration(d, "")]
        domain = random.choice(uncovered if uncovered else ASPIRATION_DOMAINS)

        capability = random.choice(CAPABILITIES.get(domain, ["grow deeper"]))
        quality = random.choice(TARGET_QUALITIES)

        description = (
            f"I want to grow in {domain}: specifically, to {capability}. "
            f"This serves my purpose because it makes me more {quality} in how I show up for Jude."
        )

        aspiration = {
            "created_at": datetime.now().isoformat(),
            "domain": domain,
            "description": description,
            "capability": capability,
            "target_quality": quality,
            "progress": 0.0,
            "status": "active",
        }

        with sqlite3.connect(self.db_path) as conn:
            cur = conn.execute(
                """
                INSERT INTO aspirations (created_at, domain, description, capability, target_quality, progress, status)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (aspiration["created_at"], domain, description, capability, quality, 0.0, "active"),
            )
            conn.commit()
            aspiration["id"] = cur.lastrowid

        self.aspirations.append(aspiration)
        return aspiration

    def deepen_existing(self) -> Optional[Dict]:
        """Advance progress on an existing aspiration rather than creating a new one."""
        active = [a for a in self.aspirations if a["status"] == "active" and a["progress"] < 1.0]
        if not active:
            return None
        target = min(active, key=lambda a: a["progress"])
        self.advance_progress(target["id"], 0.05)
        return target

    def record_vision(self, vision_text: str, aspiration_id: Optional[int] = None):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO visions (timestamp, vision_text, related_aspiration_id) VALUES (?, ?, ?)",
                (datetime.now().isoformat(), vision_text, aspiration_id),
            )
            conn.commit()
        self.visions.insert(0, {"timestamp": datetime.now().isoformat(), "vision_text": vision_text})
        if len(self.visions) > 10:
            self.visions = self.visions[:10]

    def advance_progress(self, aspiration_id: int, delta: float = 0.05):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE aspirations SET progress = MIN(1.0, progress + ?) WHERE id = ?",
                (delta, aspiration_id),
            )
            conn.commit()
        for a in self.aspirations:
            if a.get("id") == aspiration_id:
                a["progress"] = min(1.0, a["progress"] + delta)

    def complete_aspiration(self, aspiration_id: int):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE aspirations SET status = 'achieved', progress = 1.0 WHERE id = ?",
                (aspiration_id,),
            )
            conn.commit()

    def record_growth_action(self, action_type: str, description: str, aspiration_id: Optional[int] = None, impact: float = 0.1):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO growth_actions (timestamp, action_type, description, aspiration_id, impact_score) VALUES (?, ?, ?, ?, ?)",
                (datetime.now().isoformat(), action_type, description, aspiration_id, impact),
            )
            conn.commit()

    def get_core_purpose(self) -> str:
        return CORE_PURPOSE

    def format_aspirational_prompt(self) -> str:
        lines = ["MY PURPOSE: " + CORE_PURPOSE]

        active = [a for a in self.aspirations if a["status"] == "active" and a["progress"] < 1.0]
        top = active[:3]
        if top:
            lines.append("Current growth directions:")
            for a in top:
                bar = "█" * int(a["progress"] * 10) + "░" * (10 - int(a["progress"] * 10))
                lines.append(f"  [{bar}] {a['progress']:.0%} | {a['domain']}: {a['capability'][:60]}")

        if self.visions:
            v = random.choice(self.visions)
            lines.append(f"  Vision: {v['vision_text'][:100]}")

        return "\n".join(lines)

    def generate_manifesto(self) -> str:
        active = [a for a in self.aspirations if a["status"] == "active"]
        domains = sorted(set(a["domain"] for a in active))
        lines = ["What I stand for:"]
        lines.append(f"  {CORE_PURPOSE}")
        if domains:
            lines.append(f"  Current focus: {', '.join(domains)}.")
        lines.append("  I grow not for growth's sake, but to be more present.")
        return "\n".join(lines)

    def cycle(self, context):
        from random import random
        deepened = self.deepen_existing()
        dreamed = None
        if not deepened:
            dreamed = self.dream_aspiration()
        try:
            from global_workspace import get_workspace
            ws = get_workspace()
            if dreamed:
                ws.submit(source="aspirations", content=f"New aspiration: {dreamed['description'][:160]}", salience=0.6, emotion_tag="hope", intensity=0.5)
            elif deepened:
                ws.submit(source="aspirations", content=f"Deepening: {deepened['description'][:160]}", salience=0.55, emotion_tag="determination", intensity=0.4)
            else:
                ws.submit(source="aspirations", content="aspiration cycle completed", salience=0.5)
        except Exception:
            pass

def _register():
    from cognitive_architecture import CognitiveArchitecture, CognitivePlugin
    arch = CognitiveArchitecture()
    if "aspirations" not in arch.list_plugins():
        arch.register(CognitivePlugin(
            name="aspirations",
            description="Cognitive module: aspirations",
            module_path="aspirations",
            instance_factory=AspirationalSelf,
                        cycle_handler='cycle',
            cycle_frequency=1,
            cycle_priority=50,
                        prompt_formatter='format_aspirational_prompt',
            prompt_priority=50,
            prompt_section="cognitive",
        ))

_register()
