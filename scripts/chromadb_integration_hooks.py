#!/usr/bin/env python3
"""ChromaDB integration hooks for DRIFT benchmark runners.

These helpers are intentionally lightweight and optional. The module can be
imported even when `chromadb` is not installed; the first actual Chroma-backed
operation will raise a clear error in that case.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import chromadb
    from chromadb.config import Settings
    from chromadb.utils import embedding_functions
except Exception as exc:  # pragma: no cover - exercised only when deps exist
    chromadb = None  # type: ignore[assignment]
    Settings = None  # type: ignore[assignment]
    embedding_functions = None  # type: ignore[assignment]
    _CHROMA_IMPORT_ERROR = exc
else:  # pragma: no cover - import-time guard
    _CHROMA_IMPORT_ERROR = None

DEFAULT_CHROMA_PERSIST_DIR = "./chroma_db"
DEFAULT_COLLECTION_NAME = "drift_memory"
DEFAULT_EMBEDDING_MODEL = "all-MiniLM-L6-v2"

SCRIPTS_DIR = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[1]
for candidate in (str(SCRIPTS_DIR), str(ROOT)):
    if candidate not in sys.path:
        sys.path.insert(0, candidate)

class ChromaMemoryStore:
    """Reusable persistent ChromaDB wrapper for DRIFT-style memory stores."""

    def __init__(
        self,
        persist_directory: str = DEFAULT_CHROMA_PERSIST_DIR,
        collection_name: str = DEFAULT_COLLECTION_NAME,
        embedding_model_name: str = DEFAULT_EMBEDDING_MODEL,
    ) -> None:
        if chromadb is None or Settings is None or embedding_functions is None:
            raise RuntimeError(
                "chromadb is not available in this environment; "
                "install it before using the ChromaDB backend."
            ) from _CHROMA_IMPORT_ERROR

        self.client = chromadb.PersistentClient(
            path=persist_directory,
            settings=Settings(anonymized_telemetry=False),
        )
        self.embedding_function = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name=embedding_model_name
        )
        self.collection = self.client.get_or_create_collection(
            name=collection_name,
            embedding_function=self.embedding_function,
            metadata={"hnsw:space": "cosine"},
        )

    def query(
        self,
        query_text: str,
        n_results: int = 50,
        where: Optional[Dict[str, Any]] = None,
        include: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        include = include or ["documents", "metadatas", "embeddings", "distances"]
        return self.collection.query(
            query_texts=[query_text],
            n_results=n_results,
            where=where,
            include=include,
        )


_memory_store: Optional[ChromaMemoryStore] = None


def get_memory_store(
    *,
    persist_directory: str = DEFAULT_CHROMA_PERSIST_DIR,
    collection_name: str = DEFAULT_COLLECTION_NAME,
    embedding_model_name: str = DEFAULT_EMBEDDING_MODEL,
) -> ChromaMemoryStore:
    """Return a process-local singleton Chroma store."""
    global _memory_store
    if _memory_store is None:
        try:
            from memory_store_config import get_config
        except Exception:
            _memory_store = ChromaMemoryStore(
                persist_directory=persist_directory,
                collection_name=collection_name,
                embedding_model_name=embedding_model_name,
            )
        else:
            cfg = get_config()
            _memory_store = ChromaMemoryStore(
                persist_directory=cfg.persist_directory,
                collection_name=cfg.collection_name,
                embedding_model_name=cfg.embedding_model,
            )
    return _memory_store


def load_dataset(dataset_path: str | Path) -> List[Dict[str, Any]]:
    """Load benchmark cases from a list JSON or a {'cases': [...]} document."""
    path = Path(dataset_path).expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(f"Dataset file not found: {path}")

    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        if "cases" in data and isinstance(data["cases"], list):
            return data["cases"]
        if "case_id" in data:
            return [data]
    raise ValueError(
        f"Unsupported dataset format in {path}. "
        "Expected a list of cases or an object with a 'cases' key."
    )


def get_query_embedding(query: str) -> List[float]:
    """Embed the query using the same model attached to the collection."""
    store = get_memory_store()
    embedding = store.embedding_function([query])[0]
    return embedding.tolist() if hasattr(embedding, "tolist") else list(embedding)


def get_candidates_for_case(
    case: Dict[str, Any],
    *,
    n_results: int = 50,
    apply_metadata_filter: bool = True,
) -> List[Dict[str, Any]]:
    """Retrieve Chroma-backed candidate memories for a labeled benchmark case."""
    store = get_memory_store()
    where_filter: Optional[Dict[str, Any]] = None
    if apply_metadata_filter:
        category = case.get("category")
        if category:
            where_filter = {"category": {"$eq": category}}

    chroma_results = store.query(
        query_text=case["query"],
        n_results=n_results,
        where=where_filter,
        include=["documents", "metadatas", "embeddings", "distances"],
    )

    ids = chroma_results.get("ids", [[]])[0]
    documents = chroma_results.get("documents", [[]])[0]
    metadatas = chroma_results.get("metadatas", [[]])[0]
    embeddings = chroma_results.get("embeddings", [[]])[0]

    candidates: List[Dict[str, Any]] = []
    for idx, mem_id in enumerate(ids):
        meta = metadatas[idx] if idx < len(metadatas) and metadatas else {}
        emb = embeddings[idx] if idx < len(embeddings) and embeddings else []
        candidate = {
            "id": mem_id,
            "memory_id": meta.get("memory_id", mem_id),
            "embedding": emb,
            "document": documents[idx] if idx < len(documents) else "",
            "timestamp": float(meta.get("timestamp", 0.0)),
            "salience": float(meta.get("salience", 0.5)),
            "emotional_valence": float(meta.get("emotional_valence", 0.0)),
            "emotional_intensity": float(meta.get("emotional_intensity", 0.5)),
            "retention_score": float(meta.get("retention_score", meta.get("retention_decay", 0.8))),
            "trust_level": float(meta.get("trust_level", 0.75)),
            "has_conflict": bool(meta.get("has_conflict", False)),
            "conflict_status": meta.get("conflict_status", "none"),
            **{
                k: v
                for k, v in meta.items()
                if k
                not in {
                    "memory_id",
                    "timestamp",
                    "salience",
                    "emotional_valence",
                    "emotional_intensity",
                    "retention_score",
                    "retention_decay",
                    "trust_level",
                    "has_conflict",
                    "conflict_status",
                }
            },
        }
        candidates.append(candidate)

    return candidates


def wire_chromadb_hooks_into_runner() -> None:
    """Monkey-patch the standalone runner with the ChromaDB-backed hooks."""
    import standalone_dmu_comparison_runner as runner  # local import by design

    runner.load_dataset = load_dataset
    runner.get_candidates_for_case = get_candidates_for_case
    runner.get_query_embedding = get_query_embedding

    print("[chromadb_integration] Hooks wired successfully to ChromaDB backend.")


if __name__ == "__main__":
    print("ChromaDB integration hooks module loaded.")
    print("Use wire_chromadb_hooks_into_runner() or import the functions directly.")
