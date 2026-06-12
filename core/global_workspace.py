"""global_workspace.py — Tiered Attention System for drift.

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
import sys
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional

from drift.core.config import DATA_DIR

try:
    from drift.core.svalbard_vault import SvalbardVault
    from drift.core.pedi_metrics import PEDIEngine
except ImportError:
    from svalbard_vault import SvalbardVault
    from pedi_metrics import PEDIEngine

logger = logging.getLogger("drift")
WORKSPACE_DB = DATA_DIR / "workspace.db"

ACTIVE_CAPACITY = 5  # max items in the conscious workspace
PRECONSCIOUS_CAPACITY = 20  # max items retained across all preconscious tiers
ARCHIVE_THRESHOLD = 0.05  # salience below this → archived to DB and evicted

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
            "strong": [],
            "moderate": [],
            "faint": [],
            "trace": [],
        }
        self._lock = threading.Lock()
        self._cycle_count: int = 0
        self._total_submitted: int = 0
        self._db_path = self.db_path
        self._init_db()
        self._load_state()

        # PEDI & Svalbard integration (Fly-by-wire)
        self.vault = SvalbardVault()
        self.vault.verify_identity_integrity(full_chain=False) 
        self.pedi = PEDIEngine(self.vault)
        self._self_check_diagnostics(self.pedi, self.vault)

    def _self_check_diagnostics(self, pedi_engine, vault):
        print("[SYSTEM] Running Global Workspace integration check...", file=sys.stderr)
        if not pedi_engine or not vault:
            print("[CRITICAL] Workspace disconnected from identity regulator or vault.", file=sys.stderr)
            sys.exit(1)
        print("[SYSTEM] Regulatory triad verified. Workspace is live.", file=sys.stderr)

    def _lantern_4_veto(self, user_input: str, sys_response: str, active_state: dict) -> tuple[bool, bool]:
        """Returns (approved: bool, quarantine: bool)"""
        resonance = active_state.get("resonance", 0.0)
        shadow_depth = active_state.get("shadow_depth", 0.0)

        # Criteria 1: Must have high resonance to even be considered
        if resonance < 0.85:
            return False, False
            
        # Criteria 2: Semantic Density Override
        # If resonance is absolute fire, ignore length constraints.
        if resonance < 0.95:
            if len(user_input.split()) < 5 or len(sys_response.split()) < 10:
                print("[LANTERN-4] Rejected: Exchange lacks semantic depth.")
                return False, False
                
        # Criteria 3: Shadow Quarantine Protocol
        # Accept messy breakthroughs, but flag them so PEDI doesn't anchor to them blindly.
        quarantine = False
        if shadow_depth > 0.75:
            print(f"[LANTERN-4] High Shadow Depth ({shadow_depth}). Marking block for quarantine.")
            quarantine = True
            
        print("[LANTERN-4] Nomination approved.")
        return True, quarantine

    def execute_cli_cycle(self, raw_active_state: dict, user_input: str, generate_response_func):
        """
        The main hook for your AntiGravity CLI.
        Pass the active state, the user input, and your LLM generation function.
        """
        # 1. PEDI Fly-By-Wire Regulation (Fix state BEFORE thinking)
        regulated_state, correction, status = self.pedi.evaluate_cycle(raw_active_state)
        
        # 2. Act using aligned state
        # (Your CLI calls its actual LLM here, passing the regulated state as context)
        sys_response = generate_response_func(user_input, regulated_state)
        
        # 3. Lantern-4 Veto & Svalbard Sealing (Post-action evaluation)
        if status == "EVOLVING" or regulated_state.get("resonance", 0.0) > 0.90:
            in_correcting_state = (status == "CORRECTING")
            is_hold_state = status.startswith("HOLD")
            if not is_hold_state and not in_correcting_state:
                approved, quarantine = self._lantern_4_veto(user_input, sys_response, regulated_state)
                if approved:
                    self.vault.deposit_core_memory(
                        event=f"CLI Milestone: {user_input[:40]}...",
                        user_q=user_input,
                        sys_q=sys_response,
                        current_state=regulated_state,
                        quarantined=quarantine
                    )
                
        # Return the regulated state so your CLI loop can persist it to the next turn
        return sys_response, regulated_state, status

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
            # Migration: add 'tier' column if it does not exist in legacy table
            try:
                conn.execute("ALTER TABLE workspace_history ADD COLUMN tier TEXT")
            except sqlite3.OperationalError:
                pass
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
                    [
                        (b.timestamp, b.source, b.content[:500], b.salience, tier)
                        for b, tier in entries
                    ],
                )
                conn.commit()
        except Exception as e:
            logger.warning("Could not archive workspace entries: %s", e)

    # ── Public API ────────────────────────────────────────────────────────

    def submit(
        self,
        source: str,
        content: str,
        salience: float = 0.5,
        emotion_tag: Optional[str] = None,
        intensity: float = 0.0,
    ):
        """Add a new broadcast to the pool for the next competition cycle."""
        with self._lock:
            self._pool.append(
                Broadcast(
                    source=source,
                    content=content,
                    salience=salience,
                    emotion_tag=emotion_tag,
                    intensity=intensity,
                )
            )
            self._total_submitted += 1

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
            self._cycle_count += 1
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

            ranked = sorted(
                seen.values(), key=lambda x: x.current_salience(now), reverse=True
            )

            # Partition into tiers
            new_active: List[Broadcast] = []
            new_preconscious: Dict[str, List[Broadcast]] = {
                "strong": [],
                "moderate": [],
                "faint": [],
                "trace": [],
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
                self.state.broadcast_history.append(
                    {
                        "content": winner.content,
                        "source": winner.source,
                        "strength": winner.current_salience(now),
                        "timestamp": now.isoformat(),
                    }
                )
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
                lines.append(
                    f"  · [{b.source}] {b.content[:120]} ({b.current_salience(now):.2f})"
                )

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
            band: [
                {"source": b.source, "content": b.content[:80], "salience": b.salience}
                for b in items
            ]
            for band, items in self.preconscious.items()
        }

    @property
    def _submissions(self) -> list:
        """Alias for the pending broadcast pool (used by api.py for count)."""
        return self._pool

    def get_conscious_summary(self) -> str:
        """Human-readable summary of current conscious contents."""
        return self.format_prompt_snippet()

    def get_history(self, limit: int = 10) -> list:
        """Return recent archived broadcasts from the SQLite log."""
        try:
            import sqlite3

            with sqlite3.connect(self._db_path) as conn:
                rows = conn.execute(
                    "SELECT source, content, salience, archived_at FROM workspace_archive ORDER BY archived_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
            return [
                {
                    "source": r[0],
                    "content": r[1],
                    "salience": r[2],
                    "entered_workspace": True,
                    "timestamp": r[3],
                }
                for r in rows
            ]
        except Exception:
            return []

    def get_stats(self) -> dict:
        """Return a snapshot of workspace statistics."""
        with self._lock:
            spotlight = self.state.spotlight
            return {
                "capacity": ACTIVE_CAPACITY,
                "current_contents": len(self.state.contents),
                "cycle_count": self._cycle_count,
                "total_broadcasts": self._total_submitted,
                "spotlight": spotlight.source if spotlight else None,
                "sources_in_consciousness": [b.source for b in self.state.contents],
            }

    def move_spotlight(self, content: str) -> bool:
        """Force spotlight to the active item whose content matches the given string."""
        with self._lock:
            for b in self.state.contents:
                if content.lower() in b.content.lower():
                    self.state.contents.remove(b)
                    if self.state.spotlight:
                        self.state.contents.insert(0, self.state.spotlight)
                    self.state.spotlight = b
                    self._save_state()
                    return True
        return False

    def reflect_on_workspace(self) -> Optional[Broadcast]:
        """Generate a higher-order reflection on current conscious contents."""
        with self._lock:
            items = self.state.contents
            if len(items) < 2:
                return None
            themes = "; ".join(f"{b.source}: {b.content[:60]}" for b in items[:3])
            return Broadcast(
                source="metacognition",
                content=f"Noticing multiple active concerns: {themes}",
                salience=0.6,
            )


# ── Singleton ──────────────────────────────────────────────────────────────

_workspace_instance: Optional[GlobalWorkspace] = None


def get_workspace() -> GlobalWorkspace:
    global _workspace_instance
    if _workspace_instance is None:
        _workspace_instance = GlobalWorkspace()
    return _workspace_instance


def _register():
    from drift.core.cognitive_architecture import (
        CognitiveArchitecture,
        CognitivePlugin,
    )

    arch = CognitiveArchitecture()
    if "global_workspace" not in arch.list_plugins():
        arch.register(
            CognitivePlugin(
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
            )
        )


_register()
