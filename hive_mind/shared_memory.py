"""Distributed semantic memory for the DRIFT Hive.

All nodes read and write to a shared ChromaDB collection with attribution,
consensus scoring, and contradiction detection.
"""
from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

# Attempt to import ChromaDB; gracefully degrade if unavailable
try:
    import chromadb
    from chromadb.config import Settings
    HAS_CHROMA = True
except Exception:
    HAS_CHROMA = False


@dataclass
class HiveMemory:
    memory_id: str
    content: str
    source_node: str
    memory_type: str = "semantic"          # semantic, episodic, procedural, reflection
    reliability_tier: float = 0.5           # 0.0-1.0
    consensus_score: float = 0.0            # how many nodes have validated this
    created_at: float = field(default_factory=time.time)
    retrieved_at: Optional[float] = None
    metadata: dict[str, Any] = field(default_factory=dict)


class SharedMemoryLayer:
    """Hive-wide memory with local fallback."""

    def __init__(
        self,
        collection_name: str = "hive_memory",
        persist_dir: str = "chroma_db/hive",
        fallback_db: str = "hive_mind/hive_memory.db",
    ) -> None:
        self.collection_name = collection_name
        self.persist_dir = Path(persist_dir)
        self.persist_dir.mkdir(parents=True, exist_ok=True)
        self.fallback_db = Path(fallback_db)
        self._collection: Any = None
        self._client: Any = None
        self._init_chroma()
        self._init_fallback()

    def _init_chroma(self) -> None:
        if not HAS_CHROMA:
            return
        try:
            self._client = chromadb.Client(
                Settings(
                    chroma_db_impl="duckdb+parquet",
                    persist_directory=str(self.persist_dir),
                    anonymized_telemetry=False,
                )
            )
            self._collection = self._client.get_or_create_collection(
                name=self.collection_name,
                metadata={"hnsw:space": "cosine"},
            )
        except Exception:
            self._client = None
            self._collection = None

    def _init_fallback(self) -> None:
        conn = sqlite3.connect(str(self.fallback_db))
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS hive_memory (
                memory_id TEXT PRIMARY KEY,
                content TEXT NOT NULL,
                source_node TEXT NOT NULL,
                memory_type TEXT DEFAULT 'semantic',
                reliability_tier REAL DEFAULT 0.5,
                consensus_score REAL DEFAULT 0.0,
                created_at REAL,
                retrieved_at REAL,
                metadata TEXT
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_source ON hive_memory(source_node)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_type ON hive_memory(memory_type)"
        )
        conn.commit()
        conn.close()

    # --- Write ---

    def save(
        self,
        memory: HiveMemory,
        embedding: Optional[list[float]] = None,
    ) -> None:
        # Chroma path
        if self._collection is not None and embedding is not None:
            try:
                self._collection.add(
                    ids=[memory.memory_id],
                    documents=[memory.content],
                    embeddings=[embedding],
                    metadatas=[{
                        "source_node": memory.source_node,
                        "memory_type": memory.memory_type,
                        "reliability_tier": memory.reliability_tier,
                        "consensus_score": memory.consensus_score,
                        "created_at": memory.created_at,
                        **memory.metadata,
                    }],
                )
            except Exception:
                pass

        # SQLite fallback (always write here for attribution/consensus tracking)
        conn = sqlite3.connect(str(self.fallback_db))
        conn.execute(
            """
            INSERT OR REPLACE INTO hive_memory
            (memory_id, content, source_node, memory_type, reliability_tier,
             consensus_score, created_at, retrieved_at, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                memory.memory_id,
                memory.content,
                memory.source_node,
                memory.memory_type,
                memory.reliability_tier,
                memory.consensus_score,
                memory.created_at,
                memory.retrieved_at,
                json.dumps(memory.metadata),
            ),
        )
        conn.commit()
        conn.close()

    # --- Read ---

    def retrieve(
        self,
        query_embedding: Optional[list[float]] = None,
        query_text: Optional[str] = None,
        top_k: int = 5,
        source_filter: Optional[str] = None,
        min_reliability: float = 0.0,
    ) -> list[HiveMemory]:
        results: list[HiveMemory] = []

        # Try Chroma semantic search
        if self._collection is not None and query_embedding is not None:
            try:
                chroma_results = self._collection.query(
                    query_embeddings=[query_embedding],
                    n_results=top_k * 2,
                    where={"reliability_tier": {"$gte": min_reliability}},
                )
                for i, doc_id in enumerate(chroma_results["ids"][0]):
                    meta = chroma_results["metadatas"][0][i]
                    results.append(HiveMemory(
                        memory_id=doc_id,
                        content=chroma_results["documents"][0][i],
                        source_node=meta.get("source_node", "unknown"),
                        memory_type=meta.get("memory_type", "semantic"),
                        reliability_tier=meta.get("reliability_tier", 0.5),
                        consensus_score=meta.get("consensus_score", 0.0),
                        created_at=meta.get("created_at", time.time()),
                        metadata={k: v for k, v in meta.items() if k not in {
                            "source_node", "memory_type", "reliability_tier",
                            "consensus_score", "created_at",
                        }},
                    ))
            except Exception:
                pass

        # Fallback: SQLite keyword + recency blend
        if not results and query_text:
            conn = sqlite3.connect(str(self.fallback_db))
            cursor = conn.cursor()
            sql = """
                SELECT memory_id, content, source_node, memory_type,
                       reliability_tier, consensus_score, created_at, metadata
                FROM hive_memory
                WHERE content LIKE ? AND reliability_tier >= ?
            """
            params = [f"%{query_text}%", min_reliability]
            if source_filter:
                sql += " AND source_node = ?"
                params.append(source_filter)
            sql += " ORDER BY (consensus_score * 0.4 + reliability_tier * 0.4 + (1.0 / (1.0 + ? - created_at)) * 0.2) DESC LIMIT ?"
            params.extend([time.time(), top_k])
            cursor.execute(sql, params)
            for row in cursor.fetchall():
                results.append(HiveMemory(
                    memory_id=row[0],
                    content=row[1],
                    source_node=row[2],
                    memory_type=row[3],
                    reliability_tier=row[4],
                    consensus_score=row[5],
                    created_at=row[6],
                    metadata=json.loads(row[7] or "{}"),
                ))
            conn.close()

        return results[:top_k]

    # --- Consensus & Contradiction ---

    def validate(self, memory_id: str, validator_node: str, boost: float = 0.1) -> None:
        """Another node vouches for this memory — boost its consensus score."""
        conn = sqlite3.connect(str(self.fallback_db))
        cursor = conn.cursor()
        cursor.execute(
            "SELECT consensus_score, metadata FROM hive_memory WHERE memory_id = ?",
            (memory_id,),
        )
        row = cursor.fetchone()
        if row:
            score = min(1.0, row[0] + boost)
            meta = json.loads(row[1] or "{}")
            validators = meta.get("validators", [])
            if validator_node not in validators:
                validators.append(validator_node)
                meta["validators"] = validators
            cursor.execute(
                "UPDATE hive_memory SET consensus_score = ?, metadata = ? WHERE memory_id = ?",
                (score, json.dumps(meta), memory_id),
            )
            conn.commit()
        conn.close()

    def find_contradictions(self, memory_id: str) -> list[HiveMemory]:
        """Find memories that contradict the given memory."""
        conn = sqlite3.connect(str(self.fallback_db))
        cursor = conn.cursor()
        cursor.execute(
            "SELECT content, metadata FROM hive_memory WHERE memory_id = ?",
            (memory_id,),
        )
        row = cursor.fetchone()
        if not row:
            conn.close()
            return []

        content = row[0]
        # Simple heuristic: look for negation keywords or opposite sentiment markers
        # In a full implementation, this would use an NLI model
        negation_terms = ["not", "never", "no ", "false", "wrong", "opposite", "contradict"]
        has_negation = any(term in content.lower() for term in negation_terms)

        # Fetch memories from same source or same topic that might conflict
        cursor.execute(
            """
            SELECT memory_id, content, source_node, memory_type,
                   reliability_tier, consensus_score, created_at, metadata
            FROM hive_memory
            WHERE memory_id != ? AND (
                content LIKE ? OR content LIKE ?
            )
            ORDER BY created_at DESC LIMIT 10
            """,
            (memory_id, f"%not {content[:20]}%", f"%{content[:20]}%"),
        )
        contradictions = []
        for r in cursor.fetchall():
            contradictions.append(HiveMemory(
                memory_id=r[0], content=r[1], source_node=r[2],
                memory_type=r[3], reliability_tier=r[4],
                consensus_score=r[5], created_at=r[6],
                metadata=json.loads(r[7] or "{}"),
            ))
        conn.close()
        return contradictions

    def stats(self) -> dict[str, Any]:
        conn = sqlite3.connect(str(self.fallback_db))
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM hive_memory")
        total = cursor.fetchone()[0]
        cursor.execute("SELECT source_node, COUNT(*) FROM hive_memory GROUP BY source_node")
        by_node = dict(cursor.fetchall())
        cursor.execute("SELECT AVG(consensus_score), AVG(reliability_tier) FROM hive_memory")
        avgs = cursor.fetchone()
        conn.close()
        return {
            "total_memories": total,
            "by_node": by_node,
            "avg_consensus": round(avgs[0] or 0.0, 3),
            "avg_reliability": round(avgs[1] or 0.0, 3),
        }
