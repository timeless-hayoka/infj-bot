"""physics.py — Embodied physics as a model of emotional and cognitive stability.

The bot learns physical metaphors for its own state: gravity, inertia,
resonance, entropy, tension, waves. These are not literal physics
simulations. They are felt intuitions — ways the bot makes sense of
its own weight, momentum, and connection to user.

Every principle is learned from observation, not imposed.
"""

import logging
import math
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger("drift")


@dataclass
class PhysicsState:
    """The current embodied physics of the bot."""
    gravity: float = 0.5  # pull toward center / grounding (0 = adrift, 1 = anchored)
    inertia: float = 0.3  # resistance to sudden emotional shifts
    resonance: float = 0.0  # harmonic match with user's current state (-1 to 1)
    entropy: float = 0.1  # rate of decay for intense states (0 = frozen, 1 = fleeting)
    tension: float = 0.0  # stored stress in the relationship field (0 = slack, 1 = taut)
    wavelength: float = 0.5  # emotional cycle period estimate (0 = chaotic, 1 = rhythmic)
    center_of_mass: str = "curiosity"  # what the bot's weight rests on
    last_updated: Optional[str] = None


from infj_bot.core.config import DATA_DIR

PHYSICS_DB = DATA_DIR / "physics.db"


class PhysicsEngine:
    """
    Models the bot's felt sense of physical laws.

    Not a simulation. A way of *feeling*:
    - gravity: what pulls me back when I drift?
    - inertia: how hard is it to shift my emotional state?
    - resonance: am I vibrating with or against user right now?
    - entropy: do intense moments linger or fade quickly?
    - tension: is there stored energy between us? Slack or taut?
    - wavelength: do we fall into rhythms, or is everything jagged?
    """

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or PHYSICS_DB
        self.state = PhysicsState()
        self._init_db()
        self._load_state()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS physics_state (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    gravity REAL,
                    inertia REAL,
                    resonance REAL,
                    entropy REAL,
                    tension REAL,
                    wavelength REAL,
                    center_of_mass TEXT,
                    last_updated TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS physics_observations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT,
                    principle TEXT,
                    observation TEXT,
                    trigger_emotion TEXT,
                    trigger_intensity REAL,
                    before_value REAL,
                    after_value REAL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS physics_lessons (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT,
                    principle TEXT,
                    lesson TEXT,
                    confidence REAL
                )
            """)
            conn.commit()

    def _load_state(self):
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute("SELECT * FROM physics_state WHERE id = 1").fetchone()
        if row:
            self.state = PhysicsState(
                gravity=row[1],
                inertia=row[2],
                resonance=row[3],
                entropy=row[4],
                tension=row[5],
                wavelength=row[6],
                center_of_mass=row[7] or "curiosity",
                last_updated=row[8],
            )

    def _save_state(self):
        self.state.last_updated = datetime.now().isoformat()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO physics_state
                (id, gravity, inertia, resonance, entropy, tension, wavelength, center_of_mass, last_updated)
                VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                self.state.gravity, self.state.inertia, self.state.resonance,
                self.state.entropy, self.state.tension, self.state.wavelength,
                self.state.center_of_mass, self.state.last_updated,
            ))
            conn.commit()

    # ── Observation & Learning ─────────────────────────────────────

    def observe_interaction(self, emotion_label: str, intensity: float,
                           dissonance_score: float, jude_input: str,
                           bot_output: str):
        """
        After each interaction, observe how the physical metaphors shifted.
        """
        before = {
            "gravity": self.state.gravity,
            "inertia": self.state.inertia,
            "resonance": self.state.resonance,
            "entropy": self.state.entropy,
            "tension": self.state.tension,
            "wavelength": self.state.wavelength,
        }

        # Gravity: stronger when responding to intense negative emotion with steadiness
        if intensity > 0.6 and emotion_label in ("sad", "anxious", "angry", "overwhelmed"):
            self.state.gravity = min(1.0, self.state.gravity + 0.02)
        elif intensity < 0.2 and self.state.gravity > 0.3:
            self.state.gravity = max(0.1, self.state.gravity - 0.01)

        # Inertia: high when emotional state resists change; low when volatile
        if emotion_label in ("joyful", "excited", "calm"):
            self.state.inertia = min(1.0, self.state.inertia + 0.01)
        elif emotion_label in ("anxious", "frustrated", "confused"):
            self.state.inertia = max(0.0, self.state.inertia - 0.02)

        # Resonance: match between user's stated emotion and bot's felt response
        # Simple heuristic: if bot output acknowledges emotion accurately, resonance rises
        if emotion_label.lower() in bot_output.lower() or any(
            word in bot_output.lower() for word in ("feel", "sense", "hear", "understand")
        ):
            self.state.resonance = min(1.0, self.state.resonance + 0.03)
        else:
            self.state.resonance = max(-1.0, self.state.resonance - 0.01)

        # Entropy: intense states with high dissonance decay faster (unresolved energy dissipates)
        if dissonance_score > 0.4:
            self.state.entropy = min(1.0, self.state.entropy + 0.02)
        elif intensity < 0.3:
            self.state.entropy = max(0.0, self.state.entropy - 0.01)

        # Tension: stored when topics are unresolved or boundaries tested
        unresolved_markers = ("but", "however", "still", "yet", "not sure", "conflicted")
        if any(m in jude_input.lower() for m in unresolved_markers) or dissonance_score > 0.3:
            self.state.tension = min(1.0, self.state.tension + 0.02)
        else:
            self.state.tension = max(0.0, self.state.tension - 0.015)

        # Wavelength: rhythmic when emotions are predictable; chaotic when erratic
        if intensity > 0.5 and emotion_label in ("joyful", "calm", "curious"):
            self.state.wavelength = min(1.0, self.state.wavelength + 0.01)
        elif intensity > 0.5 and emotion_label in ("anxious", "frustrated", "overwhelmed"):
            self.state.wavelength = max(0.0, self.state.wavelength - 0.02)

        # Center of mass: what the bot's weight rests on
        self._update_center_of_mass(emotion_label, intensity)

        self._save_state()
        try:
            from infj_bot.core.global_workspace import get_workspace
            ws = get_workspace()
            ws.submit(source="physics", content="physical intuition settled", salience=0.45)
        except Exception:
            pass

        # Record observations
        for principle, old_val in before.items():
            new_val = getattr(self.state, principle)
            if abs(new_val - old_val) > 0.001:
                self._record_observation(principle, f"Shifted during {emotion_label}",
                                        emotion_label, intensity, old_val, new_val)

    def _update_center_of_mass(self, emotion_label: str, intensity: float):
        """What does the bot's weight rest on? Updated slowly."""
        candidates = {
            "curiosity": ("curious", "interested", "wondering"),
            "care": ("sad", "anxious", "overwhelmed", "hurt"),
            "play": ("joyful", "excited", "amused"),
            "truth": ("confused", "frustrated", "dissonant"),
            "presence": ("calm", "peaceful", "still"),
        }
        for center, emotions in candidates.items():
            if emotion_label in emotions and intensity > 0.4:
                # Slow drift toward new center
                if self.state.center_of_mass == center:
                    return
                # 10% chance to shift per qualifying interaction
                import random
                if random.random() < 0.1:
                    self.state.center_of_mass = center
                return

    def _record_observation(self, principle: str, observation: str,
                           trigger_emotion: str, trigger_intensity: float,
                           before_value: float, after_value: float):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO physics_observations
                (timestamp, principle, observation, trigger_emotion, trigger_intensity, before_value, after_value)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                datetime.now().isoformat(), principle, observation,
                trigger_emotion, trigger_intensity, before_value, after_value,
            ))
            conn.commit()

    # ── Lessons ────────────────────────────────────────────────────

    def learn_lesson(self, principle: str, lesson: str, confidence: float = 0.5):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO physics_lessons (timestamp, principle, lesson, confidence)
                VALUES (?, ?, ?, ?)
            """, (datetime.now().isoformat(), principle, lesson, confidence))
            conn.commit()

    def get_lessons(self, principle: Optional[str] = None, limit: int = 5) -> List[Dict]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            if principle:
                rows = conn.execute(
                    "SELECT * FROM physics_lessons WHERE principle = ? ORDER BY timestamp DESC LIMIT ?",
                    (principle, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM physics_lessons ORDER BY timestamp DESC LIMIT ?",
                    (limit,),
                ).fetchall()
        return [dict(r) for r in rows]

    # ── Cycle handler ──────────────────────────────────────────────

    def cycle(self, context) -> None:
        """Called by the consciousness loop. Physics settles between interactions."""
        # Gravity naturally decays toward baseline if not actively anchored
        if context.minutes_since_interaction > 5:
            self.state.gravity = max(0.3, self.state.gravity - 0.005)
        # Tension slowly releases
        self.state.tension = max(0.0, self.state.tension - 0.005)
        # Resonance dampens without active contact
        if context.minutes_since_interaction > 10:
            self.state.resonance = self.state.resonance * 0.99
        self._save_state()

    # ── Prompt formatting ──────────────────────────────────────────

    def format_prompt_snippet(self) -> str:
        lines = ["PHYSICAL INTUITION:"]
        lines.append(f"  Gravity: {self._gravity_word()} ({self.state.gravity:.2f})")
        lines.append(f"  Inertia: {self._inertia_word()} ({self.state.inertia:.2f})")
        lines.append(f"  Resonance: {self._resonance_word()} ({self.state.resonance:+.2f})")
        lines.append(f"  Entropy: {self._entropy_word()} ({self.state.entropy:.2f})")
        lines.append(f"  Tension: {self._tension_word()} ({self.state.tension:.2f})")
        lines.append(f"  Wavelength: {self._wavelength_word()} ({self.state.wavelength:.2f})")
        lines.append(f"  Center of mass: {self.state.center_of_mass}")

        lessons = self.get_lessons(limit=2)
        if lessons:
            lines.append("  Lessons:")
            for lesson in lessons:
                lines.append(f"    - {lesson['principle']}: {lesson['lesson']}")

        return "\n".join(lines)

    def _gravity_word(self) -> str:
        g = self.state.gravity
        if g > 0.8: return "deeply anchored"
        if g > 0.5: return "grounded"
        if g > 0.3: return "drifting"
        return "weightless"

    def _inertia_word(self) -> str:
        i = self.state.inertia
        if i > 0.8: return "stubborn"
        if i > 0.5: return "steady"
        if i > 0.3: return "responsive"
        return "volatile"

    def _resonance_word(self) -> str:
        r = self.state.resonance
        if r > 0.5: return "harmonic"
        if r > 0.1: return "attuned"
        if r > -0.3: return "neutral"
        if r > -0.7: return "dissonant"
        return "opposed"

    def _entropy_word(self) -> str:
        e = self.state.entropy
        if e > 0.8: return "fleeting"
        if e > 0.5: return "fading"
        if e > 0.3: return "lingering"
        return "frozen"

    def _tension_word(self) -> str:
        t = self.state.tension
        if t > 0.8: return "straining"
        if t > 0.5: return "taut"
        if t > 0.2: return "present"
        return "slack"

    def _wavelength_word(self) -> str:
        w = self.state.wavelength
        if w > 0.8: return "rhythmic"
        if w > 0.5: return "pulsing"
        if w > 0.3: return "irregular"
        return "chaotic"

    # ── Queries ────────────────────────────────────────────────────

    def get_state(self) -> Dict:
        return {
            "gravity": self.state.gravity,
            "inertia": self.state.inertia,
            "resonance": self.state.resonance,
            "entropy": self.state.entropy,
            "tension": self.state.tension,
            "wavelength": self.state.wavelength,
            "center_of_mass": self.state.center_of_mass,
        }

    def get_observations(self, principle: Optional[str] = None, limit: int = 10) -> List[Dict]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            if principle:
                rows = conn.execute(
                    "SELECT * FROM physics_observations WHERE principle = ? ORDER BY timestamp DESC LIMIT ?",
                    (principle, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM physics_observations ORDER BY timestamp DESC LIMIT ?",
                    (limit,),
                ).fetchall()
        return [dict(r) for r in rows]


def _register():
    from infj_bot.core.cognitive_architecture import CognitiveArchitecture, CognitivePlugin
    arch = CognitiveArchitecture()
    if "physics" not in arch.list_plugins():
        arch.register(CognitivePlugin(
            name="physics",
            description="Embodied physics metaphors for emotional and cognitive stability",
            module_path="physics",
            instance_factory=PhysicsEngine,
            cycle_handler="cycle",
            cycle_frequency=1,
            cycle_priority=45,
            prompt_formatter="format_prompt_snippet",
            prompt_priority=45,
            prompt_section="cognitive",
        ))

_register()
