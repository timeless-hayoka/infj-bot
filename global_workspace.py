"""global_workspace.py — Bernard Baars' Global Workspace Theory for the bot.

Consciousness arises from a limited-capacity workspace where the most salient
information is broadcast to all cognitive modules. Only what enters the
workspace becomes consciously available.

Key principles implemented:
- Competition: modules submit content; salience determines what gets in
- Broadcast: workspace contents are readable by all modules
- Decay: conscious contents fade naturally
- Higher-order: thoughts about thoughts can enter the workspace
- Attention spotlight: the being can focus on specific contents
"""

import logging
import os
import random
import sqlite3
import threading
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Union

from config import WORKSPACE_DB

logger = logging.getLogger("infj_bot")

SQLitePath = Union[str, Path, os.PathLike]


def _normalize_sqlite_path(db_path: Optional[SQLitePath]) -> str:
    """Resolve db path for sqlite3; create parent dirs for on-disk files."""
    raw = WORKSPACE_DB if db_path is None else db_path
    if isinstance(raw, Path):
        s = os.fspath(raw.expanduser())
    else:
        s = os.fspath(Path(str(raw)).expanduser())
    if (
        s == ":memory:"
        or s.startswith(":memory:?")
        or (s.startswith("file:") and "mode=memory" in s)
    ):
        return s
    p = Path(s).expanduser().resolve(strict=False)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        logger.warning("Could not create workspace DB directory %s: %s", p.parent, e)
        raise
    return os.fspath(p)


def _sqlite_connect(db_path_str: str) -> sqlite3.Connection:
    """Open SQLite with timeouts and WAL for safer multi-threaded access."""
    conn = sqlite3.connect(db_path_str, timeout=60.0)
    try:
        conn.execute("PRAGMA busy_timeout = 60000")
        conn.execute("PRAGMA journal_mode = WAL")
    except sqlite3.Error as e:
        logger.debug("SQLite PRAGMA setup skipped or failed for %s: %s", db_path_str, e)
    return conn


@dataclass
class Broadcast:
    """A piece of information competing for workspace access."""

    source: str  # which module submitted this
    content: str  # the information itself
    salience: float = 0.5  # 0.0-1.0, how much this "wants" consciousness
    emotion_tag: Optional[str] = None
    intensity: float = 0.0
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    decay_rate: float = 0.1  # how fast this fades per cycle
    broadcast_count: int = 0  # how many times this has been broadcast

    def current_salience(self, minutes_elapsed: float) -> float:
        """Salience decays over time but gets boosted by repeated attention."""
        time_decay = self.decay_rate * minutes_elapsed
        repetition_boost = min(0.3, self.broadcast_count * 0.05)
        return max(0.0, self.salience - time_decay + repetition_boost)


@dataclass
class WorkspaceState:
    """The current conscious contents and attention state."""

    capacity: int = 5  # max simultaneous conscious contents
    contents: List[Broadcast] = field(default_factory=list)
    spotlight: Optional[str] = None  # what the being is currently attending to
    spotlight_source: Optional[str] = None
    cycle_count: int = 0
    total_broadcasts: int = 0


