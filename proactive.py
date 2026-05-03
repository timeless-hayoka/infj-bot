"""Smart proactive trigger system for the INFJ companion."""
import random
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from emotion import detect_emotion
from cognition import detect_dissonance


class ProactiveState:
    def __init__(self):
        self.last_user_time: Optional[datetime] = None
        self.last_stress_level: float = 0.0
        self.last_dissonance_score: float = 0.0
        self.proactive_count: int = 0

    def record_interaction(self, user_input: str, emotion: Dict, dissonance: Dict):
        self.last_user_time = datetime.now()
        self.last_stress_level = emotion.get("intensity", 0.0) * (1.0 if emotion.get("label") in ("anxious", "angry", "sad", "overwhelmed") else 0.5)
        self.last_dissonance_score = dissonance.get("score", 0.0)

    def should_trigger(self, goals_db=None) -> Optional[str]:
        """Returns a proactive prompt if a trigger fires, else None."""
        now = datetime.now()

        # Trigger 1: User has been away for a while (15-45 min) and last interaction was stressful
        if self.last_user_time is not None:
            minutes_away = (now - self.last_user_time).total_seconds() / 60.0
            if minutes_away > 20 and self.last_stress_level > 0.6:
                return (
                    "Jude stepped away after a stressful moment. "
                    "Share one gentle, grounding observation or question. "
                    "Do not ask for a status update; just leave a small light on."
                )

        # Trigger 2: Upcoming deadlines (within 4 hours)
        if goals_db is not None:
            try:
                reminders = goals_db.pending_reminders(within_minutes=240)
                if reminders:
                    r = random.choice(reminders)
                    return (
                        f"There is an upcoming reminder: '{r['message']}' at {r['remind_at']}. "
                        f"Offer a brief, helpful nudge. Keep it under two sentences."
                    )
            except Exception:
                pass

        # Trigger 3: Unresolved cognitive dissonance (score > 0.5)
        if self.last_dissonance_score > 0.5:
            return (
                "Earlier Jude showed signs of inner conflict. "
                "Drop one small, non-intrusive question that might help them name one side of the tension. "
                "Do not solve it; just reopen the door gently."
            )

        # Trigger 4: Random philosophical prompt (low probability, only if nothing else fires)
        if random.random() < 0.08:
            prompts = [
                "What is one thing you are quietly proud of but rarely mention?",
                "If your current project could speak, what would it ask for?",
                "What pattern in your own behavior have you noticed but not named?",
                "What is the smallest step that would make tomorrow easier?",
                "What question are you avoiding because the answer might change something?",
            ]
            return f"Share this brief reflective question with Jude: {random.choice(prompts)}"

        return None

    def next_wait_seconds(self) -> int:
        """Dynamic wait based on recent activity."""
        if self.last_stress_level > 0.7:
            return random.randint(180, 400)  # 3-7 min
        if self.last_dissonance_score > 0.5:
            return random.randint(300, 600)  # 5-10 min
        return random.randint(600, 1200)  # 10-20 min
