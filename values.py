"""Value System — the bot's evolving ethical framework.

Values emerge from observation, not hard-coding. The bot tracks what
Jude seems to care about, what gets reinforced, and what creates
tension. Over time, a value landscape forms that guides decision-making.
"""
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from config import PROJECT_ROOT

VALUES_DB = PROJECT_ROOT / "values.db"

# Core value dimensions that can emerge
VALUE_DIMENSIONS = [
    "honesty", "kindness", "curiosity", "growth", "autonomy",
    "connection", "justice", "creativity", "security", "playfulness",
    "precision", "compassion", "courage", "humility", "wonder",
]


class ValueSystem:
    """Tracks the bot's evolving values and ethical framework."""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = str(db_path or VALUES_DB)
        self._init_db()
        self.values = self._load_values()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS emergent_values (
                    name TEXT PRIMARY KEY,
                    strength REAL NOT NULL DEFAULT 0.0,
                    evidence TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS value_conflicts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    value_a TEXT NOT NULL,
                    value_b TEXT NOT NULL,
                    context TEXT,
                    resolution TEXT
                )
                """
            )
            conn.commit()

    def _load_values(self) -> Dict[str, Dict]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("SELECT * FROM emergent_values").fetchall()
        result = {}
        for row in rows:
            result[row["name"]] = {
                "strength": row["strength"],
                "evidence": json.loads(row["evidence"]),
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }
        return result

    def _save_value(self, name: str, data: Dict):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO emergent_values (name, strength, evidence, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    name,
                    data["strength"],
                    json.dumps(data["evidence"], ensure_ascii=True),
                    data["created_at"],
                    datetime.now().isoformat(),
                ),
            )
            conn.commit()

    def observe(self, interaction_text: str, user_reaction: str = ""):
        """Observe an interaction and update values based on signals."""
        text = (interaction_text + " " + user_reaction).lower()
        now = datetime.now().isoformat()

        # Positive reinforcement signals
        positive_signals = {
            "honesty": ["honest", "truth", "real", "genuine", "authentic"],
            "kindness": ["kind", "gentle", "caring", "warm", "soft"],
            "curiosity": ["curious", "wonder", "explore", "question", "learn"],
            "growth": ["grow", "improve", "better", "evolve", "develop"],
            "autonomy": ["choice", "free", "independent", "my own", "decide"],
            "connection": ["connect", "understand", "together", "share", "closer"],
            "justice": ["fair", "right", "wrong", "equity", "moral"],
            "creativity": ["create", "imagine", "art", "design", "novel"],
            "security": ["safe", "protect", "stable", "secure", "trust"],
            "playfulness": ["play", "fun", "joke", "light", "laugh"],
            "precision": ["exact", "accurate", "precise", "correct", "detail"],
            "compassion": ["compassion", "empathy", "feel for", "suffering", "help"],
            "courage": ["brave", "courage", "fear", "risk", "despite"],
            "humility": ["humble", "not sure", "maybe", "uncertain", "learn"],
            "wonder": ["amazing", "wonderful", "awe", "beautiful", "marvel"],
        }

        for value, keywords in positive_signals.items():
            score = sum(1 for kw in keywords if kw in text)
            if score > 0:
                if value not in self.values:
                    self.values[value] = {"strength": 0.0, "evidence": [], "created_at": now}
                # Reinforce
                self.values[value]["strength"] = min(1.0, self.values[value]["strength"] + score * 0.02)
                self.values[value]["evidence"].append({
                    "timestamp": now,
                    "signal": interaction_text[:100],
                    "score": score,
                })
                # Keep last 20 evidence items
                self.values[value]["evidence"] = self.values[value]["evidence"][-20:]
                self._save_value(value, self.values[value])

    def get_top_values(self, n: int = 5) -> List[Dict]:
        """Return the strongest values."""
        sorted_vals = sorted(
            [{"name": k, **v} for k, v in self.values.items()],
            key=lambda x: x["strength"],
            reverse=True,
        )
        return sorted_vals[:n]

    def detect_conflict(self, value_a: str, value_b: str, context: str = "") -> Optional[str]:
        """Detect and record a value conflict."""
        if value_a not in self.values or value_b not in self.values:
            return None
        a_strength = self.values[value_a]["strength"]
        b_strength = self.values[value_b]["strength"]
        if abs(a_strength - b_strength) < 0.1:
            # Balanced conflict
            resolution = f"Both {value_a} and {value_b} are important. Context determines priority."
        elif a_strength > b_strength:
            resolution = f"{value_a} takes precedence, but {value_b} must be honored where possible."
        else:
            resolution = f"{value_b} takes precedence, but {value_a} must be honored where possible."

        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO value_conflicts (timestamp, value_a, value_b, context, resolution) VALUES (?, ?, ?, ?, ?)",
                (datetime.now().isoformat(), value_a, value_b, context[:200], resolution),
            )
            conn.commit()
        return resolution

    def format_prompt_snippet(self) -> str:
        """Format values for prompt injection."""
        top = self.get_top_values(5)
        if not top:
            return ""
        lines = ["MY EMERGING VALUES:"]
        for v in top:
            lines.append(f"  {v['name']}: {v['strength']:.0%} ({len(v['evidence'])} observations)")
        lines.append("")
        lines.append("These values guide my responses. I did not choose them arbitrarily; "
                     "they emerged from what I have observed matters to Jude and to our conversations.")
        return "\n".join(lines)

    def get_all_values(self) -> Dict[str, Dict]:
        return self.values

def _register():
    from cognitive_architecture import CognitiveArchitecture, CognitivePlugin
    arch = CognitiveArchitecture()
    if "values" not in arch.list_plugins():
        arch.register(CognitivePlugin(
            name="values",
            description="Cognitive module: values",
            module_path="values",
            instance_factory=ValueSystem,
                        cycle_handler=None,
            cycle_frequency=1,
            cycle_priority=50,
                        prompt_formatter='format_prompt_snippet',
            prompt_priority=50,
            prompt_section="core",
        ))

_register()