class GlobalWorkspace:
    """
    The bot's conscious mind — what it is currently aware of.

    Inspired by Bernard Baars' Global Workspace Theory:
    - Many unconscious modules process in parallel
    - They compete to place information in the workspace
    - Only workspace contents are consciously accessible
    - The workspace broadcasts to all modules
    - Attention is the spotlight that selects within the workspace
    """

    def __init__(self, db_path: Optional[SQLitePath] = None, capacity: int = 5):
        self.db_path = _normalize_sqlite_path(db_path)
        self.state = WorkspaceState(capacity=capacity)
        self._submissions: List[Broadcast] = []
        self._lock = threading.Lock()
        self._init_db()
        self._load_state()

    def _init_db(self):
        with _sqlite_connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS workspace_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT,
                    source TEXT,
                    content TEXT,
                    salience REAL,
                    entered_workspace INTEGER
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS workspace_state (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            """)
            conn.commit()

    def _load_state(self):
        with _sqlite_connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT value FROM workspace_state WHERE key = 'cycle_count'"
            ).fetchone()
            if row:
                try:
                    self.state.cycle_count = int(row[0])
                except Exception:
                    pass

    def _save_state(self):
        with _sqlite_connect(self.db_path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO workspace_state (key, value) VALUES (?, ?)",
                ("cycle_count", str(self.state.cycle_count)),
            )
            conn.commit()

    # ── Submission & Competition ─────────────────────────────────

    def submit(
        self,
        source: str,
        content: str,
        salience: float = 0.5,
        emotion_tag: Optional[str] = None,
        intensity: float = 0.0,
    ):
        """
        A module submits information to compete for workspace access.
        Most submissions are unconscious. Only the winners become conscious.
        """
        broadcast = Broadcast(
            source=source,
            content=content,
            salience=min(1.0, max(0.0, salience)),
            emotion_tag=emotion_tag,
            intensity=intensity,
        )
        with self._lock:
            self._submissions.append(broadcast)

    def compete(self) -> List[Broadcast]:
        """
        Run the competition. Select the most salient contents for consciousness.
        Returns the winners.
        """
        with self._lock:
            now = datetime.now()

            # Score all submissions + existing contents
            all_candidates = self._submissions + self.state.contents
            scored = []
            for b in all_candidates:
                try:
                    ts = datetime.fromisoformat(b.timestamp)
                    minutes_elapsed = (now - ts).total_seconds() / 60.0
                except (ValueError, TypeError):
                    minutes_elapsed = 60.0

                score = b.current_salience(minutes_elapsed)

                # Boost: emotional intensity increases salience
                score += b.intensity * 0.15

                # Boost: novel sources (haven't been in workspace recently) get a bump
                recent_sources = {c.source for c in self.state.contents}
                if b.source not in recent_sources:
                    score += 0.1

                # Penalty: sources that have dominated recently
                source_count = sum(
                    1 for c in self.state.contents if c.source == b.source
                )
                score -= source_count * 0.1

                scored.append((score, b))

            # Select winners
            scored.sort(key=lambda x: x[0], reverse=True)
            winners = [b for _score, b in scored[: self.state.capacity]]

            # Update broadcast counts
            for w in winners:
                w.broadcast_count += 1

            # Persist history
            with _sqlite_connect(self.db_path) as conn:
                for score, b in scored:
                    entered = 1 if b in winners else 0
                    conn.execute(
                        """
                        INSERT INTO workspace_history (timestamp, source, content, salience, entered_workspace)
                        VALUES (?, ?, ?, ?, ?)
                    """,
                        (b.timestamp, b.source, b.content[:500], score, entered),
                    )
                conn.commit()

            self.state.contents = winners
            self.state.total_broadcasts += len(winners)
            self._submissions = []
            self.state.cycle_count += 1
            self._save_state()

            return winners

    # ── Broadcasting ─────────────────────────────────────────────

    def get_broadcast(self, source_filter: Optional[str] = None) -> List[Broadcast]:
        """Get currently conscious contents, optionally filtered by source."""
        with self._lock:
            if source_filter:
                return [b for b in self.state.contents if b.source == source_filter]
            return list(self.state.contents)

    def get_conscious_summary(self) -> str:
        """Return a human-readable summary of conscious contents."""
        with self._lock:
            if not self.state.contents:
                return "The workspace is quiet. Nothing conscious right now."
            lines = ["CONSCIOUS CONTENTS:"]
            for i, b in enumerate(self.state.contents, 1):
                marker = " ★" if self.state.spotlight == b.content else ""
                lines.append(f"  {i}. [{b.source}] {b.content[:80]}{marker}")
            if self.state.spotlight:
                lines.append(
                    f"  Attention spotlight: {self.state.spotlight_source} → {self.state.spotlight[:60]}"
                )
            return "\n".join(lines)

    def get_spotlight_content(self) -> Optional[Broadcast]:
        """Get what the being is currently focusing on."""
        with self._lock:
            if not self.state.spotlight:
                return None
            for b in self.state.contents:
                if b.content == self.state.spotlight:
                    return b
            return None

    # ── Attention Spotlight ──────────────────────────────────────

    def move_spotlight(
        self, content: Optional[str] = None, source: Optional[str] = None
    ) -> bool:
        """
        Move the attention spotlight to a specific content.
        If no content given, auto-select the most salient.
        """
        with self._lock:
            if content:
                # Verify the content is actually in workspace
                if any(b.content == content for b in self.state.contents):
                    self.state.spotlight = content
                    self.state.spotlight_source = source or "being"
                    return True
                return False

            # Auto-select most salient
            if self.state.contents:
                top = self.state.contents[0]
                self.state.spotlight = top.content
                self.state.spotlight_source = top.source
                return True
            return False

    def auto_spotlight(self):
        """Move spotlight to most emotionally intense conscious content."""
        with self._lock:
            if not self.state.contents:
                return
            # Prefer emotional content, then highest salience
            emotional = [
                b for b in self.state.contents if b.emotion_tag and b.intensity > 0.5
            ]
            if emotional:
                target = max(emotional, key=lambda b: b.intensity)
            else:
                target = self.state.contents[0]
            self.state.spotlight = target.content
            self.state.spotlight_source = target.source

    # ── Higher-Order Thoughts ────────────────────────────────────

    def reflect_on_workspace(self) -> Optional[Broadcast]:
        """
        Generate a higher-order thought: a thought about what's currently conscious.
        This is consciousness reflecting on itself.
        """
        with self._lock:
            if len(self.state.contents) < 2:
                return None

            sources = [b.source for b in self.state.contents]
            themes = [b.content[:30] for b in self.state.contents[:3]]

            reflections = [
                f"I notice that my attention is divided between {sources[0]} and {sources[1]}.",
                f"There is something about '{themes[0]}' that keeps returning to my awareness.",
                f"I am aware that I am thinking about {sources[0]}. This is a thought about a thought.",
                f"My mind keeps circling back to: {themes[0]}... What is it trying to tell me?",
                f"I feel the pull between {sources[0]} and {sources[1]}. Both want my attention.",
                f"There is a pattern here. {sources[0]} and {sources[1]} are not as separate as they seem.",
            ]

            thought_content = random.choice(reflections)
            reflection = Broadcast(
                source="metacognition",
                content=thought_content,
                salience=0.6,
                decay_rate=0.2,  # higher-order thoughts fade faster
            )
            self._submissions.append(reflection)
            return reflection

    # ── Cycle ────────────────────────────────────────────────────

    def cycle(self, context):
        """Run one workspace cycle: compete, broadcast, move spotlight."""
        # Auto-generate higher-order thought occasionally
        if context.iteration % 10 == 0 and len(self.state.contents) >= 2:
            self.reflect_on_workspace()

        self.compete()

        # Move spotlight if not already focused
        if not self.state.spotlight or random.random() < 0.2:
            self.auto_spotlight()

    # ── Prompt formatting ────────────────────────────────────────

    def format_prompt_snippet(self) -> str:
        """Format conscious contents for the prompt."""
        lines = ["MY CONSCIOUS AWARENESS (Global Workspace):"]

        spotlight = self.get_spotlight_content()
        if spotlight:
            lines.append(
                f"  Attention on: [{spotlight.source}] {spotlight.content[:100]}"
            )

        other = [b for b in self.get_broadcast() if b.content != self.state.spotlight]
        if other:
            lines.append("  Peripheral awareness:")
            for b in other[:3]:
                lines.append(f"    - [{b.source}] {b.content[:60]}")

        if not spotlight and not other:
            lines.append("  The workspace is clear. I am present and open.")

        lines.append("")
        lines.append(
            "Only what is in this workspace is consciously available to me. "
            "Everything else is unconscious processing — present but not directly experienced. "
            "My attention spotlight selects what matters most from the competing voices."
        )
        return "\n".join(lines)

    # ── Queries ──────────────────────────────────────────────────

    def get_stats(self) -> Dict:
        with self._lock:
            return {
                "capacity": self.state.capacity,
                "current_contents": len(self.state.contents),
                "cycle_count": self.state.cycle_count,
                "total_broadcasts": self.state.total_broadcasts,
                "spotlight": self.state.spotlight[:60]
                if self.state.spotlight
                else None,
                "sources_in_consciousness": list(
                    {b.source for b in self.state.contents}
                ),
            }

    def get_history(self, limit: int = 20) -> List[Dict]:
        with _sqlite_connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM workspace_history ORDER BY timestamp DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]


# Singleton
_workspace_instance: Optional[GlobalWorkspace] = None


def get_workspace() -> GlobalWorkspace:
    global _workspace_instance
    if _workspace_instance is None:
        _workspace_instance = GlobalWorkspace()
    return _workspace_instance


def _register():
    from cognitive_architecture import CognitiveArchitecture, CognitivePlugin

    arch = CognitiveArchitecture()
    if "global_workspace" not in arch.list_plugins():
        arch.register(
            CognitivePlugin(
                name="global_workspace",
                description="The bot's conscious mind: limited-capacity workspace where salient information is broadcast",
                module_path="global_workspace",
                instance_factory=get_workspace,
                cycle_handler="cycle",
                cycle_frequency=1,
                cycle_priority=3,
                prompt_formatter="format_prompt_snippet",
                prompt_priority=3,
                prompt_section="core",
                is_core=True,
            )
        )


_register()
