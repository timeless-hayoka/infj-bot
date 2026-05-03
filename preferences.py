"""Persistent user preferences for the INFJ companion bot.

Stores structured preferences in SQLite and injects them into prompts
so the bot remembers how Jude likes to communicate, what matters to
him, and what to avoid.
"""
import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

from config import PROJECT_ROOT

PREFS_DB = PROJECT_ROOT / "preferences.db"

DEFAULT_PREFS = {
    "communication_style": "warm and analytical",  # casual, formal, technical, warm, direct
    "response_length": "medium",  # short, medium, long
    "interests": [],  # list of topics Jude cares about
    "avoid_topics": [],  # list of topics to steer away from
    "preferred_tools": [],  # tools Jude uses most
    "proactive_frequency": "normal",  # low, normal, high
    "corrections": [],  # list of past corrections Jude gave
    "known_facts": {},  # durable facts about Jude (timezone, profession, etc.)
}


class PreferenceStore:
    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = str(db_path or PREFS_DB)
        self._init_db()
        self._ensure_defaults()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS preferences (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.commit()

    def _ensure_defaults(self):
        for key, value in DEFAULT_PREFS.items():
            if self.get(key) is None:
                self.set(key, value)

    def get(self, key: str) -> Any:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT value FROM preferences WHERE key = ?", (key,)
            ).fetchone()
        if row is None:
            return None
        try:
            return json.loads(row[0])
        except json.JSONDecodeError:
            return row[0]

    def set(self, key: str, value: Any) -> None:
        from datetime import datetime
        json_value = json.dumps(value, ensure_ascii=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO preferences (key, value, updated_at) VALUES (?, ?, ?)",
                (key, json_value, datetime.now().isoformat()),
            )
            conn.commit()

    def delete(self, key: str) -> bool:
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.execute("DELETE FROM preferences WHERE key = ?", (key,))
            conn.commit()
            return cur.rowcount > 0

    def all(self) -> Dict[str, Any]:
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute("SELECT key, value FROM preferences").fetchall()
        result = {}
        for key, value in rows:
            try:
                result[key] = json.loads(value)
            except json.JSONDecodeError:
                result[key] = value
        return result

    def add_to_list(self, key: str, item: str) -> None:
        current = self.get(key) or []
        if not isinstance(current, list):
            current = [current]
        if item not in current:
            current.append(item)
            self.set(key, current)

    def remove_from_list(self, key: str, item: str) -> None:
        current = self.get(key) or []
        if not isinstance(current, list):
            return
        if item in current:
            current.remove(item)
            self.set(key, current)

    def add_correction(self, correction: str) -> None:
        """Record a correction from the user so the bot can learn."""
        current = self.get("corrections") or []
        current.append(correction)
        # Keep last 20 corrections
        self.set("corrections", current[-20:])

    def add_known_fact(self, fact_key: str, fact_value: str) -> None:
        """Record a durable fact about the user."""
        facts = self.get("known_facts") or {}
        facts[fact_key] = fact_value
        self.set("known_facts", facts)

    def format_prompt_snippet(self) -> str:
        """Format preferences into a short snippet for the system prompt."""
        prefs = self.all()
        lines = ["USER PREFERENCES:"]
        style = prefs.get("communication_style", "warm and analytical")
        length = prefs.get("response_length", "medium")
        lines.append(f"- Communication style: {style}")
        lines.append(f"- Preferred response length: {length}")

        interests = prefs.get("interests", [])
        if interests:
            lines.append(f"- Known interests: {', '.join(interests)}")

        avoid = prefs.get("avoid_topics", [])
        if avoid:
            lines.append(f"- Topics to avoid: {', '.join(avoid)}")

        facts = prefs.get("known_facts", {})
        if facts:
            lines.append(f"- Known facts: {', '.join(f'{k}={v}' for k, v in facts.items())}")

        corrections = prefs.get("corrections", [])
        if corrections:
            lines.append(f"- Recent corrections ({len(corrections)}):")
            for c in corrections[-5:]:
                lines.append(f"  • {c}")

        return "\n".join(lines)

    def suggest_from_memory(self, memory_text: str) -> List[str]:
        """Heuristic suggestions for new preferences based on memory text."""
        suggestions = []
        lowered = memory_text.lower()
        # Simple keyword heuristics
        if any(w in lowered for w in ["hate", "don't like", "annoying", "frustrating"]):
            suggestions.append("Consider adding an avoid_topic based on negative sentiment.")
        if any(w in lowered for w in ["love", "passionate about", "obsessed with", "favorite"]):
            suggestions.append("Consider adding an interest based on positive sentiment.")
        if "too long" in lowered or "shorter" in lowered:
            suggestions.append("User prefers shorter responses; set response_length to 'short'.")
        if "too brief" in lowered or "more detail" in lowered:
            suggestions.append("User prefers detailed responses; set response_length to 'long'.")
        return suggestions
