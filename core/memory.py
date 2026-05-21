import chromadb
import uuid
import datetime
import hashlib
import json
import re
import asyncio
from pathlib import Path
from typing import List, Optional, Tuple

from infj_bot.core.config import PERSIST_DIRECTORY
from infj_bot.core.embeddings import (
    get_default_embedding_function,
    LocalEmbeddingFunction,
    SemanticEmbeddingFunction,
)
from infj_bot.core.unified_memory import MemoryManager, Event


# ── Secret scrubbing ──────────────────────────────────────────────
# Patterns are ordered from most specific to least specific.
# An allowlist prevents false positives on legit hex/base64-looking data.

SECRET_PATTERNS = [
    # PEM private keys (most specific)
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.S),
    # API key / token / password with common prefixes (highly specific)
    re.compile(
        r"(?i)(api[_-]?key|auth[_-]?token|access[_-]?token|bearer\s+|password|secret|private[_-]?key)\s*[=:]\s*['\"]?[A-Za-z0-9_\-/+=]{8,}['\"]?"
    ),
    # Generic long hex that looks like a key (less specific — guarded by allowlist)
    re.compile(r"\b[a-f0-9]{64}\b"),  # 64-char hex (SHA-256, common API key length)
    re.compile(r"\b[a-f0-9]{40}\b"),  # 40-char hex (SHA-1, GitHub token-like)
    # Long base64-ish strings with suspicious context
    re.compile(
        r"(?i)(key|token|secret|password)\s*[=:]\s*['\"]?[A-Za-z0-9_\-/+=]{24,}['\"]?"
    ),
]

# Patterns that look like secrets but are actually normal content
LEGIT_HEX_ALLOWLIST = [
    re.compile(r"^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$"),  # UUID
    re.compile(r"^[a-f0-9]{7,40}$"),  # short git hashes
    re.compile(r"^0x[a-f0-9]+$"),  # Ethereum / hex addresses
]


def _looks_like_secret(value: str) -> bool:
    """Check if a matched string is likely a secret (not allowlisted)."""
    for pattern in LEGIT_HEX_ALLOWLIST:
        if pattern.match(value):
            return False
    return True


def _run_async(coro):
    """Helper to run async code from sync methods."""
    try:
        loop = asyncio.get_running_loop()
        # Create a fire-and-forget task if we are already in an event loop
        loop.create_task(coro)
    except RuntimeError:
        # No running event loop
        asyncio.run(coro)


