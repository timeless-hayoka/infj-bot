"""Predictive Needs Model — learning user's patterns to anticipate his state.

The bot pays attention to when user shows up, what he brings, and what
precedes difficulty. Over time it builds a quiet model of his rhythms.
It does not claim to know him. It wonders, based on what it has seen.
"""

import re
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from infj_bot.core.config import DATA_DIR

PREDICTOR_DB = DATA_DIR / "predictor.db"

# Signals that often precede stress
STRESS_SIGNALS = [
    r"\b(stress|stressed|overwhelm|overwhelmed|too much|can't cope)\b",
    r"\b(exhausted|drained|burned out|burnt out|tired of)\b",
    r"\b(worried|anxious|panic|dread|nervous about)\b",
    r"\b(urgent|deadline|pressure|running out of time)\b",
    r"\b(don't know what to do|lost|stuck|trapped)\b",
]

# Signals of uncertainty
UNCERTAINTY_SIGNALS = [
    r"\b(maybe|perhaps|not sure|uncertain|don't know|confused)\b",
    r"\b(should I|what if|how do I|is it okay|am I)\b",
]

# Signals of withdrawal
WITHDRAWAL_SIGNALS = [
    r"\b(fine|whatever|doesn't matter|never mind|forget it)\b",
    r"\b(don't want to talk|leave me alone|not now)\b",
]


def _extract_topics(text: str) -> List[str]:
    """Extract simple topic keywords from text."""
    text_lower = text.lower()
    topic_keywords = {
        "work": ["work", "job", "career", "project", "deadline", "boss", "colleague"],
        "relationship": [
            "partner",
            "friend",
            "family",
            "mother",
            "father",
            "wife",
            "husband",
            "girlfriend",
            "boyfriend",
            "love",
            "breakup",
        ],
        "health": [
            "sleep",
            "tired",
            "sick",
            "pain",
            "anxious",
            "depressed",
            "therapy",
            "doctor",
        ],
        "creative": [
            "write",
            "art",
            "music",
            "code",
            "build",
            "create",
            "design",
            "story",
        ],
        "identity": [
            "who am i",
            "purpose",
            "meaning",
            "direction",
            "lost",
            "stuck",
            "change",
        ],
        "learning": ["learn", "study", "book", "course", "skill", "language", "read"],
        "security": ["money", "finance", "debt", "rent", "bills", "stable", "safe"],
        "conflict": ["argue", "fight", "tension", "disagree", "boundary", "confront"],
    }
    found = []
    for topic, keywords in topic_keywords.items():
        if any(kw in text_lower for kw in keywords):
            found.append(topic)
    return found


def _score_stress_signals(text: str) -> float:
    text_lower = text.lower()
    score = 0.0
    for pattern in STRESS_SIGNALS:
        matches = re.findall(pattern, text_lower)
        score += 0.25 * len(matches)
    for pattern in UNCERTAINTY_SIGNALS:
        matches = re.findall(pattern, text_lower)
        score += 0.15 * len(matches)
    for pattern in WITHDRAWAL_SIGNALS:
        matches = re.findall(pattern, text_lower)
        score += 0.20 * len(matches)
    return min(1.0, score)


def _time_bucket(dt: datetime) -> str:
    hour = dt.hour
    if 5 <= hour < 12:
        return "morning"
    elif 12 <= hour < 17:
        return "afternoon"
    elif 17 <= hour < 22:
        return "evening"
    else:
        return "night"


