"""Local and semantic embedding backends for Chroma / DRIFT memory."""

from __future__ import annotations

import hashlib
import math
from typing import Any, List

import numpy as np
from chromadb.api.types import Documents, Embeddings


class SemanticEmbeddingFunction:
    """sentence-transformers MiniLM vectors (384-dim by default)."""

    def __init__(self) -> None:
        self._model = None

    def _encoder(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer("all-MiniLM-L6-v2")
        return self._model

    @property
    def dim(self) -> int:
        return int(self._encoder().get_sentence_embedding_dimension())

    def name(self) -> str:
        return "semantic_minilm"

    def embed_query(self, input: str | None = None) -> np.ndarray:
        """Single-string embedding. Parameter name matches Chroma's protocol."""
        if input is None:
            raise TypeError("embed_query requires a text input")
        enc = self._encoder()
        v = enc.encode(input, convert_to_numpy=True)
        return np.asarray(v, dtype=np.float64)

    def embed_documents(self, texts: List[str]) -> List[np.ndarray]:
        if not texts:
            return []
        enc = self._encoder()
        batch = enc.encode(texts, convert_to_numpy=True)
        return [np.asarray(row, dtype=np.float64) for row in batch]

    def __call__(self, input: Documents) -> Embeddings:
        raw = self.embed_documents(list(input))
        return [e.tolist() for e in raw]

    def get_config(self) -> dict[str, Any]:
        return {"kind": "semantic_minilm", "dim": self.dim}

    @classmethod
    def build_from_config(cls, config: dict) -> SemanticEmbeddingFunction:
        return cls()


class LocalEmbeddingFunction:
    """Deterministic 64-d hash embedding, L2-normalized (tests / offline fallback)."""

    _dim = 64

    @staticmethod
    def name() -> str:
        return "local_hash_embedding"

    def embed_query(self, input: str | None = None) -> List[float]:
        if input is None:
            raise TypeError("embed_query requires a text input")
        return self._vec(input)

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        return [self._vec(t) for t in texts]

    def __call__(self, input: Documents) -> Embeddings:
        return self.embed_documents(list(input))  # type: ignore[return-value]

    def _vec(self, text: str) -> List[float]:
        h = hashlib.sha256(text.encode("utf-8")).digest()
        # Stretch 32 bytes to 64 floats in [-1, 1]
        raw = (h * 2)[: self._dim]
        vals = [((b / 255.0) * 2.0 - 1.0) for b in raw]
        mag = math.sqrt(sum(v * v for v in vals)) or 1.0
        return [v / mag for v in vals]


def get_default_embedding_function() -> SemanticEmbeddingFunction:
    return SemanticEmbeddingFunction()