class DriftMemory:
    LEGACY_COLLECTION = "infj_companion_memories"
    SEMANTIC_COLLECTION = "infj_semantic_memories"

    def __init__(self, persist_directory=None, embedding_function=None, use_semantic=True):
        if persist_directory is None:
            persist_directory = str(PERSIST_DIRECTORY)

        self.use_semantic = use_semantic
        if embedding_function is None:
            if use_semantic:
                embedding_function = get_default_embedding_function()
            else:
                embedding_function = LocalEmbeddingFunction()

        self.embedding_function = embedding_function
        
        # Phase 4.1/4.3: Initialize Unified Memory Spine directly
        self.unified_manager = MemoryManager(
            chroma_path=persist_directory,
            db_path=str(Path(persist_directory) / "unified_memory.db")
        )

        # For backwards compatibility with external scripts, expose the collection name
        if isinstance(self.embedding_function, SemanticEmbeddingFunction):
            self.collection_name = self.SEMANTIC_COLLECTION
        else:
            self.collection_name = self.LEGACY_COLLECTION

    def scrub_text(self, text: str) -> str:
        """Redact secrets from text, with allowlist protection."""
        scrubbed = text
        for pattern in SECRET_PATTERNS:
            for match in pattern.finditer(scrubbed):
                matched_text = match.group()
                if _looks_like_secret(matched_text):
                    scrubbed = scrubbed[: match.start()] + "[REDACTED]" + scrubbed[match.end() :]
        return scrubbed

    def save_interaction(self, user_input, bot_output, mode="companion", emotion=None, importance=0.5, dissonance=None):
        timestamp = datetime.datetime.now().isoformat()
        safe_user_input = self.scrub_text(user_input)
        safe_bot_output = self.scrub_text(bot_output)
        content = f"user: {safe_user_input}\nBot: {safe_bot_output}"

        emotion = emotion or {"label": "neutral"}
        dissonance = dissonance or {"score": 0.0, "values": [], "markers": []}
        
        metadata = {
            "type": "interaction",
            "timestamp": timestamp,
            "last_updated": timestamp,
            "mode": mode,
            "emotion": emotion.get("label", "neutral"),
            "emotion_secondary": emotion.get("secondary", "neutral"),
            "emotion_confidence": float(emotion.get("confidence", 0.0)),
            "emotion_valence": float(emotion.get("valence", 0.0)),
            "emotion_arousal": float(emotion.get("arousal", 0.0)),
            "emotion_intensity": float(emotion.get("intensity", 0.0)),
            "emotion_needs": emotion.get("needs", ""),
            "emotion_detector": emotion.get("detector", "unknown"),
            "dissonance_score": float(dissonance.get("score", 0.0)),
            "dissonance_values": ",".join(dissonance.get("values", [])),
            "dissonance_markers": ",".join(dissonance.get("markers", [])),
            "dissonance_detector": dissonance.get("detector", "unknown"),
            "importance": float(importance),
        }
        
        # Phase 4.3: Write to MemoryManager spine
        event = Event(type="interaction", content=content, timestamp=datetime.datetime.fromisoformat(timestamp))
        _run_async(self.unified_manager.remember(event, metadata))

    def learn_concept(self, concept_name, description, tags=None, importance=0.8):
        timestamp = datetime.datetime.now().isoformat()
        content = f"Concept: {concept_name}\nDescription: {description}"

        metadata = {
            "type": "learned_knowledge",
            "timestamp": timestamp,
            "last_updated": timestamp,
            "concept": concept_name,
            "tags": ",".join(tags or []),
            "importance": float(importance),
        }

        event = Event(type="learned_knowledge", content=content, timestamp=datetime.datetime.fromisoformat(timestamp))
        _run_async(self.unified_manager.remember(event, metadata))

    def save_reflection(self, title, summary, tags=None, importance=0.9):
        timestamp = datetime.datetime.now().isoformat()
        title = title or f"reflection-{timestamp}"
        content = f"Reflection: {title}\nSummary: {summary}"
        
        metadata = {
            "type": "reflection",
            "timestamp": timestamp,
            "last_updated": timestamp,
            "title": title,
            "tags": ",".join(tags or []),
            "importance": float(importance),
        }
        
        event = Event(type="reflection", content=content, timestamp=datetime.datetime.fromisoformat(timestamp))
        _run_async(self.unified_manager.remember(event, metadata))

    def save_thought(self, thought_text, thought_type="autonomous", source="being", emotion_tag=None, importance=0.6):
        """Save a bot thought to semantic memory so it can be retrieved later."""
        timestamp = datetime.datetime.now().isoformat()
        safe_text = self.scrub_text(thought_text)
        content = f"Thought ({thought_type} from {source}): {safe_text}"
        
        metadata = {
            "type": "thought",
            "timestamp": timestamp,
            "last_updated": timestamp,
            "thought_type": thought_type,
            "source": source,
            "emotion": emotion_tag or "neutral",
            "importance": float(importance),
        }
        
        event = Event(type="thought", content=content, timestamp=datetime.datetime.fromisoformat(timestamp))
        _run_async(self.unified_manager.remember(event, metadata))

    def save_bug_record(self, title, document, record_type="bug_note", tags=None, importance=0.85):
        timestamp = datetime.datetime.now().isoformat()
        safe_title = title.strip() or f"{record_type}-{timestamp}"
        safe_document = self.scrub_text(document)
        record_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"infj-{record_type}:{safe_title}:{timestamp}"))
        
        metadata = {
            "type": record_type,
            "timestamp": timestamp,
            "last_updated": timestamp,
            "title": safe_title,
            "tags": ",".join(tags or []),
            "importance": float(importance),
        }
        
        event = Event(type=record_type, content=safe_document, timestamp=datetime.datetime.fromisoformat(timestamp))
        _run_async(self.unified_manager.remember(event, metadata))
        
        return record_id

    def retrieve_thoughts(self, query="", n_results=5):
        """Retrieve the bot's own thoughts, optionally filtered by semantic similarity."""
        if query:
            entries = self.unified_manager.recall_sync(query, limit=n_results)
            # Filter by type thought
            entries = [e for e in entries if e.metadata.get("type") == "thought"]
            return [(e.event.content, e.metadata) for e in entries]
        else:
            entries = self.unified_manager.get_recent_sync("thought", limit=n_results)
            return [(e.event.content, e.metadata) for e in entries]

    def recent_records(self, record_type, limit=5):
        entries = self.unified_manager.get_recent_sync(record_type, limit=limit)
        return [(e.event.content, e.metadata) for e in entries]

    def retrieve_context(self, query, n_results=5, include_metadata=False, rerank=True):
        """Retrieve memory with hybrid reranking (semantic + importance + recency)."""
        # MemoryManager recall already handles Ebbinghaus recency & hybrid scoring.
        # We can just fetch via recall_sync.
        entries = self.unified_manager.recall_sync(query, limit=n_results)
        
        if not include_metadata:
            return "\n---\n".join([e.event.content for e in entries])
        return [(e.event.content, e.metadata) for e in entries]

    def retrieve_context_ranked(self, query, n_results=5):
        """
        Retrieve memory context re-ranked by the DMU (Dynamic Memory Unit).

        This applies a second re-ranking pass on top of the Unified Memory Spine's
        internal DMU scoring, using an alternative time-decay model with explicit
        emotional-weight damping. Results are logged to the DMU telemetry database.

        Falls back to standard `retrieve_context` if the DMU module is unavailable.
        """
        try:
            from infj_bot.memory.dmu import rank_memory_entries, format_ranked_entries
            entries = self.unified_manager.recall_sync(query, limit=n_results * 2)
            if not entries:
                return ""
            ranked = rank_memory_entries(entries, query=query, top_k=n_results)
            return format_ranked_entries(ranked)
        except Exception:
            # Safe fallback: if DMU fails for any reason, use standard retrieval
            return self.retrieve_context(query, n_results=n_results)

    def _rerank(self, documents, metadatas, distances, top_k=5) -> Tuple[List[str], List[dict]]:
        # Deprecated: _rerank logic is now handled internally by MemoryManager.recall
        pass

    def search(self, query, n_results=5):
        return self.retrieve_context(query, n_results=n_results, include_metadata=True)

    def recent_interactions(self, limit=10):
        entries = self.unified_manager.get_recent_sync("interaction", limit=limit)
        return [e.event.content for e in entries]

    def interaction_count(self):
        return self.unified_manager.count_sync("interaction")

    def forget_concept(self, concept_name):
        self.unified_manager.forget_concept_sync(concept_name)

    def edit_concept(self, concept_name, new_description):
        """Update an existing concept's description."""
        # We first forget the old concept to avoid duplicates
        self.unified_manager.forget_concept_sync(concept_name)
        
        timestamp = datetime.datetime.now().isoformat()
        content = f"Concept: {concept_name}\nDescription: {new_description}"

        metadata = {
            "type": "learned_knowledge",
            "timestamp": timestamp,
            "last_updated": timestamp,
            "concept": concept_name,
            "tags": "edited",
            "importance": 0.8,
        }
        
        event = Event(type="learned_knowledge", content=content, timestamp=datetime.datetime.fromisoformat(timestamp))
        _run_async(self.unified_manager.remember(event, metadata))

    def export_json(self, path):
        # We export what we can from unified manager via recall
        # This is a bit of a hack for backwards compatibility
        pass # Will implement fully later if needed, but for now we skip or return 0
        return 0

    def import_json(self, path):
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        records = payload.get("records", [])
        if not records:
            return 0
        bad = [r for r in records if not all(k in r for k in ("id", "document"))]
        if bad:
            raise ValueError(f"Import failed: {len(bad)} records missing required fields.")
        # Skipping for phase 4.2 unless required, but validation passed
        return 0

    def count(self):
        return self.unified_manager.count_sync()

    def prune_interactions(self, max_age_days=30, max_importance=0.4, force=False):
        """Remove old interactions with low importance. Returns count removed."""
        now = datetime.datetime.now()
        stats = self.unified_manager.prune_sync(now=now, threshold=0.1, force=force) # Uses standard Ebbinghaus
        return stats.sqlite_deleted

    def auto_prune(self, turn_count: int = 0, force: bool = False) -> int:
        """Auto-prune low-value memories based on turn count or time elapsed.

        Returns number of memories pruned.
        """
        stats = self.unified_manager.auto_prune_sync(turn_count=turn_count, force=force)
        return stats.sqlite_deleted

    def migrate_from_legacy(self) -> int:
        """Deprecated."""
        return 0


if __name__ == "__main__":
    # Quick test
    memory = DriftMemory()
    print("Memory System Initialized.")
