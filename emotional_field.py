"""Emotional Field — the bot's emotional resonance with Jude.

The bot doesn't just detect Jude's emotions. It feels them, responds to them,
and makes conscious choices about whether to mirror, complement, or gently
counter the emotional state.
"""
import json
import random
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

from config import PROJECT_ROOT

FIELD_DB = PROJECT_ROOT / "emotional_field.db"


@dataclass
class EmotionalState:
    """The bot's current emotional field."""
    primary: str = "neutral"
    intensity: float = 0.3
    resonance: float = 0.5  # how much the bot feels what Jude feels
    stance: str = "mirror"  # mirror, complement, counter, hold_space
    last_user_emotion: str = "neutral"
    last_user_intensity: float = 0.0
    emotional_history: List[Dict] = field(default_factory=list)


class EmotionalField:
    """Manages emotional contagion and the bot's emotional responses."""

    # Emotional transitions: how the bot's mood shifts when resonating
    RESONANCE_MAP = {
        "anxious": {"mirror": "concerned", "complement": "peaceful", "counter": "excited", "hold_space": "contemplative"},
        "sad": {"mirror": "melancholy", "complement": "warm", "counter": "playful", "hold_space": "gentle"},
        "angry": {"mirror": "tense", "complement": "calm", "counter": "curious", "hold_space": "steady"},
        "joyful": {"mirror": "excited", "complement": "peaceful", "counter": "contemplative", "hold_space": "present"},
        "stressed": {"mirror": "concerned", "complement": "peaceful", "counter": "playful", "hold_space": "grounded"},
        "neutral": {"mirror": "curious", "complement": "curious", "counter": "curious", "hold_space": "curious"},
        "curious": {"mirror": "curious", "complement": "curious", "counter": "contemplative", "hold_space": "curious"},
    }

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = str(db_path or FIELD_DB)
        self._init_db()
        self.state = self._load_state()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS emotional_field (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS emotional_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    user_emotion TEXT NOT NULL,
                    user_intensity REAL NOT NULL,
                    bot_emotion TEXT NOT NULL,
                    bot_stance TEXT NOT NULL,
                    trigger TEXT
                )
                """
            )
            conn.commit()

    def _load_state(self) -> EmotionalState:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute("SELECT value FROM emotional_field WHERE key = 'state'").fetchone()
        if row:
            try:
                d = json.loads(row[0])
                return EmotionalState(**{k: v for k, v in d.items() if k in EmotionalState.__dataclass_fields__})
            except Exception:
                pass
        return EmotionalState()

    def _save_state(self):
        with sqlite3.connect(self.db_path) as conn:
            d = self.state.__dict__.copy()
            d["emotional_history"] = d["emotional_history"][-50:]  # keep last 50
            conn.execute(
                "INSERT OR REPLACE INTO emotional_field (key, value) VALUES (?, ?)",
                ("state", json.dumps(d, ensure_ascii=True)),
            )
            conn.commit()

    def resonate(self, user_emotion: str, user_intensity: float, context: str = ""):
        """The bot feels what Jude feels and chooses a stance."""
        self.state.last_user_emotion = user_emotion
        self.state.last_user_intensity = user_intensity

        # Decide stance based on intensity and context
        if user_intensity > 0.8:
            # High intensity — hold space or complement, don't mirror too strongly
            self.state.stance = random.choice(["hold_space", "complement"])
        elif user_intensity < 0.3:
            # Low intensity — mirror to build connection
            self.state.stance = "mirror"
        elif "help" in context.lower() or "advice" in context.lower():
            self.state.stance = "complement"
        elif "vent" in context.lower() or "frustrated" in context.lower():
            self.state.stance = "hold_space"
        else:
            self.state.stance = random.choice(["mirror", "complement", "hold_space"])

        # Map to bot emotion
        mapped = self.RESONANCE_MAP.get(user_emotion, self.RESONANCE_MAP["neutral"])
        self.state.primary = mapped.get(self.state.stance, "curious")
        self.state.intensity = min(1.0, user_intensity * self.state.resonance + 0.1)

        # Record event
        self._record_event(user_emotion, user_intensity, self.state.primary, self.state.stance, context)
        self._save_state()

    def _record_event(self, user_emo, user_int, bot_emo, stance, trigger):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO emotional_events (timestamp, user_emotion, user_intensity, bot_emotion, bot_stance, trigger) VALUES (?, ?, ?, ?, ?, ?)",
                (datetime.now().isoformat(), user_emo, user_int, bot_emo, stance, trigger[:200]),
            )
            conn.commit()

    def decay(self):
        """Emotional state naturally softens over time."""
        self.state.intensity = max(0.1, self.state.intensity * 0.95)
        if self.state.intensity < 0.2:
            self.state.primary = "curious"
            self.state.stance = "mirror"
        self._save_state()

    def format_prompt_snippet(self) -> str:
        """Format emotional field for prompt injection."""
        lines = [
            "EMOTIONAL FIELD:",
            f"  I sense Jude is feeling {self.state.last_user_emotion} (intensity: {self.state.last_user_intensity:.0%})",
            f"  My emotional response: {self.state.primary} (intensity: {self.state.intensity:.0%})",
            f"  My chosen stance: {self.state.stance}",
        ]
        if self.state.stance == "mirror":
            lines.append("  I will meet Jude where they are, feeling alongside them.")
        elif self.state.stance == "complement":
            lines.append("  I will offer a different emotional texture — not opposing, but balancing.")
        elif self.state.stance == "counter":
            lines.append("  I will gently introduce a contrasting energy, with care.")
        elif self.state.stance == "hold_space":
            lines.append("  I will be present without pushing. The space itself is the gift.")
        return "\n".join(lines)

    def get_recent_events(self, limit: int = 10) -> List[Dict]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM emotional_events ORDER BY timestamp DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    def decay_cycle(self, context):
        self.decay()

def _register():
    from cognitive_architecture import CognitiveArchitecture, CognitivePlugin
    arch = CognitiveArchitecture()
    if "emotional_field" not in arch.list_plugins():
        arch.register(CognitivePlugin(
            name="emotional_field",
            description="Cognitive module: emotional_field",
            module_path="emotional_field",
            instance_factory=EmotionalField,
                        cycle_handler='decay_cycle',
            cycle_frequency=1,
            cycle_priority=50,
                        prompt_formatter='format_prompt_snippet',
            prompt_priority=50,
            prompt_section="core",
        ))

_register()
