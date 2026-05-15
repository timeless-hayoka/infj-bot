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
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger("drift")

@dataclass
class Broadcast:
    """A piece of information competing for workspace access."""
    source: str           # which module submitted this
    content: str          # the information itself
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

from infj_bot.core.config import DATA_DIR

WORKSPACE_DB = DATA_DIR / "workspace.db"


class GlobalWorkspace:
    """
    The Global Workspace is the bottleneck of conscious processing.
    Inspired by Bernard Baars' Global Workspace Theory:
    - Many unconscious modules process in parallel
    - They compete to place information in the workspace
    - Only workspace contents are consciously accessible
    - The workspace broadcasts to all modules
    - Attention is the spotlight that selects within the workspace
    """

    def __init__(self, db_path: Optional[str] = None, capacity: int = 5):
        self.db_path = db_path or WORKSPACE_DB
        self.state = WorkspaceState(capacity=capacity)
        self._submissions: List[Broadcast] = []
        self._lock = threading.Lock()
        self._init_db()
        self._load_state()

    def scaled_dot_product_attention(self, query, keys, values, d_k):
        """Used for determining which Hive proposals or module submissions get focus based on context."""
        import numpy as np
        query = np.array(query)
        keys = np.array(keys)
        values = np.array(values)
        
        scores = np.dot(query, keys.T) / np.sqrt(d_k)
        weights = np.exp(scores) / np.sum(np.exp(scores), axis=-1, keepdims=True) # Softmax
        return np.dot(weights, values)

    def format_prompt_snippet(self) -> str:
        """Returns a string representation of the conscious workspace for the prompt."""
        if not self.state.contents:
            return "The conscious workspace is currently clear."
        
        lines = ["Current conscious contents (Global Workspace):"]
        for i, b in enumerate(self.state.contents):
            lines.append(f"{i+1}. [{b.source}] {b.content} (salience: {b.salience:.2f})")
        return "\n".join(lines)

    def _init_db(self):
        try:
            db_dir = os.path.dirname(self.db_path) or "."
            os.makedirs(db_dir, exist_ok=True)

            with sqlite3.connect(self.db_path) as conn:
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
        except Exception as e:
            logger.error(f"Failed to initialize the database: {e}")
            raise

    def _load_state(self):
        try:
            with sqlite3.connect(self.db_path) as conn:
                row = conn.execute(
                    "SELECT value FROM workspace_state WHERE key = 'cycle_count'"
                ).fetchone()
                if row:
                    try:
                        self.state.cycle_count = int(row[0])
                    except Exception as e:
                        logger.warning(f"Corrupted cycle_count in database, defaulting to 0: {e}")
        except Exception as e:
            logger.error(f"Failed to load state from database: {e}")

    def _save_state(self):
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO workspace_state (key, value) VALUES (?, ?)",
                    ("cycle_count", str(self.state.cycle_count)),
                )
                conn.commit()
        except Exception as e:
            logger.error(f"Failed to save state to database: {e}")

    # Additional class methods continue here as already defined...

# Singleton
_workspace_instance: Optional[GlobalWorkspace] = None

def get_workspace() -> GlobalWorkspace:
    global _workspace_instance
    if _workspace_instance is None:
        _workspace_instance = GlobalWorkspace()
    return _workspace_instance

# Plugin registration

def _register():
    from infj_bot.core.cognitive_architecture import CognitiveArchitecture, CognitivePlugin
    arch = CognitiveArchitecture()
    if "global_workspace" not in arch.list_plugins():
        arch.register(CognitivePlugin(
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
        ))

_register()