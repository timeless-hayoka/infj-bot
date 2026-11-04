import sqlite3
import datetime
import math
import uuid
import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from pathlib import Path

import anyio

try:
    import chromadb

    _CHROMADB_AVAILABLE = True
except ImportError:
    chromadb = None  # type: ignore[assignment]
    _CHROMADB_AVAILABLE = False

from drift.core.config import PERSIST_DIRECTORY


@dataclass
class Event:
    type: str
    content: str
    timestamp: datetime.datetime = field(default_factory=datetime.datetime.now)


@dataclass
class MemoryEntry:
    unified_id: str
    event: Event
    metadata: Dict[str, Any]
    score: float = 0.0


@dataclass
class PruneStats:
    chroma_deleted: int
    sqlite_deleted: int


class MemoryManager:
    """
    Phase 4: Unified Memory Spine bridging SQLite (episodic/state) and ChromaDB (semantic).
    Atomic guarantees and Ebbinghaus forgetting built-in.
    """

    def __init__(
        self, db_path: Optional[str] = None, chroma_path: Optional[str] = None
    ):
        if db_path is None:
            self.db_path = str(Path(PERSIST_DIRECTORY) / "unified_memory.db")
        else:
            self.db_path = db_path

        if chroma_path is None:
            self.chroma_path = str(PERSIST_DIRECTORY)
        else:
            self.chroma_path = chroma_path

        self._init_sqlite()

        self._client = None
        self._collection = None

        if _CHROMADB_AVAILABLE:
            # Explicitly use project's default embedding function
            from drift.core.embeddings import get_default_embedding_function

            self.embedding_function = get_default_embedding_function()
            self._client = chromadb.PersistentClient(path=self.chroma_path)
            self._collection = self._client.get_or_create_collection(
                name="infj_unified_memory_v2", embedding_function=self.embedding_function
            )
        else:
            self.embedding_function = None

    @property
    def collection(self):
        """Returns the underlying ChromaDB collection."""
        return self._collection

    def _init_sqlite(self):
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS state (
                    key TEXT PRIMARY KEY,
                    value TEXT,
                    expires_at TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS episodic (
                    unified_id TEXT PRIMARY KEY,
                    event_type TEXT,
                    content TEXT,
                    timestamp TIMESTAMP,
                    metadata TEXT,
                    salience REAL,
                    repetitions INTEGER DEFAULT 0
                )
            """)
            conn.commit()

    def remember_sync(
        self, event: Event, metadata: dict, vector: Optional[Any] = None
    ) -> str:
        unified_id = str(uuid.uuid4())
        salience = float(metadata.get("importance", metadata.get("salience", 0.5)))

        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO episodic (unified_id, event_type, content, timestamp, metadata, salience) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    unified_id,
                    event.type,
                    event.content,
                    event.timestamp.isoformat(),
                    json.dumps(metadata),
                    salience,
                ),
            )

        kwargs = {
            "documents": [event.content],
            "metadatas": [{"unified_id": unified_id, "type": event.type}],
            "ids": [unified_id],
        }
        for k, v in metadata.items():
            if isinstance(v, (str, int, float, bool)):
                kwargs["metadatas"][0][k] = v

        if vector is not None:
            kwargs["embeddings"] = [vector]
        self._collection.add(**kwargs)
        return unified_id

    async def remember(
        self, event: Event, metadata: dict, vector: Optional[Any] = None
    ) -> str:
        return await anyio.to_thread.run_sync(
            self.remember_sync, event, metadata, vector
        )

    def _calculate_dmu(
        self,
        t_hours: float,
        salience: float,
        repetitions: int,
        c_score: float = 0.0,
        e_score: float = 0.5,
        g_score: float = 0.5,
        social: float = 0.5,
        narrative: float = 0.5,
        moral: float = 0.5,
    ) -> float:
        """
        DRIFT Memory Utility (DMU) Function
        """
        base_tau = 7.0
        alpha = 0.85
        beta = 2.2
        gamma = 1.6
        kappa = 0.35

        t_days = t_hours / 24.0

        stability = 1.0 + kappa * math.log(1.0 + repetitions + (salience * 10.0))
        tau = base_tau * stability

        reinforcement = 1.0 + alpha * math.log(1.0 + beta * salience * repetitions)

        # When pruning, c_score is 0, so it uses g_score (goal). During recall, c_score acts as the context align.
        context_align = g_score if c_score == 0.0 else c_score
        contextual = 1.0 + gamma * social * narrative * moral * context_align

        extra = (
            1.45
            if moral > 0.7
            else 1.35
            if salience > 0.8
            else 1.25
            if social > 0.7
            else 1.0
        )

        dmu = math.exp(-t_days / tau) * reinforcement * contextual * extra
        return max(dmu, 0.0)

    def recall_sync(
        self, query: str, limit: int = 20, decay_weight: float = 1.0
    ) -> List[MemoryEntry]:
        results = self._collection.query(query_texts=[query], n_results=limit * 2)
        if not results["ids"] or not results["ids"][0]:
            return []

        chroma_ids = results["ids"][0]
        distances = results["distances"][0]

        placeholders = ",".join("?" * len(chroma_ids))
        entries = []
        now = datetime.datetime.now()

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                f"SELECT * FROM episodic WHERE unified_id IN ({placeholders})",
                chroma_ids,
            ).fetchall()
            row_map = {row["unified_id"]: dict(row) for row in rows}

        for c_id, dist in zip(chroma_ids, distances):
            if c_id not in row_map:
                continue
            row = row_map[c_id]
            ts = datetime.datetime.fromisoformat(row["timestamp"])
            salience = row["salience"]
            repetitions = row["repetitions"]
            meta = json.loads(row["metadata"])

            t_hours = max(0, (now - ts).total_seconds() / 3600.0)
            sim_score = max(0.0, 1.0 - (dist * dist) / 2.0)
            boost = 0.0
            try:
                import re

                query_words = set(re.findall(r"\b\w{3,}\b", query.lower()))
                content_words = set(re.findall(r"\b\w{3,}\b", row["content"].lower()))
                overlap = query_words.intersection(content_words)
                if query_words:
                    boost = 0.2 * (len(overlap) / len(query_words))
            except Exception:
                pass
            sim_score = min(1.0, sim_score + boost)

            e_score = float(meta.get("emotion_intensity", meta.get("emotional", 0.5)))
            g_score = float(meta.get("importance", meta.get("goal", 0.5)))
            social = float(meta.get("social", 0.5))
            narrative = float(meta.get("narrative", 0.5))
            moral = float(meta.get("moral", 0.5))

            dmu = self._calculate_dmu(
                t_hours,
                salience,
                repetitions,
                c_score=sim_score,
                e_score=e_score,
                g_score=g_score,
                social=social,
                narrative=narrative,
                moral=moral,
            )

            # If decay_weight is used to suppress/enhance time effects, we can apply it.
            # But the DMU essentially is the final score.
            final_score = dmu * decay_weight

            event = Event(type=row["event_type"], content=row["content"], timestamp=ts)
            entries.append(
                MemoryEntry(
                    unified_id=c_id, event=event, metadata=meta, score=final_score
                )
            )

        entries.sort(key=lambda x: x.score, reverse=True)
        return entries[:limit]

    async def recall(
        self, query: str, limit: int = 20, decay_weight: float = 1.0
    ) -> List[MemoryEntry]:
        return await anyio.to_thread.run_sync(
            self.recall_sync, query, limit, decay_weight
        )

    def get_recent_sync(self, event_type: str, limit: int = 5) -> List[MemoryEntry]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM episodic WHERE event_type = ? ORDER BY timestamp DESC LIMIT ?",
                (event_type, limit),
            ).fetchall()

            entries = []
            for row in rows:
                ts = datetime.datetime.fromisoformat(row["timestamp"])
                event = Event(
                    type=row["event_type"], content=row["content"], timestamp=ts
                )
                meta = json.loads(row["metadata"])
                # Recent entries don't have a semantic score, just order by recency
                entries.append(
                    MemoryEntry(
                        unified_id=row["unified_id"],
                        event=event,
                        metadata=meta,
                        score=1.0,
                    )
                )
            return entries

    async def get_recent(self, event_type: str, limit: int = 5) -> List[MemoryEntry]:
        return await anyio.to_thread.run_sync(self.get_recent_sync, event_type, limit)

    def count_sync(self, event_type: Optional[str] = None) -> int:
        with sqlite3.connect(self.db_path) as conn:
            if event_type:
                return conn.execute(
                    "SELECT COUNT(*) FROM episodic WHERE event_type = ?", (event_type,)
                ).fetchone()[0]
            return conn.execute("SELECT COUNT(*) FROM episodic").fetchone()[0]

    async def count(self, event_type: Optional[str] = None) -> int:
        return await anyio.to_thread.run_sync(self.count_sync, event_type)

    def forget_concept_sync(self, concept_name: str) -> int:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT unified_id, metadata FROM episodic WHERE event_type = 'learned_knowledge'"
            ).fetchall()

            to_delete = []
            for row in rows:
                meta = json.loads(row["metadata"])
                if meta.get("concept") == concept_name:
                    to_delete.append(row["unified_id"])

            if not to_delete:
                return 0

            placeholders = ",".join("?" * len(to_delete))
            conn.execute(
                f"DELETE FROM episodic WHERE unified_id IN ({placeholders})", to_delete
            )
            conn.commit()

        self._collection.delete(ids=to_delete)
        return len(to_delete)

    async def forget_concept(self, concept_name: str) -> int:
        return await anyio.to_thread.run_sync(self.forget_concept_sync, concept_name)

    def prune_sync(
        self,
        now: datetime.datetime = None,
        threshold: float = 0.15,
        max_memories: int = None,
        force: bool = False,
    ) -> PruneStats:
        """Prune low-value memories using DMU scoring with safety guards.

        Safety: never deletes entries < 1 hour old or with emotion_intensity > 0.85.
        Hard cap: if still over max_memories, removes lowest-DMU non-protected entries.
        """
        if now is None:
            now = datetime.datetime.now()
        if max_memories is None:
            max_memories = 2500

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT unified_id, timestamp, salience, repetitions, metadata FROM episodic"
            ).fetchall()

            if len(rows) <= max_memories and not force:
                return PruneStats(0, 0)

            to_delete = []
            scored = []  # (unified_id, dmu, protected)

            for row in rows:
                ts = datetime.datetime.fromisoformat(row["timestamp"])
                t_hours = max(0, (now - ts).total_seconds() / 3600.0)
                salience = row["salience"]
                repetitions = row["repetitions"]
                meta = json.loads(row["metadata"])

                e_score = float(
                    meta.get("emotion_intensity", meta.get("emotional", 0.5))
                )
                g_score = float(meta.get("importance", meta.get("goal", 0.5)))
                social = float(meta.get("social", 0.5))
                narrative = float(meta.get("narrative", 0.5))
                moral = float(meta.get("moral", 0.5))

                # Context (C) is 0 during background prune (no query alignment)
                dmu = self._calculate_dmu(
                    t_hours,
                    salience,
                    repetitions,
                    c_score=0.0,
                    e_score=e_score,
                    g_score=g_score,
                    social=social,
                    narrative=narrative,
                    moral=moral,
                )

                # Safety overrides
                is_too_recent = t_hours < 1.0
                is_high_emotion = e_score > 0.85
                protected = is_too_recent or is_high_emotion

                if not protected and dmu < threshold:
                    to_delete.append(row["unified_id"])

                scored.append((row["unified_id"], dmu, protected))

            # Hard cap: if still over limit, remove lowest-scoring non-protected
            remaining_after_threshold = len(rows) - len(to_delete)
            if remaining_after_threshold > max_memories:
                deletable = [
                    (uid, dmu)
                    for uid, dmu, protected in scored
                    if uid not in to_delete and not protected
                ]
                deletable.sort(key=lambda x: x[1])  # lowest DMU first
                needed = remaining_after_threshold - max_memories
                for uid, _ in deletable[:needed]:
                    to_delete.append(uid)

            if not to_delete:
                return PruneStats(0, 0)

            placeholders = ",".join("?" * len(to_delete))
            conn.execute(
                f"DELETE FROM episodic WHERE unified_id IN ({placeholders})", to_delete
            )
            conn.commit()

        self._collection.delete(ids=to_delete)
        self._log_prune_stats(len(to_delete), len(rows), len(rows) - len(to_delete))
        return PruneStats(chroma_deleted=len(to_delete), sqlite_deleted=len(to_delete))

    async def prune(
        self,
        now: datetime.datetime = None,
        threshold: float = 0.15,
        max_memories: int = None,
        force: bool = False,
    ) -> PruneStats:
        return await anyio.to_thread.run_sync(
            self.prune_sync, now, threshold, max_memories, force
        )

    def auto_prune_sync(self, turn_count: int = 0, force: bool = False) -> PruneStats:
        """Auto-prune based on turn count or time since last prune.

        Call this periodically (e.g. every consciousness cycle or N user turns).
        """
        from drift.core.config import (
            BACKGROUND_PRUNE_INTERVAL_SECONDS,
            PRUNE_EVERY_N_TURNS,
            PRUNING_THRESHOLD,
            MAX_MEMORIES,
        )

        should_prune = force

        # Turn-based trigger
        if turn_count > 0 and turn_count % PRUNE_EVERY_N_TURNS == 0:
            should_prune = True

        # Time-based trigger
        if not should_prune:
            last_prune = self.get_state_sync("last_prune_time")
            if last_prune is None:
                should_prune = True
            else:
                last = (
                    datetime.datetime.fromisoformat(last_prune)
                    if isinstance(last_prune, str)
                    else last_prune
                )
                elapsed = (datetime.datetime.now() - last).total_seconds()
                if elapsed >= BACKGROUND_PRUNE_INTERVAL_SECONDS:
                    should_prune = True

        if not should_prune:
            return PruneStats(0, 0)

        stats = self.prune_sync(threshold=PRUNING_THRESHOLD, max_memories=MAX_MEMORIES)
        if stats.sqlite_deleted > 0:
            self.set_state_sync("last_prune_time", datetime.datetime.now().isoformat())
        return stats

    async def auto_prune(self, turn_count: int = 0, force: bool = False) -> PruneStats:
        return await anyio.to_thread.run_sync(self.auto_prune_sync, turn_count, force)

    def _log_prune_stats(self, pruned: int, before: int, after: int):
        """Log pruning stats to JSONL for observability."""
        log_path = Path(self.chroma_path) / "prune_log.jsonl"
        entry = {
            "timestamp": datetime.datetime.now().isoformat(),
            "pruned": pruned,
            "before": before,
            "after": after,
        }
        try:
            from drift.core.jsonl_logger import HardenedJsonlLogger

            HardenedJsonlLogger(log_path).append(entry)
        except Exception:
            pass

    def get_state_sync(self, key: str, default: Any = None) -> Any:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT value, expires_at FROM state WHERE key = ?", (key,)
            ).fetchone()
            if row:
                val, exp = row
                if exp:
                    expires_at = datetime.datetime.fromisoformat(exp)
                    if datetime.datetime.now() > expires_at:
                        conn.execute("DELETE FROM state WHERE key = ?", (key,))
                        conn.commit()
                        return default
                return json.loads(val)
            return default

    async def get_state(self, key: str, default: Any = None) -> Any:
        return await anyio.to_thread.run_sync(self.get_state_sync, key, default)

    def set_state_sync(
        self, key: str, value: Any, ttl: Optional[datetime.timedelta] = None
    ):
        expires_at = None
        if ttl:
            expires_at = (datetime.datetime.now() + ttl).isoformat()

        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO state (key, value, expires_at) VALUES (?, ?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value, expires_at=excluded.expires_at",
                (key, json.dumps(value), expires_at),
            )
            conn.commit()

    async def set_state(
        self, key: str, value: Any, ttl: Optional[datetime.timedelta] = None
    ):
        return await anyio.to_thread.run_sync(self.set_state_sync, key, value, ttl)
