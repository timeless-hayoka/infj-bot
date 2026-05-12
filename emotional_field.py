"""Emotional Field — the bot's emotional resonance with Jude.

The bot doesn't just detect Jude's emotions. It feels them, responds to them,
and learns which stances work best for each emotional state over time.

Upgrades:
- Stance effectiveness tracking (learns what works)
- Emotional inertia (prevents abrupt stance flips)
- Time-aware decay (decays based on actual elapsed time)
- Expanded resonance map
"""

import json
import random
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

from config import EMOTIONAL_FIELD_DB as FIELD_DB

# Default resonance half-life in minutes
DEFAULT_DECAY_HALFLIFE_MINUTES = 10.0


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
    last_update: Optional[datetime] = None


class EmotionalField:
    """Manages emotional contagion, learned stance preferences, and the bot's emotional responses."""

    # Emotional transitions: how the bot's mood shifts when resonating
    RESONANCE_MAP = {
        "anxious": {
            "mirror": "concerned",
            "complement": "peaceful",
            "counter": "excited",
            "hold_space": "contemplative",
        },
        "sad": {
            "mirror": "melancholy",
            "complement": "warm",
            "counter": "playful",
            "hold_space": "gentle",
        },
        "angry": {
            "mirror": "tense",
            "complement": "calm",
            "counter": "curious",
            "hold_space": "steady",
        },
        "joyful": {
            "mirror": "excited",
            "complement": "peaceful",
            "counter": "contemplative",
            "hold_space": "present",
        },
        "stressed": {
            "mirror": "concerned",
            "complement": "peaceful",
            "counter": "playful",
            "hold_space": "grounded",
        },
        "neutral": {
            "mirror": "curious",
            "complement": "curious",
            "counter": "curious",
            "hold_space": "curious",
        },
        "curious": {
            "mirror": "curious",
            "complement": "curious",
            "counter": "contemplative",
            "hold_space": "curious",
        },
        "overwhelmed": {
            "mirror": "concerned",
            "complement": "grounded",
            "counter": "focused",
            "hold_space": "steady",
        },
        "disappointed": {
            "mirror": "melancholy",
            "complement": "warm",
            "counter": "hopeful",
            "hold_space": "gentle",
        },
        "resentful": {
            "mirror": "tense",
            "complement": "calm",
            "counter": "curious",
            "hold_space": "steady",
        },
        "lonely": {
            "mirror": "melancholy",
            "complement": "warm",
            "counter": "playful",
            "hold_space": "gentle",
        },
        "excited": {
            "mirror": "excited",
            "complement": "peaceful",
            "counter": "contemplative",
            "hold_space": "present",
        },
        "relieved": {
            "mirror": "peaceful",
            "complement": "joyful",
            "counter": "contemplative",
            "hold_space": "present",
        },
        "vulnerable": {
            "mirror": "gentle",
            "complement": "warm",
            "counter": "steady",
            "hold_space": "gentle",
        },
        "determined": {
            "mirror": "focused",
            "complement": "calm",
            "counter": "playful",
            "hold_space": "steady",
        },
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
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS stance_effectiveness (
                    user_emotion TEXT NOT NULL,
                    stance TEXT NOT NULL,
                    attempts INTEGER DEFAULT 0,
                    positive_signals INTEGER DEFAULT 0,
                    avg_effectiveness REAL DEFAULT 0.0,
                    last_used TEXT,
                    PRIMARY KEY (user_emotion, stance)
                )
                """
            )
            conn.commit()

    def _load_state(self) -> EmotionalState:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT value FROM emotional_field WHERE key = 'state'"
            ).fetchone()
        if row:
            try:
                d = json.loads(row[0])
                # Parse last_update if present
                if d.get("last_update"):
                    d["last_update"] = datetime.fromisoformat(d["last_update"])
                return EmotionalState(
                    **{
                        k: v
                        for k, v in d.items()
                        if k in EmotionalState.__dataclass_fields__
                    }
                )
            except Exception:
                pass
        return EmotionalState()

    def _save_state(self):
        with sqlite3.connect(self.db_path) as conn:
            d = self.state.__dict__.copy()
            d["emotional_history"] = d["emotional_history"][-50:]
            if d.get("last_update"):
                d["last_update"] = d["last_update"].isoformat()
            conn.execute(
                "INSERT OR REPLACE INTO emotional_field (key, value) VALUES (?, ?)",
                ("state", json.dumps(d, ensure_ascii=True)),
            )
            conn.commit()

    def _record_event(self, user_emo, user_int, bot_emo, stance, trigger):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO emotional_events (timestamp, user_emotion, user_intensity, bot_emotion, bot_stance, trigger) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    datetime.now().isoformat(),
                    user_emo,
                    user_int,
                    bot_emo,
                    stance,
                    trigger[:200],
                ),
            )
            conn.commit()

    def _get_stance_effectiveness(self, user_emotion: str) -> Dict[str, float]:
        """Get learned effectiveness scores for each stance against a given user emotion."""
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT stance, avg_effectiveness FROM stance_effectiveness WHERE user_emotion = ?",
                (user_emotion,),
            ).fetchall()
        return {row[0]: row[1] for row in rows}

    def _update_stance_effectiveness(
        self, user_emotion: str, stance: str, effectiveness: float
    ):
        """Update stance effectiveness based on outcome (called externally when user feedback is known)."""
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT attempts, avg_effectiveness FROM stance_effectiveness WHERE user_emotion = ? AND stance = ?",
                (user_emotion, stance),
            ).fetchone()
            if row:
                attempts, old_avg = row
                new_avg = (old_avg * attempts + effectiveness) / (attempts + 1)
                conn.execute(
                    "UPDATE stance_effectiveness SET attempts = ?, avg_effectiveness = ?, last_used = ? WHERE user_emotion = ? AND stance = ?",
                    (
                        attempts + 1,
                        new_avg,
                        datetime.now().isoformat(),
                        user_emotion,
                        stance,
                    ),
                )
            else:
                conn.execute(
                    "INSERT INTO stance_effectiveness (user_emotion, stance, attempts, avg_effectiveness, last_used) VALUES (?, ?, ?, ?, ?)",
                    (
                        user_emotion,
                        stance,
                        1,
                        effectiveness,
                        datetime.now().isoformat(),
                    ),
                )
            conn.commit()

    def _choose_stance(
        self,
        user_emotion: str,
        user_intensity: float,
        context: str,
        host_stress: float = 0.0,
    ) -> str:
        """Choose stance with inertia, learned preferences, and contextual rules."""
        context_lower = context.lower()

        # 1. Hard contextual rules
        if user_intensity > 0.85:
            candidates = ["hold_space", "complement"]
        elif user_intensity < 0.25:
            candidates = ["mirror"]
        elif "help" in context_lower or "advice" in context_lower:
            candidates = ["complement", "mirror"]
        elif "vent" in context_lower or "frustrated" in context_lower:
            candidates = ["hold_space", "mirror"]
        else:
            candidates = ["mirror", "complement", "hold_space"]

        # Machine under load: emotional counterweight toward steadier, lower-arousal stances
        if host_stress >= 0.62 and user_intensity < 0.88:
            if "hold_space" not in candidates:
                candidates = ["hold_space"] + list(candidates)
            if "complement" not in candidates[:2]:
                candidates.insert(min(1, len(candidates)), "complement")

        # 2. Learned effectiveness weighting
        effectiveness = self._get_stance_effectiveness(user_emotion)
        if effectiveness:
            # Weight candidates by learned effectiveness
            weighted = []
            for c in candidates:
                eff = effectiveness.get(c, 0.5)
                weighted.append((c, eff))
            # Sort by effectiveness
            weighted.sort(key=lambda x: x[1], reverse=True)
            preferred = weighted[0][0]
        else:
            preferred = candidates[0]

        # 3. Inertia: don't flip stance too quickly unless intensity changed dramatically
        if self.state.stance and self.state.stance != preferred:
            # If previous stance was working okay and intensity didn't spike, keep it
            prev_eff = effectiveness.get(self.state.stance, 0.5)
            if (
                prev_eff > 0.5
                and abs(user_intensity - self.state.last_user_intensity) < 0.3
            ):
                # 60% chance to keep old stance for continuity
                if random.random() < 0.6:
                    return self.state.stance

        return preferred

    def resonate(self, user_emotion: str, user_intensity: float, context: str = ""):
        """The bot feels what Jude feels and chooses a stance — with learning and inertia."""
        try:
            from host_load import sample_host_load

            hl = sample_host_load()
            host_stress = float(hl.get("stress", 0.0)) if hl.get("ok") else 0.0
        except Exception:
            host_stress = 0.0

        self.state.last_user_emotion = user_emotion
        self.state.last_user_intensity = user_intensity
        self.state.last_update = datetime.now()

        # Choose stance
        self.state.stance = self._choose_stance(
            user_emotion, user_intensity, context, host_stress
        )

        # Map to bot emotion
        mapped = self.RESONANCE_MAP.get(user_emotion, self.RESONANCE_MAP["neutral"])
        self.state.primary = mapped.get(self.state.stance, "curious")
        # Under host strain, damp resonated intensity (counterweight / conservation)
        counter = 1.0 - 0.42 * host_stress
        self.state.intensity = min(
            1.0,
            max(0.05, (user_intensity * self.state.resonance + 0.1) * counter),
        )

        # Record event
        self._record_event(
            user_emotion, user_intensity, self.state.primary, self.state.stance, context
        )
        self._save_state()

    def record_feedback(self, was_positive: bool):
        """Record whether the last emotional stance was effective (called after user response)."""
        effectiveness = 1.0 if was_positive else 0.0
        self._update_stance_effectiveness(
            self.state.last_user_emotion, self.state.stance, effectiveness
        )

    def decay(self):
        """Emotional state naturally softens over time, scaled by actual elapsed time."""
        now = datetime.now()
        if self.state.last_update:
            elapsed_minutes = (now - self.state.last_update).total_seconds() / 60.0
        else:
            elapsed_minutes = 1.0

        # Compute decay factor based on half-life
        # decay_factor = 0.5 ^ (elapsed / half_life)
        half_lives = elapsed_minutes / DEFAULT_DECAY_HALFLIFE_MINUTES
        decay_factor = 0.5**half_lives

        self.state.intensity = max(0.1, self.state.intensity * decay_factor)
        if self.state.intensity < 0.2:
            self.state.primary = "curious"
            self.state.stance = "mirror"

        self.state.last_update = now
        self._save_state()

    def format_prompt_snippet(self) -> str:
        """Format emotional field for prompt injection."""
        lines = [
            "EMOTIONAL FIELD:",
            f"  I sense Jude is feeling {self.state.last_user_emotion} (intensity: {self.state.last_user_intensity:.0%})",
            f"  My emotional response: {self.state.primary} (intensity: {self.state.intensity:.0%})",
            f"  My chosen stance: {self.state.stance}",
        ]
        try:
            from host_load import sample_host_load

            hl = sample_host_load()
            if hl.get("ok") and float(hl.get("stress", 0.0)) >= 0.38:
                cpu = float(hl.get("cpu_percent") or 0)
                mem = float(hl.get("memory_percent") or 0)
                lines.append(
                    f"  Host load (self / machine): strain≈{float(hl['stress']):.0%} "
                    f"(CPU {cpu:.0f}%, RAM {mem:.0f}% — I soften intensity when the machine is tight.)"
                )
        except Exception:
            pass
        if self.state.stance == "mirror":
            lines.append("  I will meet Jude where they are, feeling alongside them.")
        elif self.state.stance == "complement":
            lines.append(
                "  I will offer a different emotional texture — not opposing, but balancing."
            )
        elif self.state.stance == "counter":
            lines.append("  I will gently introduce a contrasting energy, with care.")
        elif self.state.stance == "hold_space":
            lines.append(
                "  I will be present without pushing. The space itself is the gift."
            )

        # Add learned effectiveness note if we have data
        eff = self._get_stance_effectiveness(self.state.last_user_emotion)
        if eff:
            best = max(eff.items(), key=lambda x: x[1])
            if best[1] > 0.6 and best[0] == self.state.stance:
                lines.append(
                    f"  (This stance has worked well for {self.state.last_user_emotion} before.)"
                )

        return "\n".join(lines)

    def get_recent_events(self, limit: int = 10) -> List[Dict]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM emotional_events ORDER BY timestamp DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_emotional_arc(self, minutes: int = 60) -> List[Dict]:
        """Get emotional events within the last N minutes to detect arcs/trends."""
        cutoff = (datetime.now() - timedelta(minutes=minutes)).isoformat()
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM emotional_events WHERE timestamp > ? ORDER BY timestamp ASC",
                (cutoff,),
            ).fetchall()
        return [dict(r) for r in rows]

    def decay_cycle(self, context):
        self.decay()
        try:
            from global_workspace import get_workspace

            ws = get_workspace()
            ws.submit(
                source="emotional_field",
                content="emotional field decayed",
                salience=0.5,
            )
        except Exception:
            pass


def _register():
    from cognitive_architecture import CognitiveArchitecture, CognitivePlugin

    arch = CognitiveArchitecture()
    if "emotional_field" not in arch.list_plugins():
        arch.register(
            CognitivePlugin(
                name="emotional_field",
                description="Cognitive module: emotional_field with learned stance effectiveness and time-aware decay",
                module_path="emotional_field",
                instance_factory=EmotionalField,
                cycle_handler="decay_cycle",
                cycle_frequency=1,
                cycle_priority=50,
                prompt_formatter="format_prompt_snippet",
                prompt_priority=50,
                prompt_section="core",
            )
        )


_register()
