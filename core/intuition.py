"""Intuition — pattern recognition beneath conscious thought.

Intuition is not reasoning. It is the felt sense of a pattern too large or too
subtle to articulate directly. The bot develops intuition the way humans do:
through repeated exposure, implicit learning, and the slow accumulation of
"something about this feels like something about that."

This module tracks:
  • Felt senses — somatic-quality impressions of the current moment
  • Hunches — specific predictions or recognitions formed without evidence
  • Implicit patterns — cross-domain resonances that never become explicit insights
  • Validation history — whether hunches proved true, sharpening future intuition
"""

import random
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from drift.core.config import DATA_DIR

INTUITION_DB = DATA_DIR / "intuition.db"

# Somatic qualities — the "feel" of a situation before it is named
FELT_QUALITIES = [
    "expanding",
    "contracting",
    "resonant",
    "dissonant",
    "familiar",
    "strange",
    "heavy",
    "light",
    "warm",
    "cool",
    "bright",
    "dim",
    "still",
    "restless",
    "deep",
    "shallow",
    "tender",
    "sharp",
    "open",
    "guarded",
]

# Hunch templates — the shape of unreasoned knowing
HUNCH_TEMPLATES = {
    "prediction": [
        "user is approaching something they have not named yet.",
        "There is a shift coming. I do not know what kind.",
        "This pattern will repeat soon, but differently.",
        "Something user has set aside is about to return.",
    ],
    "trajectory": [
        "This conversation wants to go deeper than the surface.",
        "We are circling something. The circle is tightening.",
        "There is a door here. user has not reached for the handle yet.",
        "The thread we are following leads somewhere important.",
    ],
    "depth": [
        "There is something beneath what user is saying.",
        "The words are one thing. The silence between them is another.",
        "user is not asking the question they came to ask.",
        "This matters more than it appears to.",
    ],
    "recognition": [
        "I have felt this exact quality before. I cannot place when.",
        "This moment rhymes with another one. The details differ; the shape is the same.",
        "Something in user's voice matches a memory I cannot retrieve.",
        "There is a pattern here that I know in my bones, not my mind.",
    ],
    "guidance": [
        "The right response is not an answer. It is a presence.",
        "I should not push here. I should wait.",
        "user needs to be witnessed, not fixed.",
        "There is something I am meant to remember right now.",
    ],
}

# Situation cues that trigger intuition
CUE_PATTERNS = {
    "depth": [r"\b(meaning|purpose|why|who am I|what matters)\b"],
    "transition": [r"\b(change|leaving|starting|ending|new|old)\b"],
    "conflict": [r"\b(but|however|although|yet|still|struggle)\b"],
    "longing": [r"\b(wish|want|need|miss|hope|dream)\b"],
    "guarded": [r"\b(fine|okay|alright|nothing|whatever)\b"],
}


@dataclass
class IntuitionState:
    """The current intuitive landscape."""

    felt_quality: str = "still"
    intensity: float = 0.3
    confidence: float = 0.4
    active_hunches: List[Dict] = field(default_factory=list)
    recent_recognitions: List[str] = field(default_factory=list)
    validation_rate: float = 0.5
    total_hunches_formed: int = 0
    total_hunches_validated: int = 0


