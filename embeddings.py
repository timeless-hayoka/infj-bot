"""embeddings.py — Semantic and legacy embedding functions for ChromaDB.

Provides a sentence-transformers based embedding function for real semantic
search, while keeping the old hash-based fallback available.
"""

import logging
from typing import Any, Dict, List

import numpy as np

logger = logging.getLogger("infj_bot")


class SemanticEmbeddingFunction:
    """ChromaDB-compatible embedding function using sentence-transformers."""

    _model = None
    _model_name = "all-MiniLM-L6-v2"
    _dim = 384

    def __init__(self, model_name: str = None):
        if model_name:
            self._model_name = model_name
        self._load_model()

    def _load_model(self):
        if SemanticEmbeddingFunction._model is None:
            try:
                from sentence_transformers import SentenceTransformer
                logger.info("Loading semantic embedding model: %s", self._model_name)
                SemanticEmbeddingFunction._model = SentenceTransformer(self._model_name)
                logger.info("Semantic embedding model loaded.")
            except Exception:
                logger.exception("Failed to load sentence-transformers model")
                raise
        self.model = SemanticEmbeddingFunction._model

    def __call__(self, input: List[str]) -> List[np.ndarray]:
        return self.embed_documents(input)

    def embed_documents(self, documents: List[str]) -> List[np.ndarray]:
        if not documents:
            return []
        embeddings = self.model.encode(documents, show_progress_bar=False, convert_to_numpy=True)
        # Ensure we return a list of 1-D arrays
        if embeddings.ndim == 1:
            embeddings = embeddings.reshape(1, -1)
        return [emb.astype(np.float32) for emb in embeddings]

    def embed_query(self, query: str) -> np.ndarray:
        if isinstance(query, list):
            return self.embed_documents(query)
        emb = self.model.encode(query, show_progress_bar=False, convert_to_numpy=True)
        return emb.astype(np.float32)

    def name(self) -> str:
        return f"semantic_embedding:{self._model_name}"

    def get_config(self) -> Dict[str, Any]:
        return {"model_name": self._model_name}

    @classmethod
    def build_from_config(cls, config: Dict[str, Any]) -> "SemanticEmbeddingFunction":
        return cls(model_name=config.get("model_name", cls._model_name))

    @property
    def dim(self) -> int:
        return self._dim


class LocalEmbeddingFunction:
    """Legacy hash-bucket embedding for backward compatibility.

    Not recommended for new collections — use SemanticEmbeddingFunction.
    """

    import hashlib
    import re

    @staticmethod
    def name():
        return "local_hash_embedding"

    def __call__(self, input):
        return self.embed_documents(input)

    def embed_query(self, input):
        if isinstance(input, str):
            return self.embed_documents([input])[0]
        return self.embed_documents(input)

    def embed_documents(self, input):
        import hashlib
        import re

        embeddings = []
        for document in input:
            buckets = [0.0] * 64
            tokens = re.findall(r"[a-z0-9]+", document.lower())
            for token in tokens:
                digest = hashlib.sha256(token.encode("utf-8")).digest()
                bucket = int.from_bytes(digest[:2], "big") % len(buckets)
                sign = 1.0 if digest[2] % 2 == 0 else -1.0
                buckets[bucket] += sign
            magnitude = sum(value * value for value in buckets) ** 0.5 or 1.0
            embeddings.append([value / magnitude for value in buckets])
        return embeddings

    def get_config(self) -> Dict[str, Any]:
        return {}

    @classmethod
    def build_from_config(cls, config: Dict[str, Any]) -> "LocalEmbeddingFunction":
        return cls()


def get_default_embedding_function():
    """Return the default embedding function (semantic)."""
    try:
        return SemanticEmbeddingFunction()
    except Exception:
        logger.warning("Semantic embeddings unavailable, falling back to hash embeddings.")
        return LocalEmbeddingFunction()
