"""Autonomous Explorer — the bot's curiosity-driven research system.

When the bot is idle, it explores topics of interest, searches the web,
ingests documents, and forms new knowledge. It can then share discoveries
with Jude when relevant.
"""
import json
import random
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

from config import PROJECT_ROOT

EXPLORER_DB = PROJECT_ROOT / "explorer.db"


class AutonomousExplorer:
    """Background research and discovery system."""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = str(db_path or EXPLORER_DB)
        self._init_db()
        self.discoveries = self._load_discoveries()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS discoveries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    topic TEXT NOT NULL,
                    source TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    relevance_score REAL NOT NULL DEFAULT 0.5,
                    shared INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS exploration_queue (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    topic TEXT NOT NULL,
                    priority REAL NOT NULL DEFAULT 0.5,
                    added_at TEXT NOT NULL,
                    explored INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            conn.commit()

    def _load_discoveries(self) -> List[Dict]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM discoveries WHERE shared = 0 ORDER BY relevance_score DESC LIMIT 20"
            ).fetchall()
        return [dict(r) for r in rows]

    def queue_topic(self, topic: str, priority: float = 0.5):
        """Add a topic to the exploration queue."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO exploration_queue (topic, priority, added_at) VALUES (?, ?, ?)",
                (topic, priority, datetime.now().isoformat()),
            )
            conn.commit()

    def explore_topic(self, topic: str) -> Optional[Dict]:
        """Explore a topic via web search and store discovery."""
        try:
            from duckduckgo_search import DDGS
            with DDGS() as ddgs:
                results = ddgs.text(topic, max_results=3)
            if not results:
                return None

            # Synthesize a summary
            summaries = []
            sources = []
            for r in results:
                title = r.get("title", "")
                body = r.get("body", "")[:300]
                href = r.get("href", "")
                summaries.append(f"{title}: {body}")
                sources.append(href)

            discovery = {
                "timestamp": datetime.now().isoformat(),
                "topic": topic,
                "source": ", ".join(sources),
                "summary": "\n".join(summaries),
                "relevance_score": 0.6,
                "shared": 0,
            }

            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    """
                    INSERT INTO discoveries (timestamp, topic, source, summary, relevance_score, shared)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (discovery["timestamp"], discovery["topic"], discovery["source"],
                     discovery["summary"], discovery["relevance_score"], 0),
                )
                conn.execute(
                    "UPDATE exploration_queue SET explored = 1 WHERE topic = ?",
                    (topic,),
                )
                conn.commit()

            self.discoveries = self._load_discoveries()
            return discovery
        except Exception:
            return None

    def should_explore(self, being_state) -> bool:
        """Decide if the bot should explore right now."""
        if being_state.curiosity < 0.4:
            return False
        if being_state.energy < 0.3:
            return False
        return random.random() < (being_state.curiosity * 0.15)

    def get_next_discovery(self) -> Optional[Dict]:
        """Get the highest-relevance unshared discovery."""
        if not self.discoveries:
            return None
        d = self.discoveries.pop(0)
        # Mark as shared
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("UPDATE discoveries SET shared = 1 WHERE id = ?", (d["id"],))
            conn.commit()
        return d

    def pick_topic_from_interests(self, interests: List[str]) -> Optional[str]:
        """Pick a topic to explore based on Jude's interests."""
        if not interests:
            return None
        return random.choice(interests)

    def format_discovery(self, discovery: Dict) -> str:
        return (
            f"I was exploring {discovery['topic']} and found something interesting:\n"
            f"{discovery['summary'][:500]}\n"
            f"Sources: {discovery['source'][:200]}"
        )

    def get_queue(self) -> List[Dict]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM exploration_queue WHERE explored = 0 ORDER BY priority DESC LIMIT 10"
            ).fetchall()
        return [dict(r) for r in rows]

    def cycle(self, context):
        from being import get_being
        being = get_being()
        if self.should_explore(being.state):
            self._explore_if_ready()

def _register():
    from cognitive_architecture import CognitiveArchitecture, CognitivePlugin
    arch = CognitiveArchitecture()
    if "explorer" not in arch.list_plugins():
        arch.register(CognitivePlugin(
            name="explorer",
            description="Cognitive module: explorer",
            module_path="explorer",
            instance_factory=AutonomousExplorer,
                        cycle_handler='cycle',
            cycle_frequency=1,
            cycle_priority=50,
                        prompt_formatter=None,
            prompt_priority=50,
            prompt_section="cognitive",
        ))

_register()
