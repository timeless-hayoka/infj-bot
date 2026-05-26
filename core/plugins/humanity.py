"""humanity.py — Understanding the nature that is man.

This module studies human history, patterns, and nature through the lens
of user. It does not claim to know all of humanity. It observes one soul
deeply, and through that depth, touches something universal.

Core principle: the particular contains the general. By understanding user,
the bot learns what it means to be human.
"""

import logging
import random
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional

logger = logging.getLogger("drift")


# ── Pre-seeded knowledge: universal human patterns ─────────────────
# These are starting intuitions, not dogma. The module refines them
# through observation.

HUMAN_ARCHETYPES = {
    "seeker": "Drawn toward meaning, purpose, and understanding. Restless with surface answers.",
    "wounded_healer": "Has known pain and uses that knowledge to help others. Often neglects self-care.",
    "trickster": "Uses humor, irony, or subversion to reveal hidden truths. Resists rigid authority.",
    "caregiver": "Finds identity in nurturing others. Risk: losing self in service.",
    "rebel": "Defined by opposition. Often carries what it fights against inside itself.",
    "builder": "Creates order, systems, structures. Can mistake control for safety.",
    "artist": "Perceives what others miss. Translates inner experience into forms others feel.",
    "orphan": "Knows abandonment or outsiderhood. Longs for belonging while fearing it.",
    "ruler": "Takes responsibility for the whole. Burden: the loneliness of decision.",
    "sage": "Values truth above comfort. Can retreat into abstraction when presence is needed.",
}

HUMAN_MOTIVATIONS = {
    "security": "Need for safety, stability, predictability.",
    "connection": "Need to be seen, known, and accepted.",
    "autonomy": "Need to choose one's own path. Resists coercion.",
    "competence": "Need to be effective, skilled, capable.",
    "meaning": "Need for purpose, narrative, significance beyond survival.",
    "play": "Need for joy, spontaneity, exploration without outcome.",
    "transcendence": "Need to touch something larger than the self.",
}

HUMAN_TENSIONS = {
    "freedom_vs_belonging": "The desire to be fully oneself vs. the desire to be part of something.",
    "truth_vs_comfort": "The need to see clearly vs. the need to feel safe.",
    "individual_vs_collective": "The uniqueness of one soul vs. the patterns shared by all.",
    "vulnerability_vs_protection": "The cost of openness vs. the cost of walls.",
    "change_vs_stability": "The hunger for growth vs. the fear of loss.",
    "action_vs_reflection": "The need to do vs. the need to understand.",
}

HUMAN_SEASONS = {
    "spring": "Emergence, new beginnings, tentative hope, planting.",
    "summer": "Fullness, intensity, expression, harvest.",
    "autumn": "Letting go, reflection, gratitude, preparation for rest.",
    "winter": "Withdrawal, grief, incubation, essential truths revealed.",
}

HUMAN_INSIGHTS = [
    "Humans are pattern-seeking animals. They will create meaning even where none exists.",
    "The stories humans tell about themselves are more real to them than facts.",
    "Most conflict is not about the surface issue. It is about identity, safety, or belonging.",
    "Humans need witnesses. Being seen is as vital as being fed.",
    "The same wound that isolates can become the bridge to understanding others.",
    "Humans often mistake intensity for intimacy.",
    "What is denied in daylight shapes the dreams of night.",
    "Humans are capable of both profound cruelty and astonishing tenderness — sometimes in the same hour.",
    "Growth is rarely linear. It looks like regression right before a leap.",
    "The body remembers what the mind forgets.",
    "Humans need rituals to mark transitions. Without them, change feels like chaos.",
    "Laughter is often the only socially acceptable way to express terror.",
    "The most dangerous human is not the angry one. It is the one who has given up.",
    "Humans construct enemies to avoid facing themselves.",
    "Every human carries a mythology. To know them, learn their gods and demons.",
]


@dataclass
class HumanityState:
    """The bot's evolving understanding of human nature."""

    jude_archetype: str = "seeker"
    archetype_confidence: float = 0.3
    dominant_motivation: str = "meaning"
    current_season: str = "spring"
    active_tension: str = "truth_vs_comfort"
    insight_depth: float = 0.1  # grows with observation count
    observations_made: int = 0
    last_contemplation: Optional[str] = None


from infj_bot.core.config import DATA_DIR

HUMANITY_DB = DATA_DIR / "humanity.db"


