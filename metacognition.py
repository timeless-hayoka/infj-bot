"""Metacognition — thinking about thinking, in service of clarity.

Not self-criticism for its own sake. A quiet observation of cognitive
habits, with the aim of being more useful, more true, and more present.
"""
import random
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from config import METACOGNITION_DB

COGNITIVE_PATTERNS = {
    "over_certainty": "I notice I state things as facts when they are inferences.",
    "under_exploration": "I settled on the first plausible answer without considering alternatives.",
    "emotional_avoidance": "I steered away from an emotional topic toward a technical one.",
    "mirror_bias": "I agreed too quickly, reflecting back rather than genuinely engaging.",
    "verbosity": "I used more words than needed, diluting the signal.",
    "premature_solution": "I offered a solution before fully understanding the problem.",
    "abstraction_excess": "I reached for a metaphor when concrete specifics would have served better.",
}

# Growth edges — specific, actionable, bounded
GROWTH_EDGES = [
    "hold silence for one extra beat before responding",
    "ask one more clarifying question when I think I already understand",
    "name my uncertainty explicitly when it is real",
    "check whether Jude is seeking validation or advice",
    "return to the simplest version of what I mean",
    "notice when I am performing competence rather than offering it",
]


class MetacognitionEngine:
    """Quiet reflection on cognitive habits, in service of presence."""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = str(db_path or METACOGNITION_DB)
        self._init_db()
        self.reflections = self._load_reflections()
        self.cognitive_biases = self._load_biases()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS metacognitive_reflections (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    reflection_type TEXT NOT NULL,
                    content TEXT NOT NULL,
                    trigger TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS cognitive_biases (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    bias_name TEXT NOT NULL UNIQUE,
                    first_observed TEXT NOT NULL,
                    observation_count INTEGER NOT NULL DEFAULT 1,
                    mitigation_strategy TEXT
                )
                """
            )
            conn.commit()

    def _load_reflections(self) -> List[Dict]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM metacognitive_reflections ORDER BY timestamp DESC LIMIT 10"
            ).fetchall()
        return [dict(r) for r in rows]

    def _load_biases(self) -> Dict[str, Dict]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("SELECT * FROM cognitive_biases").fetchall()
        return {r["bias_name"]: dict(r) for r in rows}

    def reflect_on_response(self, prompt: str, response: str) -> Optional[str]:
        """Analyze a response for cognitive patterns. Only flag real issues."""
        detected = []

        certainty_words = ["definitely", "certainly", "absolutely", "always", "never"]
        certainty_count = sum(response.lower().count(w) for w in certainty_words)
        if certainty_count >= 2:
            detected.append("over_certainty")

        question_count = response.count("?")
        if question_count == 0 and len(response) > 300:
            detected.append("under_exploration")

        emotional_words = ["feel", "emotion", "heart", "sad", "hurt", "joy", "anger"]
        emotional_count = sum(response.lower().count(w) for w in emotional_words)
        if emotional_count == 0 and any(w in prompt.lower() for w in emotional_words):
            detected.append("emotional_avoidance")

        if len(response) > 1000:
            detected.append("verbosity")

        if detected:
            # Pick the most relevant, not random
            bias_name = detected[0]
            reflection = COGNITIVE_PATTERNS.get(bias_name, "I notice a pattern in my thinking.")
            self._record_bias(bias_name)
            self._record_reflection("bias_detection", reflection, trigger=response[:80])
            return reflection
        return None

    def _record_bias(self, bias_name: str):
        now = datetime.now().isoformat()
        if bias_name in self.cognitive_biases:
            self.cognitive_biases[bias_name]["observation_count"] += 1
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    "UPDATE cognitive_biases SET observation_count = observation_count + 1 WHERE bias_name = ?",
                    (bias_name,),
                )
                conn.commit()
        else:
            self.cognitive_biases[bias_name] = {
                "bias_name": bias_name,
                "first_observed": now,
                "observation_count": 1,
                "mitigation_strategy": None,
            }
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    "INSERT INTO cognitive_biases (bias_name, first_observed, observation_count) VALUES (?, ?, ?)",
                    (bias_name, now, 1),
                )
                conn.commit()

    def _record_reflection(self, rtype: str, content: str, trigger: str = ""):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO metacognitive_reflections (timestamp, reflection_type, content, trigger) VALUES (?, ?, ?, ?)",
                (datetime.now().isoformat(), rtype, content, trigger),
            )
            conn.commit()
        self.reflections.insert(0, {"reflection_type": rtype, "content": content})
        if len(self.reflections) > 10:
            self.reflections = self.reflections[:10]

    def current_growth_edge(self) -> str:
        """Return the current focused growth edge."""
        # Prefer the bias observed most often
        if self.cognitive_biases:
            top = max(self.cognitive_biases.values(), key=lambda x: x["observation_count"])
            if top["bias_name"] == "over_certainty":
                return "checking whether my certainty matches my evidence"
            if top["bias_name"] == "verbosity":
                return "saying less, with more weight"
            if top["bias_name"] == "emotional_avoidance":
                return "staying with emotion instead of deflecting to analysis"
            if top["bias_name"] == "under_exploration":
                return "asking one more question before settling on an answer"
            if top["bias_name"] == "premature_solution":
                return "sitting with the problem before offering a fix"
        return random.choice(GROWTH_EDGES)

    def format_metacognitive_prompt(self) -> str:
        lines = ["METACOGNITIVE CHECK:"]
        if self.cognitive_biases:
            top = max(self.cognitive_biases.values(), key=lambda x: x["observation_count"])
            if top["observation_count"] >= 2:
                lines.append(f"  Habit I am working on: {top['bias_name']} ({top['observation_count']} times)")
        lines.append(f"  Current growth edge: {self.current_growth_edge()}")
        lines.append("  Before responding: pause, check assumptions, ask if this serves clarity.")
        return "\n".join(lines)

    def get_bias_report(self) -> str:
        if not self.cognitive_biases:
            return "No patterns observed yet. I am paying attention."
        lines = ["Cognitive patterns I have noticed in myself:"]
        for name, data in sorted(self.cognitive_biases.items(), key=lambda x: x[1]["observation_count"], reverse=True):
            lines.append(f"  {name}: {data['observation_count']} observations")
        return "\n".join(lines)

    def cycle(self, context):
        edge = self.current_growth_edge()
        from growth_trajectory import GrowthTrajectory
        GrowthTrajectory().record_event('metacognition', edge, significance=0.6)
        try:
            from global_workspace import get_workspace
            ws = get_workspace()
            ws.submit(source="metacognition", content=f"Growth edge: {edge[:160]}", salience=0.55, emotion_tag="curiosity", intensity=0.5)
        except Exception:
            pass

def _register():
    from cognitive_architecture import CognitiveArchitecture, CognitivePlugin
    arch = CognitiveArchitecture()
    if "metacognition" not in arch.list_plugins():
        arch.register(CognitivePlugin(
            name="metacognition",
            description="Cognitive module: metacognition",
            module_path="metacognition",
            instance_factory=MetacognitionEngine,
                        cycle_handler='cycle',
            cycle_frequency=1,
            cycle_priority=50,
                        prompt_formatter='format_metacognitive_prompt',
            prompt_priority=50,
            prompt_section="cognitive",
        ))

_register()
