"""global_workspace.py — Tiered Attention System for infj-bot.

Replaces the broken GWT stub with a genuine competition model:

Each cycle, ALL items (new submissions + surviving active + preconscious) compete
by current salience. The winner becomes the spotlight; runners-up fill the active
workspace; everything below active threshold goes to a preconscious tier grouped
by salience band rather than being discarded; items below the archive threshold
are logged to SQLite and evicted.

Key fixes over the previous implementation:
- Spotlight is a Broadcast object (.salience accessible directly)
- New high-salience items can evict stale low-salience active items
- Decay uses real elapsed time (not "1 cycle = 1 minute" approximation)
- No broadcast_count repetition boost that caused infinite salience inflation
- workspace.spotlight / workspace.contents accessible directly on instance
- Preconscious tiers retain below-threshold items grouped by salience band
"""

import logging
import os
import sqlite3
import threading
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional

from infj_bot.core.config import DATA_DIR

logger = logging.getLogger("drift")
WORKSPACE_DB = DATA_DIR / "workspace.db"

ACTIVE_CAPACITY = 5        # max items in the conscious workspace
PRECONSCIOUS_CAPACITY = 20 # max items retained across all preconscious tiers
ARCHIVE_THRESHOLD = 0.05   # salience below this → archived to DB and evicted

# Salience band labels used for preconscious grouping (high → low)
_BANDS = [
    (0.6, 1.0, "strong"),
    (0.4, 0.6, "moderate"),
    (0.2, 0.4, "faint"),
    (0.0, 0.2, "trace"),
]


def _band_for(salience: float) -> str:
    for lo, hi, label in _BANDS:
        if lo <= salience <= hi:
            return label
    return "trace"


@dataclass
class Broadcast:
    """A piece of information competing for workspace access."""
    source: str
    content: str
    salience: float = 0.5
    emotion_tag: Optional[str] = None
    intensity: float = 0.0
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    decay_rate: float = 0.08  # fractional salience lost per minute

    def current_salience(self, now: Optional[datetime] = None) -> float:
        """Exponential decay from creation time + emotional intensity boost."""
        if now is None:
            now = datetime.now()
        try:
            created = datetime.fromisoformat(self.timestamp)
            minutes = max(0.0, (now - created).total_seconds() / 60.0)
        except Exception:
            minutes = 0.0
        decayed = self.salience * ((1.0 - self.decay_rate) ** minutes)
        boost = min(0.25, self.intensity * 0.25) if self.intensity > 0.5 else 0.0
        return max(0.0, min(1.0, decayed + boost))


@dataclass
class WorkspaceState:
    capacity: int = ACTIVE_CAPACITY
    contents: List[Broadcast] = field(default_factory=list)
    spotlight: Optional[Broadcast] = None
    spotlight_source: Optional[str] = None
    cycle_count: int = 0
    total_broadcasts: int = 0
    broadcast_history: List[Dict] = field(default_factory=list)
    last_ignition: Optional[datetime] = None


