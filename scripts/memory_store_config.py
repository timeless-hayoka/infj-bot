from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class MemoryStoreConfig:
    """Configuration for ChromaDB-backed memory retrieval."""

    persist_directory: str = os.getenv("DRIFT_CHROMA_PERSIST_DIR", "./chroma_db")
    collection_name: str = os.getenv("DRIFT_MEMORY_COLLECTION", "drift_memory")
    embedding_model: str = os.getenv("DRIFT_EMBEDDING_MODEL", "all-MiniLM-L6-v2")
    default_n_results: int = int(os.getenv("DRIFT_DEFAULT_N_RESULTS", "50"))


def get_config() -> MemoryStoreConfig:
    return MemoryStoreConfig()


def get_chroma_store():
    from chromadb_integration_hooks import ChromaMemoryStore

    cfg = get_config()
    return ChromaMemoryStore(
        persist_directory=cfg.persist_directory,
        collection_name=cfg.collection_name,
        embedding_model_name=cfg.embedding_model,
    )
