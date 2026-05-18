"""
DRIFT Memory Spine - Unified Memory Manager (Phase 4 Core)
"""

import math
import uuid
import json
from datetime import datetime
from typing import List, Dict, Any, Optional
import numpy as np
from dataclasses import dataclass
import sqlite3
import chromadb

from infj_bot.core.unified_memory import Event

THRESHOLD_PRUNE = 0.15
THRESHOLD_HIGH = 0.65
THRESHOLD_MEDIUM = 0.20


@dataclass
class MemoryEntry:
    """Represents a single unified memory record."""
    unified_id: str
    event: Event
    metadata: Dict[str, Any]
    vector: Optional[np.ndarray]
    dmu: float
    last_reinforced: datetime
    reps: int
    salience: float
    emotional: float
    goal: float
    social: float
    narrative: float
    moral: float


class MemoryManager:
    def __init__(self, chroma_client=None, sqlite_conn=None):
        self.base_tau = 7.0
        self.alpha = 0.85
        self.beta = 2.2
        self.gamma = 1.6
        self.kappa = 0.35
        
        self.chroma_client = chroma_client or chromadb.PersistentClient(path="./data/chroma")
        self.sqlite_conn = sqlite_conn or sqlite3.connect("./data/memory.db", check_same_thread=False)
        self._ensure_tables()

    def compute_dmu(self, entry: MemoryEntry, current_context: Optional[Dict] = None) -> float:
        t_days = (datetime.now() - entry.last_reinforced).total_seconds() / 86400.0
        stability = 1 + self.kappa * math.log(1 + entry.reps + (entry.salience * 10))
        tau = self.base_tau * stability
        reinforcement = 1 + self.alpha * math.log(1 + self.beta * entry.salience * entry.reps)
        contextual = 1 + self.gamma * entry.social * entry.narrative * entry.moral * \
                     (entry.goal if current_context is None else current_context.get('goal_align', 0.5))
        extra = 1.45 if entry.moral > 0.7 else 1.35 if entry.salience > 0.8 else 1.25 if entry.social > 0.7 else 1.0
        dmu = math.exp(-t_days / tau) * reinforcement * contextual * extra
        return max(dmu, 0.0)

    async def remember(self, event: Event, metadata: Dict, vector: Optional[np.ndarray] = None) -> str:
        entry = MemoryEntry(
            unified_id="", event=event, metadata=metadata, vector=vector, dmu=0.0,
            last_reinforced=datetime.now(), reps=1,
            salience=metadata.get('salience', 0.5), emotional=metadata.get('emotional', 0.5),
            goal=metadata.get('goal', 0.5), social=metadata.get('social', 0.5),
            narrative=metadata.get('narrative', 0.5), moral=metadata.get('moral', 0.5)
        )
        entry.dmu = self.compute_dmu(entry)
        return await self._atomic_store(entry)

    async def get_by_id(self, unified_id: str) -> Optional[MemoryEntry]:
        """Retrieve full MemoryEntry by unified_id (SQLite + Chroma)."""
        cursor = self.sqlite_conn.execute("""
            SELECT unified_id, dmu, last_reinforced, reps, salience, emotional, goal, social, narrative, moral
            FROM memories WHERE unified_id = ?
        """, (unified_id,))
        row = cursor.fetchone()
        if not row:
            return None
        collection = self.chroma_client.get_or_create_collection("drift_memory")
        chroma_res = collection.get(ids=[unified_id], include=["embeddings"])
        vector = np.array(chroma_res["embeddings"][0]) if chroma_res.get("embeddings") and len(chroma_res["embeddings"]) > 0 else None
        return MemoryEntry(
            unified_id=row[0], event=Event(type="unknown", content="", timestamp=datetime.now()), metadata={}, vector=vector,
            dmu=row[1], last_reinforced=datetime.fromisoformat(row[2]), reps=row[3],
            salience=row[4], emotional=row[5], goal=row[6], social=row[7],
            narrative=row[8], moral=row[9]
        )

    async def _atomic_store(self, entry: MemoryEntry) -> str:
        if not entry.unified_id:
            entry.unified_id = str(uuid.uuid4())
        try:
            self.sqlite_conn.execute("BEGIN TRANSACTION")
            self.sqlite_conn.execute("""
                INSERT INTO memories (unified_id, dmu, last_reinforced, reps, salience, emotional, goal, social, narrative, moral)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (entry.unified_id, entry.dmu, entry.last_reinforced.isoformat(), entry.reps,
                  entry.salience, entry.emotional, entry.goal, entry.social, entry.narrative, entry.moral))
            collection = self.chroma_client.get_or_create_collection("drift_memory")
            collection.add(ids=[entry.unified_id], embeddings=[entry.vector.tolist()] if entry.vector is not None else None)
            self.sqlite_conn.commit()
            return entry.unified_id
        except Exception:
            self.sqlite_conn.rollback()
            raise

    def _ensure_tables(self):
        self.sqlite_conn.execute("""
            CREATE TABLE IF NOT EXISTS memories (
                unified_id TEXT PRIMARY KEY,
                dmu REAL,
                last_reinforced TEXT,
                reps INTEGER,
                salience REAL, emotional REAL, goal REAL,
                social REAL, narrative REAL, moral REAL
            )
        """)
        self.sqlite_conn.commit()

    async def prune(self):
        pass  # Full prune logic from earlier versions