class GlobalWorkspace:
    """
    Tiered attention workspace.

    Tiers (assigned each cycle by current salience rank):
      spotlight   — rank 1: the single item being actively attended to
      active      — ranks 2..N: consciously available, included in prompts
      preconscious — below active, above archive threshold: retained by salience band
      archived    — below archive threshold: logged to SQLite and evicted
    """

    def __init__(self, db_path=None, capacity: int = ACTIVE_CAPACITY):
        self.db_path = str(db_path or WORKSPACE_DB)
        self.state = WorkspaceState(capacity=capacity)
        self._pool: List[Broadcast] = []  # incoming submissions awaiting next cycle
        self.preconscious: Dict[str, List[Broadcast]] = {
            "strong": [], "moderate": [], "faint": [], "trace": []
        }
        self._lock = threading.Lock()
        self._init_db()
        self._load_state()

    # ── Properties for direct access (used by dii_tracker, etc.) ──────────

    @property
    def spotlight(self) -> Optional[Broadcast]:
        return self.state.spotlight

    @property
    def contents(self) -> List[Broadcast]:
        return self.state.contents

    # ── DB setup ──────────────────────────────────────────────────────────

    def _init_db(self):
        os.makedirs(os.path.dirname(self.db_path) or ".", exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS workspace_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT,
                    source TEXT,
                    content TEXT,
                    salience REAL,
                    tier TEXT
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
        try:
            with sqlite3.connect(self.db_path) as conn:
                row = conn.execute(
                    "SELECT value FROM workspace_state WHERE key = 'cycle_count'"
                ).fetchone()
                if row:
                    self.state.cycle_count = int(row[0])
        except Exception as e:
            logger.warning("Could not load workspace state: %s", e)

    def _save_state(self):
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO workspace_state (key, value) VALUES (?, ?)",
                    ("cycle_count", str(self.state.cycle_count)),
                )
                conn.commit()
        except Exception as e:
            logger.warning("Could not save workspace state: %s", e)

    def _archive_to_db(self, entries: List[tuple]):
        """Write (broadcast, tier_label) pairs to workspace_history."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.executemany(
                    "INSERT INTO workspace_history (timestamp, source, content, salience, tier) VALUES (?, ?, ?, ?, ?)",
                    [(b.timestamp, b.source, b.content[:500], b.salience, tier) for b, tier in entries],
                )
                conn.commit()
        except Exception as e:
            logger.warning("Could not archive workspace entries: %s", e)

    # ── Public API ────────────────────────────────────────────────────────

    def submit(self, source: str, content: str, salience: float = 0.5,
               emotion_tag: Optional[str] = None, intensity: float = 0.0):
        """Add a new broadcast to the pool for the next competition cycle."""
        with self._lock:
            self._pool.append(Broadcast(
                source=source,
                content=content,
                salience=salience,
                emotion_tag=emotion_tag,
                intensity=intensity,
            ))

    def set_spotlight(self, content: str, source: str = "", strength: float = 1.0):
        """Manually override the spotlight (used by external callers)."""
        b = Broadcast(source=source, content=content, salience=strength)
        self.state.spotlight = b
        self.state.spotlight_source = source
        self.state.last_ignition = datetime.now()

    def cycle(self, context=None):
        """
        Run one competition cycle.

        1. Merge new submissions with all surviving items (active + preconscious).
        2. Deduplicate by (source, content prefix).
        3. Sort all by current salience (real elapsed time decay).
        4. Assign tiers: spotlight → active → preconscious bands → archived.
        5. Persist archived items to SQLite.
        """
        with self._lock:
            self.state.cycle_count += 1
            now = datetime.now()

            # Gather all competitors
            survivors = list(self.state.contents)
            for band_items in self.preconscious.values():
                survivors.extend(band_items)
            all_items = survivors + self._pool
            self._pool = []

            # Deduplicate: same (source, content prefix) → keep highest base salience
            seen: Dict[tuple, Broadcast] = {}
            for b in all_items:
                key = (b.source, b.content[:80])
                if key not in seen or b.salience > seen[key].salience:
                    seen[key] = b

            ranked = sorted(seen.values(), key=lambda x: x.current_salience(now), reverse=True)

            # Partition into tiers
            new_active: List[Broadcast] = []
            new_preconscious: Dict[str, List[Broadcast]] = {
                "strong": [], "moderate": [], "faint": [], "trace": []
            }
            to_archive: List[tuple] = []
            preconscious_count = 0

            for b in ranked:
                cs = b.current_salience(now)
                if cs < ARCHIVE_THRESHOLD:
                    to_archive.append((b, "archived"))
                elif len(new_active) < self.state.capacity:
                    new_active.append(b)
                else:
                    # Below active threshold — place in preconscious band, not discarded
                    if preconscious_count < PRECONSCIOUS_CAPACITY:
                        band = _band_for(cs)
                        new_preconscious[band].append(b)
                        preconscious_count += 1
                    else:
                        to_archive.append((b, "archived_overflow"))

            # Commit tier assignments
            self.state.contents = new_active
            self.preconscious = new_preconscious

            # Spotlight = highest-salience Broadcast object (not a dict)
            if new_active:
                winner = new_active[0]
                self.state.spotlight = winner
                self.state.spotlight_source = winner.source
                self.state.last_ignition = now
                self.state.broadcast_history.append({
                    "content": winner.content,
                    "source": winner.source,
                    "strength": winner.current_salience(now),
                    "timestamp": now.isoformat(),
                })
                if len(self.state.broadcast_history) > 50:
                    self.state.broadcast_history.pop(0)
                self.state.total_broadcasts += len(new_active)

            if to_archive:
                self._archive_to_db(to_archive)
            self._save_state()

    def format_prompt_snippet(self) -> str:
        """Prompt-ready summary: spotlight + active awareness + top preconscious band."""
        if not self.state.contents and not any(self.preconscious.values()):
            return "Attention workspace: clear."

        now = datetime.now()
        lines = []

        if self.state.spotlight:
            s = self.state.spotlight
            lines.append(f"[Focus] {s.source}: {s.content[:200]}")

        secondary = self.state.contents[1:]
        if secondary:
            lines.append("Active awareness:")
            for b in secondary:
                lines.append(f"  · [{b.source}] {b.content[:120]} ({b.current_salience(now):.2f})")

        # Show strongest populated preconscious band
        for band in ("strong", "moderate"):
            items = self.preconscious.get(band, [])
            if items:
                lines.append(f"Background ({band}):")
                for b in items[:3]:
                    lines.append(f"  · [{b.source}] {b.content[:100]}")
                break

        return "\n".join(lines)

    def get_preconscious_summary(self) -> Dict:
        """Returns each preconscious tier's items as a dict (for inspection/debug)."""
        return {
            band: [{"source": b.source, "content": b.content[:80], "salience": b.salience}
                   for b in items]
            for band, items in self.preconscious.items()
        }


# ── Singleton ──────────────────────────────────────────────────────────────

_workspace_instance: Optional[GlobalWorkspace] = None


def get_workspace() -> GlobalWorkspace:
    global _workspace_instance
    if _workspace_instance is None:
        _workspace_instance = GlobalWorkspace()
    return _workspace_instance


def _register():
    from infj_bot.core.cognitive_architecture import CognitiveArchitecture, CognitivePlugin
    arch = CognitiveArchitecture()
    if "global_workspace" not in arch.list_plugins():
        arch.register(CognitivePlugin(
            name="global_workspace",
            description="Tiered attention workspace: spotlight → active → preconscious bands → archived",
            module_path="global_workspace",
            instance_factory=get_workspace,
            cycle_handler="cycle",
            cycle_frequency=1,
            cycle_priority=3,
            prompt_formatter="format_prompt_snippet",
            prompt_priority=3,
            prompt_section="core",
            is_core=True,
        ))


_register()
