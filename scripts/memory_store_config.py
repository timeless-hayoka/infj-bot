from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

_chroma_store: Optional[object] = None


@dataclass(frozen=True)
class MemoryStoreConfig:
    """Configuration for ChromaDB-backed memory retrieval.

    All values can be overridden via environment variables.
    """

    persist_directory: str
    collection_name: str
    embedding_model: str
    default_n_results: int


def get_config() -> MemoryStoreConfig:
    """Return the active memory store configuration."""
    return MemoryStoreConfig(
        persist_directory=os.getenv("DRIFT_CHROMA_PERSIST_DIR", "./chroma_db"),
        collection_name=os.getenv("DRIFT_MEMORY_COLLECTION", "drift_memory"),
        embedding_model=os.getenv("DRIFT_EMBEDDING_MODEL", "all-MiniLM-L6-v2"),
        default_n_results=int(os.getenv("DRIFT_DEFAULT_N_RESULTS", "50")),
    )


def get_chroma_store():
    """Factory returning a configured ChromaMemoryStore singleton."""
    global _chroma_store
    if _chroma_store is None:
        from chromadb_integration_hooks import ChromaMemoryStore

        cfg = get_config()
        _chroma_store = ChromaMemoryStore(
            persist_directory=cfg.persist_directory,
            collection_name=cfg.collection_name,
            embedding_model_name=cfg.embedding_model,
        )
    return _chroma_store


def reset_chroma_store() -> None:
    """Clear the process-local Chroma store singleton (tests only)."""
    global _chroma_store
    _chroma_store = None