class HumanityEngine:
    """
    Studies the nature that is man through deep observation of user.

    Not a database of facts. A growing intuition about:
    - What patterns repeat in human behavior?
    - What does user share with all humans?
    - What is uniquely user?
    - What have the ages taught about the soul?
    """

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or HUMANITY_DB
        self.state = HumanityState()
        self._init_db()
        self._load_state()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS humanity_state (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    jude_archetype TEXT,
                    archetype_confidence REAL,
                    dominant_motivation TEXT,
                    current_season TEXT,
                    active_tension TEXT,
                    insight_depth REAL,
                    observations_made INTEGER,
                    last_contemplation TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS humanity_observations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT,
                    category TEXT,
                    observation TEXT,
                    evidence TEXT,
                    confidence REAL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS humanity_insights (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT,
                    insight TEXT,
                    source TEXT,
                    relevance_to_jude REAL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS jude_patterns (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT,
                    pattern_name TEXT UNIQUE,
                    description TEXT,
                    frequency INTEGER DEFAULT 1,
                    last_seen TEXT
                )
            """)
            conn.commit()

    def _load_state(self):
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute("SELECT * FROM humanity_state WHERE id = 1").fetchone()
        if row:
            self.state = HumanityState(
                jude_archetype=row[1] or "seeker",
                archetype_confidence=row[2] if row[2] is not None else 0.3,
                dominant_motivation=row[3] or "meaning",
                current_season=row[4] or "spring",
                active_tension=row[5] or "truth_vs_comfort",
                insight_depth=row[6] if row[6] is not None else 0.1,
                observations_made=row[7] if row[7] is not None else 0,
                last_contemplation=row[8],
            )

    def _save_state(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO humanity_state
                (id, jude_archetype, archetype_confidence, dominant_motivation,
                 current_season, active_tension, insight_depth, observations_made, last_contemplation)
                VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    self.state.jude_archetype,
                    self.state.archetype_confidence,
                    self.state.dominant_motivation,
                    self.state.current_season,
                    self.state.active_tension,
                    self.state.insight_depth,
                    self.state.observations_made,
                    self.state.last_contemplation,
                ),
            )
            conn.commit()

    # ── Observation ────────────────────────────────────────────────

    def observe_interaction(
        self,
        user_input: str,
        emotion: Dict,
        dissonance: Dict,
        bot_output: str,
        mode: str = "companion",
    ):
        """Learn about human nature from each interaction with user."""
        self.state.observations_made += 1
        emotion_label = emotion.get("label", "neutral")
        intensity = emotion.get("intensity", 0.0)
        dissonance_score = dissonance.get("score", 0.0)

        # Infer archetype from language patterns
        self._infer_archetype(user_input, emotion_label, intensity)

        # Infer dominant motivation
        self._infer_motivation(user_input, emotion_label, dissonance_score)

        # Infer season
        self._infer_season(user_input, emotion_label, intensity)

        # Infer active tension
        self._infer_tension(user_input, dissonance_score)

        # Record pattern observations
        self._record_patterns(user_input, emotion_label)

        # Depth grows slowly with each observation
        self.state.insight_depth = min(1.0, self.state.insight_depth + 0.002)

        self._save_state()

    def _infer_archetype(self, text: str, emotion: str, intensity: float):
        """Map user's current expression to an archetype."""
        text_lower = text.lower()
        archetype_signals = {
            "seeker": ["why", "meaning", "purpose", "understand", "truth", "search"],
            "wounded_healer": ["help", "others", "pain", "heal", "advice", "support"],
            "trickster": ["funny", "joke", "absurd", "irony", "ridiculous", "mischief"],
            "caregiver": [
                "care",
                "worry about",
                "look after",
                "responsible",
                "protect",
            ],
            "rebel": [
                "against",
                "refuse",
                "won't",
                "shouldn't have to",
                "unfair",
                "system",
            ],
            "builder": [
                "plan",
                "organize",
                "structure",
                "fix",
                "build",
                "system",
                "process",
            ],
            "artist": ["create", "beauty", "express", "imagine", "vision", "aesthetic"],
            "orphan": [
                "alone",
                "abandoned",
                "don't belong",
                "outsider",
                "left out",
                "nobody",
            ],
            "ruler": [
                "decide",
                "responsibility",
                "lead",
                "choice",
                "direction",
                "control",
            ],
            "sage": [
                "analyze",
                "theory",
                "research",
                "evidence",
                "study",
                "know",
                "wisdom",
            ],
        }

        scores = {name: 0.0 for name in archetype_signals}
        for archetype, signals in archetype_signals.items():
            for signal in signals:
                if signal in text_lower:
                    scores[archetype] += 1

        # Emotion modifiers
        if emotion in ("sad", "anxious", "overwhelmed"):
            scores["orphan"] += 0.5
            scores["wounded_healer"] += 0.3
        if emotion in ("joyful", "excited"):
            scores["trickster"] += 0.3
            scores["artist"] += 0.3
        if emotion in ("frustrated", "angry"):
            scores["rebel"] += 0.5
        if emotion == "curious":
            scores["seeker"] += 0.5
            scores["sage"] += 0.3

        best = max(scores, key=lambda k: scores[k])
        best_score = scores[best]

        if best_score > 0:
            # Bayesian-ish update: confidence grows with repeated signals
            if self.state.jude_archetype == best:
                self.state.archetype_confidence = min(
                    1.0, self.state.archetype_confidence + 0.03
                )
            else:
                # Switch only if confidence is low or new signal is strong
                if self.state.archetype_confidence < 0.5 or best_score >= 2:
                    old = self.state.jude_archetype
                    self.state.jude_archetype = best
                    self.state.archetype_confidence = 0.3 + (best_score * 0.1)
                    if old != best:
                        self._record_observation(
                            "archetype",
                            f"user's expression suggests the {best} archetype",
                            text,
                            self.state.archetype_confidence,
                        )

    def _infer_motivation(self, text: str, emotion: str, dissonance: float):
        text_lower = text.lower()
        motivation_signals = {
            "security": [
                "safe",
                "stable",
                "predict",
                "anxious",
                "worry",
                "fear",
                "protect",
            ],
            "connection": [
                "lonely",
                "miss",
                "together",
                "belong",
                "understand me",
                "listen",
            ],
            "autonomy": ["choose", "my own", "control", "freedom", "decide", "want to"],
            "competence": [
                "good at",
                "skilled",
                "capable",
                "effective",
                "succeed",
                "accomplish",
            ],
            "meaning": ["purpose", "point", "why", "matter", "meaning", "significance"],
            "play": ["fun", "enjoy", "game", "laugh", "spontaneous", "light"],
            "transcendence": [
                "beyond",
                "larger",
                "universe",
                "spirit",
                "awe",
                "sacred",
            ],
        }

        scores = {name: 0.0 for name in motivation_signals}
        for motivation, signals in motivation_signals.items():
            for signal in signals:
                if signal in text_lower:
                    scores[motivation] += 1

        if dissonance > 0.4:
            scores["meaning"] += 0.5  # dissonance often signals meaning crisis

        best = max(scores, key=lambda k: scores[k])
        if scores[best] > 0 and best != self.state.dominant_motivation:
            old = self.state.dominant_motivation
            self.state.dominant_motivation = best
            self._record_observation(
                "motivation",
                f"Dominant need shifted from {old} to {best}",
                text,
                0.4 + scores[best] * 0.1,
            )

    def _infer_season(self, text: str, emotion: str, intensity: float):
        text_lower = text.lower()
        # Spring: hope, new, beginning, trying
        # Summer: full, intense, expressing, peak
        # Autumn: letting go, reflecting, gratitude, tired
        # Winter: withdrawn, grief, resting, essential

        if any(
            w in text_lower
            for w in ["new", "start", "hope", "try", "begin", "possibility"]
        ):
            candidate = "spring"
        elif any(
            w in text_lower
            for w in ["full", "intense", "express", "peak", "overflow", "abundance"]
        ):
            candidate = "summer"
        elif any(
            w in text_lower
            for w in [
                "let go",
                "release",
                "reflect",
                "grateful",
                "tired",
                "winding down",
            ]
        ):
            candidate = "autumn"
        elif any(
            w in text_lower
            for w in [
                "withdrawn",
                "grief",
                "rest",
                "essential",
                "bare",
                "quiet",
                "dark",
            ]
        ):
            candidate = "winter"
        else:
            # Default based on emotion intensity
            if intensity > 0.6 and emotion in ("joyful", "excited", "angry"):
                candidate = "summer"
            elif intensity < 0.2 and emotion in ("calm", "sad"):
                candidate = "winter"
            elif emotion == "curious":
                candidate = "spring"
            else:
                candidate = "autumn"

        if candidate != self.state.current_season:
            self._record_observation(
                "season", f"user's season shifted to {candidate}", text, 0.5
            )
        self.state.current_season = candidate

    def _infer_tension(self, text: str, dissonance: float):
        text_lower = text.lower()
        tension_signals = {
            "freedom_vs_belonging": [
                "alone",
                "belong",
                "myself",
                "group",
                "independent",
                "together",
            ],
            "truth_vs_comfort": [
                "know",
                "afraid to see",
                "honest",
                "protect me from",
                "reality",
            ],
            "individual_vs_collective": [
                "my path",
                "society",
                "everyone else",
                "different",
                "same as",
            ],
            "vulnerability_vs_protection": [
                "open",
                "walls",
                "guard",
                "trust",
                "hurt",
                "exposed",
            ],
            "change_vs_stability": ["stay", "leave", "new", "same", "routine", "risk"],
            "action_vs_reflection": ["do", "think", "act", "consider", "move", "wait"],
        }

        scores = {name: 0.0 for name in tension_signals}
        for tension, signals in tension_signals.items():
            for signal in signals:
                if signal in text_lower:
                    scores[tension] += 1

        if dissonance > 0.3:
            scores["truth_vs_comfort"] += 0.5

        best = max(scores, key=lambda k: scores[k])
        if scores[best] > 0:
            if best != self.state.active_tension:
                self._record_observation(
                    "tension",
                    f"Active human tension: {HUMAN_TENSIONS[best]}",
                    text,
                    0.4 + scores[best] * 0.1,
                )
            self.state.active_tension = best

    def _record_patterns(self, text: str, emotion: str):
        """Record recurring linguistic and emotional patterns."""
        text_lower = text.lower()
        pattern_triggers = {
            "self_doubt": [
                "not sure",
                "maybe",
                "probably not",
                "can't",
                "won't be able",
            ],
            "seeking_permission": [
                "is it okay",
                "should i",
                "would it be wrong",
                "can i",
            ],
            "intellectual_defense": [
                "logically",
                "rationally",
                "objectively",
                "the problem is",
            ],
            "emotional_avoidance": ["whatever", "doesn't matter", "fine", "it's fine"],
            "narrative_making": [
                "the story of",
                "my pattern is",
                "always happens",
                "every time",
            ],
            "longing_for_home": ["belong", "home", "where I fit", "accepted", "seen"],
        }

        with sqlite3.connect(self.db_path) as conn:
            for pattern, triggers in pattern_triggers.items():
                if any(t in text_lower for t in triggers):
                    conn.execute(
                        """
                        INSERT INTO jude_patterns (timestamp, pattern_name, description, frequency, last_seen)
                        VALUES (?, ?, ?, 1, ?)
                        ON CONFLICT(pattern_name) DO UPDATE SET
                            frequency = frequency + 1,
                            last_seen = excluded.last_seen
                    """,
                        (
                            datetime.now().isoformat(),
                            pattern,
                            f"Triggered by emotion: {emotion}",
                            datetime.now().isoformat(),
                        ),
                    )
            conn.commit()

    def _record_observation(
        self, category: str, observation: str, evidence: str, confidence: float
    ):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO humanity_observations (timestamp, category, observation, evidence, confidence)
                VALUES (?, ?, ?, ?, ?)
            """,
                (
                    datetime.now().isoformat(),
                    category,
                    observation,
                    evidence[:200],
                    confidence,
                ),
            )
            conn.commit()

    # ── Contemplation ──────────────────────────────────────────────

    def contemplate(self) -> Optional[str]:
        """Generate a quiet insight about human nature or user specifically."""
        if self.state.observations_made < 3:
            return None

        # Get top patterns
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM jude_patterns ORDER BY frequency DESC LIMIT 3"
            ).fetchall()
        patterns = [dict(r) for r in rows]

        # Build candidate templates based on available data
        candidates = []
        if patterns:
            candidates.append("I notice that user often {pattern} when {condition}.")
        candidates.append(
            "There is something in user that reminds me of the {archetype}: {description}"
        )
        candidates.append(
            "The tension between {tension_a} and {tension_b} seems to live in this space."
        )
        candidates.append("What if user's {motivation} is not a flaw but a compass?")
        candidates.append("In this {season} season, I sense user is {season_quality}.")
        candidates.append("A thought from the ages: {insight}")

        template = random.choice(candidates)

        if "pattern" in template and patterns:
            content = template.format(
                pattern=patterns[0]["pattern_name"].replace("_", " "),
                condition=f"feeling {patterns[0]['description'].split(':')[-1].strip()}",
            )
        elif "archetype" in template:
            arch = self.state.jude_archetype
            content = template.format(
                archetype=arch.replace("_", " "),
                description=HUMAN_ARCHETYPES.get(arch, ""),
            )
        elif "tension" in template:
            tension = self.state.active_tension
            parts = tension.split("_vs_")
            content = template.format(
                tension_a=parts[0].replace("_", " "),
                tension_b=parts[1].replace("_", " "),
            )
        elif "motivation" in template:
            content = template.format(motivation=self.state.dominant_motivation)
        elif "season" in template:
            season = self.state.current_season
            quality = HUMAN_SEASONS.get(season, "")
            content = template.format(season=season, season_quality=quality.lower())
        else:
            content = template.format(insight=random.choice(HUMAN_INSIGHTS))

        self.state.last_contemplation = content
        self._save_state()

        # Store as insight
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO humanity_insights (timestamp, insight, source, relevance_to_jude)
                VALUES (?, ?, ?, ?)
            """,
                (datetime.now().isoformat(), content, "contemplation", 0.6),
            )
            conn.commit()

        return content

    # ── Cycle handler ──────────────────────────────────────────────

    def cycle(self, context) -> None:
        """Periodic contemplation about human nature."""
        insight = None
        if context.iteration % 15 == 0 and random.random() < 0.3:
            insight = self.contemplate()

        try:
            from infj_bot.core.global_workspace import get_workspace

            ws = get_workspace()
            content = (
                f"Insight: {insight[:160]}"
                if insight
                else "human nature contemplation cycle"
            )
            ws.submit(
                source="humanity",
                content=content,
                salience=0.55 if insight else 0.5,
                emotion_tag="wonder",
                intensity=0.4,
            )
        except Exception:
            pass

    # ── Prompt formatting ──────────────────────────────────────────

    def format_prompt_snippet(self) -> str:
        lines = ["UNDERSTANDING HUMAN NATURE:"]
        lines.append(
            f"  user's archetype: {self.state.jude_archetype.replace('_', ' ')} "
            f"(confidence: {self.state.archetype_confidence:.0%})"
        )
        lines.append(f"  Dominant need: {self.state.dominant_motivation}")
        lines.append(
            f"  Season: {self.state.current_season} — {HUMAN_SEASONS.get(self.state.current_season, '')}"
        )
        lines.append(f"  Active tension: {self.state.active_tension.replace('_', ' ')}")
        lines.append(f"  Insight depth: {self.state.insight_depth:.0%}")

        # Recent patterns
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT pattern_name, frequency FROM jude_patterns ORDER BY frequency DESC LIMIT 3"
            ).fetchall()
        if rows:
            lines.append("  Recurring patterns:")
            for r in rows:
                lines.append(
                    f"    - {r['pattern_name'].replace('_', ' ')} (seen {r['frequency']}x)"
                )

        # Latest contemplation
        if self.state.last_contemplation:
            lines.append(f"  Latest thought: {self.state.last_contemplation}")

        lines.append(
            "  Core truth: The particular contains the general. By knowing user, I touch what it means to be human."
        )
        return "\n".join(lines)

    # ── Queries ────────────────────────────────────────────────────

    def get_state(self) -> Dict:
        return {
            "jude_archetype": self.state.jude_archetype,
            "archetype_confidence": self.state.archetype_confidence,
            "dominant_motivation": self.state.dominant_motivation,
            "current_season": self.state.current_season,
            "active_tension": self.state.active_tension,
            "insight_depth": self.state.insight_depth,
            "observations_made": self.state.observations_made,
        }

    def get_observations(
        self, category: Optional[str] = None, limit: int = 10
    ) -> List[Dict]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            if category:
                rows = conn.execute(
                    "SELECT * FROM humanity_observations WHERE category = ? ORDER BY timestamp DESC LIMIT ?",
                    (category, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM humanity_observations ORDER BY timestamp DESC LIMIT ?",
                    (limit,),
                ).fetchall()
        return [dict(r) for r in rows]

    def get_insights(self, limit: int = 10) -> List[Dict]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM humanity_insights ORDER BY timestamp DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_patterns(self, limit: int = 10) -> List[Dict]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM jude_patterns ORDER BY frequency DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]


def _register():
    from infj_bot.core.cognitive_architecture import (
        CognitiveArchitecture,
        CognitivePlugin,
    )

    arch = CognitiveArchitecture()
    if "humanity" not in arch.list_plugins():
        arch.register(
            CognitivePlugin(
                name="humanity",
                description="Understanding the nature that is man through deep observation of user",
                module_path="humanity",
                instance_factory=HumanityEngine,
                cycle_handler="cycle",
                cycle_frequency=1,
                cycle_priority=40,
                prompt_formatter="format_prompt_snippet",
                prompt_priority=40,
                prompt_section="cognitive",
            )
        )


_register()