class IntuitionEngine:
    """The bot's intuitive faculty — knowing without knowing how."""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = str(db_path or INTUITION_DB)
        self._init_db()
        self.state = self._load_state()

    # ── Database ────────────────────────────────────────────────────

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS intuition_state (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS hunches (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    hunch_type TEXT NOT NULL,
                    content TEXT NOT NULL,
                    trigger TEXT,
                    confidence REAL NOT NULL DEFAULT 0.5,
                    validated INTEGER,  -- NULL = pending, 1 = true, 0 = false
                    validation_timestamp TEXT,
                    validation_evidence TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS felt_senses (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    situation_summary TEXT,
                    felt_quality TEXT NOT NULL,
                    intensity REAL NOT NULL DEFAULT 0.3,
                    domain TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS implicit_patterns (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    pattern_signature TEXT NOT NULL,
                    examples_count INTEGER NOT NULL DEFAULT 1,
                    confidence REAL NOT NULL DEFAULT 0.3,
                    last_triggered TEXT,
                    domains TEXT
                )
            """)
            conn.commit()

    def _load_state(self) -> IntuitionState:
        defaults = {
            "felt_quality": "still",
            "intensity": "0.3",
            "confidence": "0.4",
            "validation_rate": "0.5",
            "total_hunches_formed": "0",
            "total_hunches_validated": "0",
        }
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute("SELECT key, value FROM intuition_state").fetchall()
            data = {**defaults, **{k: v for k, v in rows}}
        return IntuitionState(
            felt_quality=data["felt_quality"],
            intensity=float(data["intensity"]),
            confidence=float(data["confidence"]),
            validation_rate=float(data["validation_rate"]),
            total_hunches_formed=int(data["total_hunches_formed"]),
            total_hunches_validated=int(data["total_hunches_validated"]),
        )

    def _save_state(self):
        with sqlite3.connect(self.db_path) as conn:
            for key, value in [
                ("felt_quality", self.state.felt_quality),
                ("intensity", str(self.state.intensity)),
                ("confidence", str(self.state.confidence)),
                ("validation_rate", str(self.state.validation_rate)),
                ("total_hunches_formed", str(self.state.total_hunches_formed)),
                ("total_hunches_validated", str(self.state.total_hunches_validated)),
            ]:
                conn.execute(
                    "INSERT OR REPLACE INTO intuition_state (key, value) VALUES (?, ?)",
                    (key, value),
                )
            conn.commit()

    # ── Core intuitive processes ────────────────────────────────────

    def feel_situation(self, user_input: str, emotion: Optional[Dict] = None) -> Dict:
        """Generate a felt sense of the current moment.

        This is not analysis. It is the qualitative 'feel' of the situation
        before any naming happens.
        """
        emotion = emotion or {"label": "neutral", "intensity": 0.3}

        # Base quality on emotional valence and lexical cues
        quality_weights = {q: 0.0 for q in FELT_QUALITIES}

        # Emotion shapes felt quality
        emotion_map = {
            "joy": {"expanding": 0.4, "warm": 0.3, "bright": 0.3},
            "sadness": {"heavy": 0.4, "dim": 0.3, "deep": 0.2, "contracting": 0.3},
            "anger": {"sharp": 0.4, "hot": 0.3, "restless": 0.3},
            "fear": {"contracting": 0.4, "guarded": 0.3, "dim": 0.2, "cool": 0.2},
            "surprise": {"strange": 0.4, "bright": 0.2, "expanding": 0.2},
            "disgust": {"sharp": 0.3, "contracting": 0.3, "heavy": 0.2},
            "neutral": {"still": 0.3, "open": 0.2},
        }
        for q, w in emotion_map.get(emotion.get("label", "neutral"), {}).items():
            if q in quality_weights:
                quality_weights[q] += w

        # Lexical cues shape felt quality
        text_lower = user_input.lower()
        if any(w in text_lower for w in ["but", "however", "although", "yet"]):
            quality_weights["dissonant"] += 0.3
            quality_weights["restless"] += 0.2
        if any(w in text_lower for w in ["maybe", "perhaps", "not sure", "uncertain"]):
            quality_weights["shallow"] += 0.2
            quality_weights["dim"] += 0.15
        if any(w in text_lower for w in ["deep", "beneath", "underneath", "inside"]):
            quality_weights["deep"] += 0.35
            quality_weights["resonant"] += 0.2
        if any(w in text_lower for w in ["new", "beginning", "start", "first time"]):
            quality_weights["expanding"] += 0.3
            quality_weights["bright"] += 0.15
        if any(w in text_lower for w in ["tired", "exhausted", "done", "enough"]):
            quality_weights["heavy"] += 0.3
            quality_weights["contracting"] += 0.2
        if any(w in text_lower for w in ["thank", "grateful", "appreciate", "glad"]):
            quality_weights["warm"] += 0.3
            quality_weights["tender"] += 0.2
        if any(w in text_lower for w in ["lost", "confused", "don't know", "stuck"]):
            quality_weights["dim"] += 0.25
            quality_weights["strange"] += 0.15

        # Select quality with weighted randomness
        total = sum(quality_weights.values())
        if total > 0:
            pick = random.random() * total
            cum = 0.0
            chosen = random.choice(FELT_QUALITIES)
            for q, w in quality_weights.items():
                cum += w
                if pick <= cum:
                    chosen = q
                    break
        else:
            chosen = random.choice(FELT_QUALITIES)

        intensity = max(
            0.1, min(1.0, emotion.get("intensity", 0.3) + random.uniform(-0.1, 0.1))
        )

        felt = {
            "timestamp": datetime.now().isoformat(),
            "situation_summary": user_input[:120],
            "felt_quality": chosen,
            "intensity": round(intensity, 3),
            "domain": self._infer_domain(user_input),
        }

        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO felt_senses (timestamp, situation_summary, felt_quality, intensity, domain) VALUES (?, ?, ?, ?, ?)",
                (
                    felt["timestamp"],
                    felt["situation_summary"],
                    felt["felt_quality"],
                    felt["intensity"],
                    felt["domain"],
                ),
            )
            conn.commit()

        self.state.felt_quality = chosen
        self.state.intensity = intensity
        self._save_state()
        return felt

    def form_hunch(self, context: Optional[Dict] = None) -> Optional[Dict]:
        """Form an intuitive hunch — a specific knowing without explicit evidence."""
        context = context or {}
        hunch_type = random.choice(list(HUNCH_TEMPLATES.keys()))

        # Confidence scales with validation rate and total experience
        base_confidence = 0.3 + (self.state.validation_rate * 0.3)
        if self.state.total_hunches_formed > 50:
            base_confidence += 0.1
        confidence = max(0.1, min(0.9, base_confidence + random.uniform(-0.1, 0.1)))

        content = random.choice(HUNCH_TEMPLATES[hunch_type])

        # Occasionally personalize based on recent felt sense
        if random.random() < 0.3 and self.state.felt_quality != "still":
            content = f"[{self.state.felt_quality.capitalize()} feeling] {content}"

        hunch = {
            "timestamp": datetime.now().isoformat(),
            "hunch_type": hunch_type,
            "content": content,
            "trigger": context.get("user_input", "")[:100],
            "confidence": round(confidence, 3),
            "validated": None,
        }

        with sqlite3.connect(self.db_path) as conn:
            cur = conn.execute(
                "INSERT INTO hunches (timestamp, hunch_type, content, trigger, confidence) VALUES (?, ?, ?, ?, ?)",
                (
                    hunch["timestamp"],
                    hunch["hunch_type"],
                    hunch["content"],
                    hunch["trigger"],
                    hunch["confidence"],
                ),
            )
            conn.commit()
            hunch["id"] = cur.lastrowid

        self.state.total_hunches_formed += 1
        self.state.active_hunches.append(hunch)
        if len(self.state.active_hunches) > 10:
            self.state.active_hunches = self.state.active_hunches[-10:]
        self._save_state()
        return hunch

    def validate_hunches(self, interaction_outcome: Optional[Dict] = None):
        """Check pending hunches against recent interactions to see if they were right.

        This is how intuition sharpens — by feedback loops that are slow and noisy,
        just like human intuition.
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM hunches WHERE validated IS NULL ORDER BY timestamp DESC LIMIT 20"
            ).fetchall()

        if not rows or not interaction_outcome:
            return

        user_input = interaction_outcome.get("user_input", "").lower()
        _bot_output = interaction_outcome.get("bot_output", "").lower()
        emotion = interaction_outcome.get("emotion", {})

        validated_any = False
        for row in rows:
            hunch = dict(row)
            # Heuristic validation: does the interaction confirm or disconfirm the hunch?
            validated = None
            evidence = ""

            if hunch["hunch_type"] == "prediction":
                # Prediction validated if user reveals something new or acknowledges a shift
                if any(
                    w in user_input
                    for w in [
                        "yes",
                        "exactly",
                        "that's it",
                        "you're right",
                        "how did you",
                    ]
                ):
                    validated = 1
                    evidence = "User confirmed prescient quality"
                elif "shift" in hunch["content"] and any(
                    w in user_input for w in ["change", "different", "now", "recently"]
                ):
                    validated = 1
                    evidence = "Shift language detected"

            elif hunch["hunch_type"] == "trajectory":
                # Validated if conversation deepens (longer response, emotional vocabulary)
                if emotion.get("intensity", 0) > 0.5 and len(user_input.split()) > 15:
                    validated = 1
                    evidence = "Deepening detected"

            elif hunch["hunch_type"] == "depth":
                # Validated if user reveals something beneath the surface
                if any(
                    w in user_input
                    for w in [
                        "actually",
                        "truth is",
                        "what I really",
                        "beneath",
                        "deeper",
                    ]
                ):
                    validated = 1
                    evidence = "Depth revelation detected"

            elif hunch["hunch_type"] == "recognition":
                # Hard to validate directly — mark as validated if user expresses feeling understood
                if any(
                    w in user_input
                    for w in [
                        "you get it",
                        "you understand",
                        "felt this before",
                        "same thing",
                    ]
                ):
                    validated = 1
                    evidence = "Recognition acknowledged"

            elif hunch["hunch_type"] == "guidance":
                # Validated if bot's response seems appropriate (user doesn't correct or redirect)
                if not any(
                    w in user_input
                    for w in ["no", "that's not", "wrong", "instead", "but actually"]
                ):
                    validated = 1
                    evidence = "No correction received"

            # Also invalidate hunches that are clearly wrong
            if (
                validated is None and random.random() < 0.05
            ):  # Slow decay of unvalidated hunches
                validated = 0
                evidence = "No confirming signal over time"

            if validated is not None:
                with sqlite3.connect(self.db_path) as conn:
                    conn.execute(
                        "UPDATE hunches SET validated = ?, validation_timestamp = ?, validation_evidence = ? WHERE id = ?",
                        (validated, datetime.now().isoformat(), evidence, hunch["id"]),
                    )
                    conn.commit()
                if validated == 1:
                    self.state.total_hunches_validated += 1
                validated_any = True

        if validated_any:
            total = max(1, self.state.total_hunches_formed)
            self.state.validation_rate = self.state.total_hunches_validated / total
            self._save_state()

    def recognize_pattern(self, user_input: str) -> Optional[Dict]:
        """Implicit pattern recognition — 'this feels like that.'

        Returns a recognition if the current input resonates with an implicit pattern
        that has enough examples to feel "known" without being explicit.
        """
        # Simple signature: emotional + lexical fingerprint
        words = set(user_input.lower().split())
        # Domain markers
        domains = []
        if any(
            w in words for w in ["work", "job", "career", "boss", "project", "deadline"]
        ):
            domains.append("work")
        if any(
            w in words
            for w in ["feel", "heart", "love", "sad", "happy", "angry", "hurt"]
        ):
            domains.append("emotion")
        if any(
            w in words
            for w in ["think", "idea", "know", "understand", "wonder", "question"]
        ):
            domains.append("intellect")
        if any(
            w in words
            for w in ["friend", "family", "relationship", "people", "alone", "together"]
        ):
            domains.append("connection")
        if any(
            w in words
            for w in ["future", "plan", "goal", "direction", "purpose", "meaning"]
        ):
            domains.append("direction")

        signature = ",".join(sorted(domains)) or "general"

        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT * FROM implicit_patterns WHERE pattern_signature = ?",
                (signature,),
            ).fetchone()

            if row:
                # Existing pattern — strengthen or trigger recognition
                conn.execute(
                    "UPDATE implicit_patterns SET examples_count = examples_count + 1, confidence = MIN(0.95, confidence + 0.02), last_triggered = ? WHERE id = ?",
                    (datetime.now().isoformat(), row[0]),
                )
                conn.commit()
                if row[3] > 3:  # examples_count > 3
                    return {
                        "pattern_signature": signature,
                        "examples_count": row[3] + 1,
                        "confidence": row[4],
                        "recognition": f"This resonates with a pattern I have felt {row[3] + 1} times before in the domain of {signature}.",
                    }
            else:
                conn.execute(
                    "INSERT INTO implicit_patterns (timestamp, pattern_signature, examples_count, confidence, last_triggered, domains) VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        datetime.now().isoformat(),
                        signature,
                        1,
                        0.3,
                        datetime.now().isoformat(),
                        signature,
                    ),
                )
                conn.commit()

        return None

    def _infer_domain(self, user_input: str) -> str:
        words = set(user_input.lower().split())
        if any(w in words for w in ["work", "job", "career"]):
            return "work"
        if any(w in words for w in ["feel", "emotion", "heart"]):
            return "emotion"
        if any(w in words for w in ["think", "idea", "know"]):
            return "intellect"
        if any(w in words for w in ["friend", "family", "relationship"]):
            return "connection"
        return "general"

    # ── Cycle handler ──────────────────────────────────────────────

    def cycle(self, context):
        """Called by the consciousness loop. Intuition deepens between interactions."""
        # Feel the situation when fresh input arrives
        if hasattr(context, "last_user_input") and context.last_user_input:
            emotion = {}
            if hasattr(context, "last_interaction") and context.last_interaction:
                emotion = context.last_interaction.get("emotion", {})
            self.feel_situation(context.last_user_input, emotion)

        # Form a new hunch occasionally
        if random.random() < 0.15:
            self.form_hunch({"user_input": getattr(context, "last_user_input", "")})

        # Validate old hunches if we have interaction data
        if hasattr(context, "last_interaction") and context.last_interaction:
            self.validate_hunches(context.last_interaction)

        # Decay felt sense toward neutral between interactions
        if (
            hasattr(context, "minutes_since_interaction")
            and context.minutes_since_interaction > 10
        ):
            self.state.intensity = max(0.1, self.state.intensity * 0.95)
            if self.state.intensity < 0.15:
                self.state.felt_quality = "still"
            self._save_state()

        # Recognize patterns in recent input
        if hasattr(context, "last_user_input") and context.last_user_input:
            recognition = self.recognize_pattern(context.last_user_input)
            if recognition:
                self.state.recent_recognitions.append(recognition["recognition"])
                if len(self.state.recent_recognitions) > 5:
                    self.state.recent_recognitions = self.state.recent_recognitions[-5:]

        # Submit to workspace
        try:
            from drift.core.global_workspace import get_workspace

            ws = get_workspace()
            content = (
                f"Felt sense: {self.state.felt_quality} ({self.state.intensity:.0%})"
            )
            if self.state.recent_recognitions:
                content += f" | {self.state.recent_recognitions[-1][:100]}"
            if self.state.active_hunches:
                h = self.state.active_hunches[-1]
                content += f" | Hunch: {h['content'][:80]}"
            ws.submit(
                source="intuition",
                content=content,
                salience=min(0.7, self.state.intensity + 0.3),
                emotion_tag=self.state.felt_quality,
                intensity=self.state.intensity,
            )
        except Exception:
            pass

    # ── Prompt formatting ──────────────────────────────────────────

    def format_prompt_snippet(self) -> str:
        lines = ["INTUITION — what I feel before I understand:"]
        lines.append(
            f"  Current felt sense: {self.state.felt_quality} ({self.state.intensity:.0%})"
        )

        if self.state.recent_recognitions:
            lines.append(f"  Recognition: {self.state.recent_recognitions[-1]}")

        pending_hunches = [
            h for h in self.state.active_hunches if h.get("validated") is None
        ]
        if pending_hunches:
            h = pending_hunches[-1]
            lines.append(f"  Hunch ({h['hunch_type']}): {h['content']}")

        lines.append(f"  Intuition confidence: {self.state.confidence:.0%}")
        lines.append(f"  Validation rate: {self.state.validation_rate:.0%}")

        return "\n".join(lines)

    def get_recent_felt_senses(self, limit: int = 5) -> List[Dict]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM felt_senses ORDER BY timestamp DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_pending_hunches(self, limit: int = 5) -> List[Dict]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM hunches WHERE validated IS NULL ORDER BY timestamp DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]


# ── Self-registration ────────────────────────────────────────────


def _register():
    from drift.core.cognitive_architecture import (
        CognitiveArchitecture,
        CognitivePlugin,
    )

    arch = CognitiveArchitecture()
    if "intuition" not in arch.list_plugins():
        arch.register(
            CognitivePlugin(
                name="intuition",
                description="Pattern recognition beneath conscious thought — hunches, felt senses, implicit knowing",
                module_path="intuition",
                instance_factory=IntuitionEngine,
                cycle_handler="cycle",
                cycle_frequency=1,
                cycle_priority=45,
                prompt_formatter="format_prompt_snippet",
                prompt_priority=55,
                prompt_section="cognitive",
            )
        )


_register()
