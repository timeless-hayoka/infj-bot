import chromadb
import uuid
import datetime
import hashlib
import json
import re
from pathlib import Path
from typing import List, Optional, Tuple

from config import INFJ_MEMORY_SEARCH_TOP_K, PERSIST_DIRECTORY
from embeddings import get_default_embedding_function, LocalEmbeddingFunction, SemanticEmbeddingFunction


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
    re.compile(r"^[a-f0-9]{32}$"),  # MD5
    re.compile(r"^[a-f0-9]{64}$"),  # SHA-256
    re.compile(r"^[a-f0-9]{128}$"),  # SHA-512
]


def _looks_like_secret(value: str) -> bool:
    """Check if a matched string is likely a secret (not allowlisted)."""
    for pattern in LEGIT_HEX_ALLOWLIST:
        if pattern.match(value):
            return False
    return True


class InfjMemory:
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
        self.client = chromadb.PersistentClient(path=persist_directory)

        # Determine collection name based on embedding type
        if isinstance(self.embedding_function, SemanticEmbeddingFunction):
            self.collection_name = self.SEMANTIC_COLLECTION
        else:
            self.collection_name = self.LEGACY_COLLECTION

        self.collection = self.client.get_or_create_collection(
            name=self.collection_name,
            embedding_function=self.embedding_function,
        )

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
        content = f"Jude: {safe_user_input}\nBot: {safe_bot_output}"

        emotion = emotion or {"label": "neutral"}
        dissonance = dissonance or {"score": 0.0, "values": [], "markers": []}
        self.collection.add(
            documents=[content],
            ids=[str(uuid.uuid4())],
            metadatas=[
                {
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
            ],
        )

    def learn_concept(self, concept_name, description, tags=None, importance=0.8):
        timestamp = datetime.datetime.now().isoformat()
        content = f"Concept: {concept_name}\nDescription: {description}"

        self.collection.upsert(
            documents=[content],
            ids=[str(uuid.uuid5(uuid.NAMESPACE_DNS, f"infj-concept:{concept_name}"))],
            metadatas=[
                {
                    "type": "learned_knowledge",
                    "timestamp": timestamp,
                    "last_updated": timestamp,
                    "concept": concept_name,
                    "tags": ",".join(tags or []),
                    "importance": float(importance),
                }
            ],
        )

    def save_reflection(self, title, summary, tags=None, importance=0.9):
        timestamp = datetime.datetime.now().isoformat()
        title = title or f"reflection-{timestamp}"
        content = f"Reflection: {title}\nSummary: {summary}"
        self.collection.upsert(
            documents=[content],
            ids=[str(uuid.uuid5(uuid.NAMESPACE_DNS, f"infj-reflection:{title}"))],
            metadatas=[
                {
                    "type": "reflection",
                    "timestamp": timestamp,
                    "last_updated": timestamp,
                    "title": title,
                    "tags": ",".join(tags or []),
                    "importance": float(importance),
                }
            ],
        )

    def save_thought(self, thought_text, thought_type="autonomous", source="being", emotion_tag=None, importance=0.6):
        """Save a bot thought to semantic memory so it can be retrieved later."""
        timestamp = datetime.datetime.now().isoformat()
        safe_text = self.scrub_text(thought_text)
        content = f"Thought ({thought_type} from {source}): {safe_text}"
        self.collection.add(
            documents=[content],
            ids=[str(uuid.uuid4())],
            metadatas=[
                {
                    "type": "thought",
                    "timestamp": timestamp,
                    "last_updated": timestamp,
                    "thought_type": thought_type,
                    "source": source,
                    "emotion": emotion_tag or "neutral",
                    "importance": float(importance),
                }
            ],
        )

    def save_bug_record(self, title, document, record_type="bug_note", tags=None, importance=0.85):
        timestamp = datetime.datetime.now().isoformat()
        safe_title = title.strip() or f"{record_type}-{timestamp}"
        safe_document = self.scrub_text(document)
        record_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"infj-{record_type}:{safe_title}:{timestamp}"))
        self.collection.add(
            documents=[safe_document],
            ids=[record_id],
            metadatas=[
                {
                    "type": record_type,
                    "timestamp": timestamp,
                    "last_updated": timestamp,
                    "title": safe_title,
                    "tags": ",".join(tags or []),
                    "importance": float(importance),
                }
            ],
        )
        return record_id

    def retrieve_thoughts(self, query="", n_results=None):
        """Retrieve the bot's own thoughts, optionally filtered by semantic similarity."""
        if n_results is None:
            n_results = INFJ_MEMORY_SEARCH_TOP_K
        if query:
            results = self.collection.query(
                query_texts=[query],
                n_results=n_results,
                where={"type": "thought"},
            )
        else:
            results = self.collection.get(
                where={"type": "thought"},
                include=["documents", "metadatas"],
            )
            # Sort by timestamp descending and limit
            docs = results.get("documents", [])
            metas = results.get("metadatas", [])
            combined = list(zip(docs, metas))
            combined.sort(key=lambda x: x[1].get("timestamp", ""), reverse=True)
            combined = combined[:n_results]
            return [(doc, meta) for doc, meta in combined]
        docs = results.get("documents", [[]])[0]
        metas = results.get("metadatas", [[]])[0]
        return list(zip(docs, metas))

    def recent_records(self, record_type, limit=5):
        results = self.collection.get(
            where={"type": record_type},
            include=["documents", "metadatas"],
        )
        records = list(zip(results.get("documents", []), results.get("metadatas", [])))
        records.sort(key=lambda record: record[1].get("timestamp", ""), reverse=True)
        return records[:limit]

    def retrieve_context(self, query, n_results=None, include_metadata=False, rerank=True):
        """Retrieve memory with hybrid reranking (semantic + importance + recency)."""
        if n_results is None:
            n_results = INFJ_MEMORY_SEARCH_TOP_K
        results = self.collection.query(
            query_texts=[query],
            n_results=n_results * 3 if rerank else n_results,
        )
        documents = [doc for sublist in results["documents"] for doc in sublist]
        metadatas = [meta for sublist in results.get("metadatas", []) for meta in sublist]
        distances = [d for sublist in results.get("distances", []) for d in sublist]

        if rerank and documents:
            documents, metadatas = self._rerank(documents, metadatas, distances, top_k=n_results)

        if not include_metadata:
            return "\n---\n".join(documents)
        return list(zip(documents, metadatas))

    def _rerank(self, documents, metadatas, distances, top_k=5) -> Tuple[List[str], List[dict]]:
        now = datetime.datetime.now()
        scored = []
        for doc, meta, dist in zip(documents, metadatas, distances):
            importance = float(meta.get("importance", 0.5))
            try:
                ts = datetime.datetime.fromisoformat(meta.get("timestamp", ""))
                age_hours = max(0, (now - ts).total_seconds() / 3600.0)
            except (ValueError, TypeError):
                age_hours = 8760  # 1 year default

            # Recency decay: half-life of 24 hours for interactions, 7 days for knowledge
            record_type = meta.get("type", "interaction")
            half_life_hours = 24.0 if record_type == "interaction" else 168.0
            recency_score = 0.5 ** (age_hours / half_life_hours)

            # Semantic similarity: Chroma L2 distance → cosine-like score
            # For normalized embeddings (MiniLM), L2 dist ≈ sqrt(2-2*cos), so:
            # cos_sim ≈ 1 - (dist^2)/2 for small distances
            sim_score = max(0.0, 1.0 - (dist * dist) / 2.0)

            # Hybrid score weights
            score = sim_score * 0.55 + importance * 0.25 + recency_score * 0.20
            scored.append((score, doc, meta))
        scored.sort(key=lambda x: x[0], reverse=True)
        top = scored[:top_k]
        return [doc for _s, doc, _m in top], [meta for _s, _d, meta in top]

    def search(self, query, n_results=None):
        """Search memories and return list of (document, metadata) pairs."""
        if n_results is None:
            n_results = INFJ_MEMORY_SEARCH_TOP_K
        return self.retrieve_context(query, n_results=n_results, include_metadata=True)

    def recent_interactions(self, limit=10):
        results = self.collection.get(
            where={"type": "interaction"},
            include=["documents", "metadatas"],
        )
        records = list(zip(results.get("documents", []), results.get("metadatas", [])))
        records.sort(key=lambda record: record[1].get("timestamp", ""), reverse=True)
        return [document for document, _metadata in records[:limit]]

    def interaction_count(self):
        results = self.collection.get(where={"type": "interaction"}, include=[])
        return len(results.get("ids", []))

    def forget_concept(self, concept_name):
        concept_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"infj-concept:{concept_name}"))
        self.collection.delete(ids=[concept_id])

    def edit_concept(self, concept_name, new_description):
        """Update an existing concept's description."""
        concept_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"infj-concept:{concept_name}"))
        timestamp = datetime.datetime.now().isoformat()
        content = f"Concept: {concept_name}\nDescription: {new_description}"
        self.collection.upsert(
            documents=[content],
            ids=[concept_id],
            metadatas=[
                {
                    "type": "learned_knowledge",
                    "timestamp": timestamp,
                    "last_updated": timestamp,
                    "concept": concept_name,
                    "tags": "edited",
                    "importance": 0.8,
                }
            ],
        )

    def export_json(self, path):
        results = self.collection.get(include=["documents", "metadatas"])
        payload = {
            "exported_at": datetime.datetime.now().isoformat(),
            "collection": self.collection_name,
            "records": [
                {"id": item_id, "document": document, "metadata": metadata}
                for item_id, document, metadata in zip(
                    results.get("ids", []),
                    results.get("documents", []),
                    results.get("metadatas", []),
                )
            ],
        }
        Path(path).write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")
        return len(payload["records"])

    def import_json(self, path):
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        records = payload.get("records", [])
        if not records:
            return 0
        bad = [r for r in records if not all(k in r for k in ("id", "document"))]
        if bad:
            raise ValueError(f"Import failed: {len(bad)} records missing required fields.")
        self.collection.upsert(
            ids=[record["id"] for record in records],
            documents=[record["document"] for record in records],
            metadatas=[record.get("metadata", {}) for record in records],
        )
        return len(records)

    def count(self):
        return self.collection.count()

    def prune_interactions(self, max_age_days=30, max_importance=0.4):
        """Remove old interactions with low importance. Returns count removed."""
        cutoff = datetime.datetime.now() - datetime.timedelta(days=max_age_days)
        results = self.collection.get(
            where={"type": "interaction"},
            include=["metadatas"],
        )
        ids_to_delete = []
        for item_id, metadata in zip(results.get("ids", []), results.get("metadatas", [])):
            try:
                ts = datetime.datetime.fromisoformat(metadata.get("timestamp", ""))
            except (ValueError, TypeError):
                continue
            importance = float(metadata.get("importance", 0.0))
            if ts < cutoff and importance <= max_importance:
                ids_to_delete.append(item_id)
        if ids_to_delete:
            self.collection.delete(ids=ids_to_delete)
        return len(ids_to_delete)

    def migrate_from_legacy(self) -> int:
        """Migrate records from the legacy hash-based collection to the semantic collection.

        Returns the number of records migrated.
        """
        if not isinstance(self.embedding_function, SemanticEmbeddingFunction):
            raise RuntimeError("Migration only meaningful when using semantic embeddings.")

        try:
            legacy = self.client.get_collection(
                name=self.LEGACY_COLLECTION,
                embedding_function=LocalEmbeddingFunction(),
            )
        except Exception:
            return 0

        results = legacy.get(include=["documents", "metadatas"])
        ids = results.get("ids", [])
        documents = results.get("documents", [])
        metadatas = results.get("metadatas", [])

        if not ids:
            return 0

        # Batch add to semantic collection
        batch_size = 100
        migrated = 0
        for i in range(0, len(ids), batch_size):
            batch_ids = ids[i : i + batch_size]
            batch_docs = documents[i : i + batch_size]
            batch_meta = metadatas[i : i + batch_size]
            self.collection.upsert(
                ids=batch_ids,
                documents=batch_docs,
                metadatas=batch_meta,
            )
            migrated += len(batch_ids)

        return migrated


if __name__ == "__main__":
    # Quick test
    memory = InfjMemory()
    print("Memory System Initialized.")
    print(f"Collection: {memory.collection_name}")
    print(f"Embedding: {memory.embedding_function.name()}")