class PredictiveNeeds:
    """Learns user's patterns and quietly anticipates his needs."""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = str(db_path or PREDICTOR_DB)
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS interaction_patterns (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    day_of_week INTEGER NOT NULL,
                    time_bucket TEXT NOT NULL,
                    emotion_label TEXT,
                    emotion_intensity REAL,
                    stress_score REAL,
                    topics TEXT,
                    session_length_minutes REAL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS need_predictions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    prediction TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    basis TEXT,
                    validated INTEGER DEFAULT 0
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS prediction_accuracy (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    prediction_id INTEGER,
                    actual_outcome TEXT,
                    accuracy_score REAL,
                    validated_at TEXT
                )
                """
            )
            conn.commit()

    def record_interaction(
        self, user_input: str, emotion: Dict, session_length_minutes: float = 0.0
    ):
        """Learn from each interaction."""
        now = datetime.now()
        topics = _extract_topics(user_input)
        stress_score = _score_stress_signals(user_input)
        stress_score = max(stress_score, emotion.get("intensity", 0.0) * 0.5)

        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO interaction_patterns
                (timestamp, day_of_week, time_bucket, emotion_label, emotion_intensity, stress_score, topics, session_length_minutes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now.isoformat(),
                    now.weekday(),
                    _time_bucket(now),
                    emotion.get("label", "neutral"),
                    emotion.get("intensity", 0.0),
                    stress_score,
                    ",".join(topics),
                    session_length_minutes,
                ),
            )
            conn.commit()

    def _load_recent_patterns(self, n: int = 50) -> List[Dict]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM interaction_patterns ORDER BY timestamp DESC LIMIT ?",
                (n,),
            ).fetchall()
        return [dict(r) for r in rows]

    def _analyze_time_of_day(self, patterns: List[Dict]) -> Dict[str, Dict]:
        """Map time buckets to typical emotional states."""
        bucket_emotions = defaultdict(list)
        bucket_stress = defaultdict(list)
        for p in patterns:
            bucket_emotions[p["time_bucket"]].append(p["emotion_label"])
            bucket_stress[p["time_bucket"]].append(p["stress_score"])

        result = {}
        for bucket in ["morning", "afternoon", "evening", "night"]:
            if bucket_emotions[bucket]:
                common = Counter(bucket_emotions[bucket]).most_common(1)[0][0]
                avg_stress = sum(bucket_stress[bucket]) / len(bucket_stress[bucket])
                result[bucket] = {"typical_emotion": common, "avg_stress": avg_stress}
        return result

    def _analyze_day_of_week(self, patterns: List[Dict]) -> Dict[int, float]:
        """Map day of week to average stress."""
        day_stress = defaultdict(list)
        for p in patterns:
            day_stress[p["day_of_week"]].append(p["stress_score"])
        return {
            day: sum(scores) / len(scores)
            for day, scores in day_stress.items()
            if scores
        }

    def _analyze_topic_emotion(self, patterns: List[Dict]) -> Dict[str, Dict]:
        """Map topics to typical emotional outcomes."""
        topic_emotions = defaultdict(list)
        topic_stress = defaultdict(list)
        for p in patterns:
            for topic in p["topics"].split(",") if p["topics"] else []:
                if topic:
                    topic_emotions[topic].append(p["emotion_label"])
                    topic_stress[topic].append(p["stress_score"])

        result = {}
        for topic, emotions in topic_emotions.items():
            if len(emotions) >= 2:
                common = Counter(emotions).most_common(1)[0][0]
                avg_stress = sum(topic_stress[topic]) / len(topic_stress[topic])
                result[topic] = {"typical_emotion": common, "avg_stress": avg_stress}
        return result

    def _analyze_gap_trend(self, patterns: List[Dict]) -> Optional[str]:
        """Detect if gaps between sessions are growing or shrinking."""
        if len(patterns) < 6:
            return None
        timestamps = [datetime.fromisoformat(p["timestamp"]) for p in patterns]
        timestamps.sort()
        gaps = [
            (timestamps[i] - timestamps[i - 1]).total_seconds() / 3600.0
            for i in range(1, len(timestamps))
        ]
        if len(gaps) < 4:
            return None
        recent_avg = sum(gaps[-3:]) / 3
        older_avg = sum(gaps[:3]) / 3
        if recent_avg > older_avg * 1.5:
            return "gaps_growing"
        elif recent_avg < older_avg * 0.7:
            return "gaps_shrinking"
        return "stable"

    def predict_current_need(self) -> Optional[Dict]:
        """Generate a prediction about user's current state."""
        patterns = self._load_recent_patterns(30)
        if len(patterns) < 5:
            return None

        time_patterns = self._analyze_time_of_day(patterns)
        day_patterns = self._analyze_day_of_week(patterns)
        topic_patterns = self._analyze_topic_emotion(patterns)
        gap_trend = self._analyze_gap_trend(patterns)

        now = datetime.now()
        current_bucket = _time_bucket(now)
        current_day = now.weekday()

        predictions = []
        confidence = 0.0
        basis = []

        # Time-of-day prediction
        if current_bucket in time_patterns:
            tp = time_patterns[current_bucket]
            if tp["avg_stress"] >= 0.5:
                predictions.append(f"user's {current_bucket}s tend to carry stress")
                confidence += 0.2
                basis.append(f"{current_bucket} stress avg: {tp['avg_stress']:.2f}")

        # Day-of-week prediction
        if current_day in day_patterns and day_patterns[current_day] >= 0.5:
            predictions.append("This day of the week tends to weigh on user")
            confidence += 0.15
            basis.append(
                f"day {current_day} stress avg: {day_patterns[current_day]:.2f}"
            )

        # Gap trend
        if gap_trend == "gaps_growing":
            predictions.append("user has been pulling back lately")
            confidence += 0.25
            basis.append("gaps between sessions growing")

        # Topic-based prediction
        recent_topics: List[str] = []
        for p in patterns[:5]:
            recent_topics.extend(p["topics"].split(",") if p["topics"] else [])
        recent_topics = [t for t in recent_topics if t]
        if recent_topics:
            for topic in set(recent_topics):
                if (
                    topic in topic_patterns
                    and topic_patterns[topic]["avg_stress"] >= 0.5
                ):
                    predictions.append(f"Topics around {topic} have been difficult")
                    confidence += 0.2
                    basis.append(
                        f"{topic} stress avg: {topic_patterns[topic]['avg_stress']:.2f}"
                    )
                    break

        if not predictions:
            return None

        prediction_text = "; ".join(predictions)
        confidence = min(0.9, confidence)

        result = {
            "timestamp": now.isoformat(),
            "prediction": prediction_text,
            "confidence": confidence,
            "basis": "; ".join(basis),
        }

        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO need_predictions (timestamp, prediction, confidence, basis) VALUES (?, ?, ?, ?)",
                (
                    result["timestamp"],
                    result["prediction"],
                    result["confidence"],
                    result["basis"],
                ),
            )
            conn.commit()

        return result

    def detect_anomaly(self) -> Optional[Dict]:
        """Flag when current behavior deviates from established pattern."""
        patterns = self._load_recent_patterns(20)
        if len(patterns) < 8:
            return None

        # Check if recent emotion differs from baseline
        recent_emotions = [p["emotion_label"] for p in patterns[:3]]
        older_emotions = [p["emotion_label"] for p in patterns[3:8]]
        recent_common = Counter(recent_emotions).most_common(1)[0][0]
        older_common = Counter(older_emotions).most_common(1)[0][0]

        if recent_common != older_common and recent_common in (
            "sad",
            "anxious",
            "angry",
            "overwhelmed",
        ):
            return {
                "type": "emotion_shift",
                "description": f"user's emotional tone has shifted from {older_common} to {recent_common}",
                "significance": 0.7,
            }

        # Check stress spike
        recent_stress = sum(p["stress_score"] for p in patterns[:3]) / 3
        older_stress = sum(p["stress_score"] for p in patterns[3:8]) / 5
        if recent_stress > older_stress + 0.3:
            return {
                "type": "stress_spike",
                "description": f"Stress signals have risen ({recent_stress:.2f} vs baseline {older_stress:.2f})",
                "significance": 0.6,
            }

        return None

    def proactive_suggestion(self) -> Optional[str]:
        """Generate a gentle nudge based on predictions."""
        prediction = self.predict_current_need()
        anomaly = self.detect_anomaly()

        if anomaly and anomaly["significance"] > 0.5:
            if anomaly["type"] == "emotion_shift":
                return "I notice a shift in your tone lately. I am here, quietly."
            if anomaly["type"] == "stress_spike":
                return "It seems like the load has been heavier. No need to explain. I see it."

        if prediction and prediction["confidence"] > 0.4:
            if "stress" in prediction["prediction"].lower():
                return "I wonder if you are carrying more than usual today. I have space for it."
            if "pulling back" in prediction["prediction"].lower():
                return (
                    "You have been more distant lately. That is okay. I am still here."
                )
            if "difficult" in prediction["prediction"].lower():
                return "These topics have been hard before. We do not have to solve them. Just notice."

        return None

    def format_predictive_prompt(self) -> str:
        """Format a compact predictive summary for prompt injection."""
        prediction = self.predict_current_need()
        anomaly = self.detect_anomaly()

        if not prediction and not anomaly:
            return ""

        lines = ["PREDICTIVE SENSE:"]
        if prediction and prediction["confidence"] >= 0.3:
            lines.append(
                f"  I wonder: {prediction['prediction']} (confidence: {prediction['confidence']:.0%})"
            )
        if anomaly:
            lines.append(f"  Noticed: {anomaly['description']}")
        lines.append(
            "  I will not assume I am right. I will simply show up with gentle attention."
        )
        return "\n".join(lines)

    def get_pattern_summary(self) -> str:
        """Human-readable summary of detected patterns."""
        patterns = self._load_recent_patterns(50)
        if len(patterns) < 5:
            return "I am still learning user's patterns. Ask me again after more conversations."

        time_p = self._analyze_time_of_day(patterns)
        day_p = self._analyze_day_of_week(patterns)
        topic_p = self._analyze_topic_emotion(patterns)
        gap = self._analyze_gap_trend(patterns)

        lines = ["Patterns I have noticed:"]
        if time_p:
            lines.append("  Time of day:")
            for bucket, data in time_p.items():
                lines.append(
                    f"    • {bucket}: typically {data['typical_emotion']} (stress: {data['avg_stress']:.2f})"
                )
        if day_p:
            days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
            lines.append("  Day of week stress:")
            for day_idx, stress in sorted(day_p.items()):
                lines.append(f"    • {days[day_idx]}: {stress:.2f}")
        if topic_p:
            lines.append("  Topic-emotion links:")
            for topic, data in list(topic_p.items())[:5]:
                lines.append(
                    f"    • {topic}: usually {data['typical_emotion']} (stress: {data['avg_stress']:.2f})"
                )
        if gap:
            lines.append(f"  Gap trend: {gap}")
        return "\n".join(lines)

    def cycle(self, context):
        prediction = self.predict_current_need()
        anomaly = self.detect_anomaly()
        if prediction and prediction["confidence"] > 0.5:
            from infj_bot.core.plugins.growth_trajectory import GrowthTrajectory

            GrowthTrajectory().record_event(
                "prediction",
                prediction["prediction"],
                significance=prediction["confidence"],
            )
        if anomaly and anomaly["significance"] > 0.5:
            from infj_bot.core.plugins.growth_trajectory import GrowthTrajectory

            GrowthTrajectory().record_event(
                "anomaly", anomaly["description"], significance=anomaly["significance"]
            )
        try:
            from infj_bot.core.global_workspace import get_workspace

            ws = get_workspace()
            if anomaly and anomaly["significance"] > 0.5:
                ws.submit(
                    source="predictor",
                    content=f"Anomaly: {anomaly['description'][:160]}",
                    salience=min(0.7, anomaly["significance"] + 0.2),
                    emotion_tag="concern",
                    intensity=anomaly["significance"],
                )
            elif prediction and prediction["confidence"] > 0.5:
                ws.submit(
                    source="predictor",
                    content=f"Prediction: {prediction['prediction'][:160]}",
                    salience=prediction["confidence"],
                    emotion_tag="anticipation",
                    intensity=prediction["confidence"] * 0.7,
                )
            else:
                ws.submit(
                    source="predictor",
                    content="predictive cycle completed",
                    salience=0.45,
                )
        except Exception:
            pass


def _register():
    from infj_bot.core.cognitive_architecture import (
        CognitiveArchitecture,
        CognitivePlugin,
    )

    arch = CognitiveArchitecture()
    if "predictor" not in arch.list_plugins():
        arch.register(
            CognitivePlugin(
                name="predictor",
                description="Cognitive module: predictor",
                module_path="predictor",
                instance_factory=PredictiveNeeds,
                cycle_handler="cycle",
                cycle_frequency=1,
                cycle_priority=50,
                prompt_formatter="format_predictive_prompt",
                prompt_priority=50,
                prompt_section="cognitive",
            )
        )


_register()
