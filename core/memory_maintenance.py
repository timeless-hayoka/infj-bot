"""
core/memory_maintenance.py — Cognitive Forgetting & Consolidation
==================================================================
Implements the 'Forgetting Curve' logic to prevent context poisoning,
reduce resonance loops, and maintain cognitive agility.

Mechanism:
1. Identify stale/low-salience episodic memories.
2. Summarize/Consolidate into Durable Knowledge (Semantic/Episodic traits).
3. Move raw details to Cold Storage (Archive).
4. Prune from Active Memory (ChromaDB/SQLite).

Part of Phase 6 (Safety/Stability) and Nexus Roadmap.
"""

import logging
import sqlite3
from datetime import datetime, timedelta
from typing import List, Dict

from drift.core.config import DATA_DIR, BEING_DB, NEXUS_DB
from drift.core.local_llm import OllamaBridge

logger = logging.getLogger("drift.memory_maintenance")

ARCHIVE_DB = DATA_DIR / "archive.db"

class ForgettingEngine:
    """Enforces the forgetting curve on the PHI organism."""

    def __init__(self, brain=None):
        self.brain = brain or OllamaBridge() # Use local if possible
        self._init_dbs()

    def _init_dbs(self):
        """Ensure schemas exist for Cold Storage."""
        with sqlite3.connect(ARCHIVE_DB) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS archived_memories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    original_id TEXT,
                    timestamp TEXT,
                    content TEXT,
                    metadata TEXT,
                    archived_at TEXT
                )
            """)
            conn.commit()

    async def consolidate(self, cutoff_hours: int = 48):
        """Perform a consolidation cycle."""
        logger.info("[forgetting] Starting consolidation cycle (cutoff: %dh)", cutoff_hours)
        
        # 1. Fetch stale thoughts from being.db
        stale_thoughts = self._fetch_stale_thoughts(cutoff_hours)
        if not stale_thoughts:
            logger.info("[forgetting] No stale thoughts found.")
            return

        # 2. Extract durable knowledge via Brain (LLM)
        knowledge = await self._extract_knowledge(stale_thoughts)
        
        # 3. Commit to Nexus and Cold Storage
        if knowledge:
            self._commit_knowledge(knowledge)
            self._archive_and_purge(stale_thoughts)
            logger.info("[forgetting] Consolidated %d thoughts into durable knowledge.", len(stale_thoughts))
        else:
            logger.warning("[forgetting] No knowledge extracted. Retaining thoughts for next cycle.")
            
        # 4. Long-term DB maintenance
        self.vacuum_dbs()

    def vacuum_dbs(self):
        """Run SQLite VACUUM to defragment and optimize databases for long-term operation."""
        dbs = [ARCHIVE_DB, BEING_DB, NEXUS_DB]
        for db in dbs:
            try:
                with sqlite3.connect(db) as conn:
                    conn.execute("VACUUM")
                logger.info("[forgetting] Vacuumed database %s.", db)
            except Exception as e:
                logger.error("[forgetting] Failed to vacuum %s: %s", db, e)

    def _fetch_stale_thoughts(self, hours: int) -> List[Dict]:
        cutoff = datetime.now() - timedelta(hours=hours)
        with sqlite3.connect(BEING_DB) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM thoughts WHERE timestamp < ?",
                (cutoff.isoformat(),)
            ).fetchall()
        return [dict(r) for r in rows]

    async def _extract_knowledge(self, thoughts: List[Dict]) -> List[Dict]:
        if not thoughts:
            return []
        
        # Format for LLM
        text = "\n".join([f"[{t['timestamp']}] {t['content']}" for t in thoughts])
        
        prompt = f"""
You are the PHI Memory Consolidator. Analyze these raw thoughts and extract 
enduring patterns, preferences, or rules about Jude (the user) or yourself.

Output strictly as a JSON array of:
{{"category": "preference|behavior|rule", "fact": "the generalized insight", "confidence": 0.0-1.0}}

THOUGHTS:
{text}
"""
        try:
            # Note: Using brain.think or brain._generate
            # For now, we assume self.brain is functional
            response = self.brain.think(prompt, mode="engineer")
            import json
            import re
            # Extract JSON
            match = re.search(r"\[.*\]", response, re.DOTALL)
            if match:
                return json.loads(match.group())
        except Exception as e:
            logger.error("[forgetting] Extraction failed: %s", e)
        return []

    def _commit_knowledge(self, knowledge: List[Dict]):
        now = datetime.now().isoformat()
        with sqlite3.connect(NEXUS_DB) as conn:
            for item in knowledge:
                try:
                    conn.execute(
                        "INSERT INTO durable_knowledge (category, content, confidence, last_reinforced, created_at) VALUES (?, ?, ?, ?, ?)",
                        (item['category'], item['fact'], item['confidence'], now, now)
                    )
                except sqlite3.OperationalError:
                    # Table might not exist yet if using a fresh nexus.db
                    pass
                except sqlite3.IntegrityError:
                    # Already exists, could reinforce here
                    pass
            conn.commit()

    def _archive_and_purge(self, thoughts: List[Dict]):
        now = datetime.now().isoformat()
        with sqlite3.connect(ARCHIVE_DB) as conn:
            for t in thoughts:
                conn.execute(
                    "INSERT INTO archived_memories (original_id, timestamp, content, metadata, archived_at) VALUES (?, ?, ?, ?, ?)",
                    (str(t.get('id')), t.get('timestamp'), t.get('content'), t.get('metadata', ''), now)
                )
            conn.commit()
        
        # Delete from being.db
        ids = [t['id'] for t in thoughts]
        with sqlite3.connect(BEING_DB) as conn:
            conn.execute(
                f"DELETE FROM thoughts WHERE id IN ({','.join('?'*len(ids))})",
                ids
            )
            conn.commit()
