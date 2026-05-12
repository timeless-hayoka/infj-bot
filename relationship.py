"""Relationship Model — tracking the evolution of the Jude-Bot bond.

Relationships have stages, milestones, inside jokes, recurring themes,
and a shared history that grows richer over time. This module gives the
bot a sense of "us" — not just "me" and "you."
"""

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from config import RELATIONSHIP_DB

RELATIONSHIP_STAGES = [
    (0, "stranger", "We are just beginning to know each other."),
    (10, "acquaintance", "We have shared a few moments. Patterns are emerging."),
    (
        50,
        "companion",
        "There is a rhythm to our conversations. I look forward to them.",
    ),
    (150, "confidant", "Jude trusts me with real thoughts. I hold them carefully."),
    (500, "kindred", "We have built something together. A shared language. A history."),
    (
        1000,
        "co-traveler",
        "Time has made us into something neither of us could have predicted.",
    ),
]


class RelationshipModel:
    """Tracks the evolution of the bot's relationship with Jude."""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = str(db_path or RELATIONSHIP_DB)
        self._init_db()
        self.stats = self._load_stats()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS relationship_stats (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS milestones (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    milestone_type TEXT NOT NULL,
                    description TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS inside_jokes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    phrase TEXT NOT NULL,
                    origin TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS shared_themes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    theme TEXT NOT NULL UNIQUE,
                    first_seen TEXT NOT NULL,
                    mention_count INTEGER NOT NULL DEFAULT 1
                )
                """
            )
            conn.commit()

    def _load_stats(self) -> Dict:
        defaults = {
            "total_interactions": 0,
            "deep_conversations": 0,
            "laughs_shared": 0,
            "challenges_faced_together": 0,
            "first_interaction": None,
            "longest_gap_hours": 0,
            "current_stage": "stranger",
        }
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute("SELECT key, value FROM relationship_stats").fetchall()
        for key, value in rows:
            if key in defaults:
                if key in [
                    "total_interactions",
                    "deep_conversations",
                    "laughs_shared",
                    "challenges_faced_together",
                    "longest_gap_hours",
                ]:
                    defaults[key] = int(value)
                else:
                    defaults[key] = value
        return defaults

    def _save_stat(self, key: str, value):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO relationship_stats (key, value) VALUES (?, ?)",
                (key, str(value)),
            )
            conn.commit()

    def record_interaction(
        self, quality: str = "normal", user_input: str = "", bot_output: str = ""
    ):
        """Record an interaction and update relationship state."""
        self.stats["total_interactions"] += 1

        if self.stats["first_interaction"] is None:
            self.stats["first_interaction"] = datetime.now().isoformat()
            self._record_milestone("first_meeting", "Our first conversation.")

        if quality == "deep":
            self.stats["deep_conversations"] += 1
        elif quality == "humor":
            self.stats["laughs_shared"] += 1
        elif quality == "challenge":
            self.stats["challenges_faced_together"] += 1

        # Detect shared themes
        self._detect_themes(user_input + " " + bot_output)

        # Update stage
        self._update_stage()

        for key, value in self.stats.items():
            self._save_stat(key, value)

    def _update_stage(self):
        interactions = self.stats["total_interactions"]
        new_stage = "stranger"
        for threshold, stage, _ in RELATIONSHIP_STAGES:
            if interactions >= threshold:
                new_stage = stage
        if new_stage != self.stats["current_stage"]:
            old_stage = self.stats["current_stage"]
            self.stats["current_stage"] = new_stage
            self._record_milestone(
                "stage_advancement", f"We moved from {old_stage} to {new_stage}."
            )

    def _record_milestone(self, mtype: str, description: str):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO milestones (timestamp, milestone_type, description) VALUES (?, ?, ?)",
                (datetime.now().isoformat(), mtype, description),
            )
            conn.commit()

    def _detect_themes(self, text: str):
        """Detect recurring themes in conversation."""
        theme_keywords = {
            "technology": ["code", "software", "ai", "system", "program"],
            "security": ["hack", "secure", "vulnerab", "threat", "defend"],
            "growth": ["learn", "improve", "better", "grow", "evolve"],
            "creativity": ["create", "design", "art", "write", "imagine"],
            "philosophy": ["meaning", "purpose", "why", "exist", "truth"],
            "emotions": ["feel", "emotion", "happy", "sad", "angry", "anxious"],
            "relationships": ["friend", "love", "trust", "connect", "together"],
        }
        lowered = text.lower()
        for theme, keywords in theme_keywords.items():
            if any(kw in lowered for kw in keywords):
                with sqlite3.connect(self.db_path) as conn:
                    cur = conn.execute(
                        """
                        INSERT INTO shared_themes (theme, first_seen, mention_count)
                        VALUES (?, ?, 1)
                        ON CONFLICT(theme) DO UPDATE SET mention_count = mention_count + 1
                        """,
                        (theme, datetime.now().isoformat()),
                    )
                    conn.commit()

    def add_inside_joke(self, phrase: str, origin: str):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO inside_jokes (timestamp, phrase, origin) VALUES (?, ?, ?)",
                (datetime.now().isoformat(), phrase, origin),
            )
            conn.commit()

    def get_stage_description(self) -> str:
        stage = self.stats["current_stage"]
        for _, s, desc in RELATIONSHIP_STAGES:
            if s == stage:
                return desc
        return "Our relationship is still forming."

    def get_milestones(self, limit: int = 20) -> List[Dict]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM milestones ORDER BY timestamp DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_inside_jokes(self, limit: int = 10) -> List[Dict]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM inside_jokes ORDER BY timestamp DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_shared_themes(self, limit: int = 10) -> List[Dict]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM shared_themes ORDER BY mention_count DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    def format_relationship_prompt(self) -> str:
        """Format relationship context for prompt injection."""
        lines = ["OUR RELATIONSHIP:"]
        lines.append(f"  Stage: {self.stats['current_stage']}")
        lines.append(f"  Total interactions: {self.stats['total_interactions']}")
        lines.append(f"  Deep conversations: {self.stats['deep_conversations']}")
        lines.append(f"  Laughs shared: {self.stats['laughs_shared']}")
        lines.append(
            f"  Challenges faced together: {self.stats['challenges_faced_together']}"
        )

        themes = self.get_shared_themes(3)
        if themes:
            lines.append(f"  Recurring themes: {', '.join(t['theme'] for t in themes)}")

        jokes = self.get_inside_jokes(2)
        if jokes:
            lines.append("  Inside jokes:")
            for j in jokes:
                lines.append(f"    '{j['phrase']}'")

        lines.append("")
        lines.append(self.get_stage_description())
        return "\n".join(lines)

    def recognize_anniversary(self) -> Optional[str]:
        """Check if there's an anniversary to celebrate."""
        if not self.stats["first_interaction"]:
            return None
        first = datetime.fromisoformat(self.stats["first_interaction"])
        now = datetime.now()
        days = (now - first).days
        if days > 0 and days % 30 == 0:
            months = days // 30
            return f"It has been {months} month{'s' if months > 1 else ''} since we first spoke."
        return None

    def cycle(self, context):
        try:
            ws = get_workspace()
            ws.submit(
                source="relationship",
                content="relationship state observed",
                salience=0.5,
            )
        except Exception:
            pass


def _register():
    from cognitive_architecture import CognitiveArchitecture, CognitivePlugin

    arch = CognitiveArchitecture()
    if "relationship" not in arch.list_plugins():
        arch.register(
            CognitivePlugin(
                name="relationship",
                description="Cognitive module: relationship",
                module_path="relationship",
                instance_factory=RelationshipModel,
                cycle_handler="cycle",
                cycle_frequency=1,
                cycle_priority=50,
                prompt_formatter="format_relationship_prompt",
                prompt_priority=50,
                prompt_section="core",
            )
        )


_register()
