"""Local and semantic embedding backends for Chroma / DRIFT memory."""

from __future__ import annotations

import hashlib
import logging
import math
from typing import Any, List

import threading

import numpy as np
import os

try:
    import torch

    os.environ["TORCH_DEVICE"] = "cpu"
    torch.set_default_device("cpu")
    _TORCH_AVAILABLE = True
except ImportError:
    torch = None  # type: ignore[assignment]
    _TORCH_AVAILABLE = False

try:
    from chromadb.api.types import Documents, Embeddings
except ImportError:
    Documents = List  # type: ignore[misc,assignment]
    Embeddings = List  # type: ignore[misc,assignment]


logger = logging.getLogger(__name__)

_OFFLINE_EXC_NAMES = {
    "ProxyError",
    "ConnectionError",
    "ConnectTimeout",
    "ConnectError",
    "ReadTimeout",
    "HTTPError",
    "LocalEntryNotFoundError",
    "OfflineModeIsEnabled",
}


def _is_offline_error(exc: BaseException) -> bool:
    """True when exc, or anything it was raised from, means 'could not fetch'."""
    seen: set[int] = set()
    cur: BaseException | None = exc
    while cur is not None and id(cur) not in seen:
        seen.add(id(cur))
        if type(cur).__name__ in _OFFLINE_EXC_NAMES:
            return True
        cur = cur.__cause__ or cur.__context__
    return False


class SemanticEmbeddingFunction:
    """sentence-transformers MiniLM vectors (384-dim by default).

    If the model cannot be fetched (no network, blocked proxy, cold cache) this
    degrades to LocalEmbeddingFunction rather than failing every embed call.
    The decision is made once and held for the process, so a single collection
    never mixes 384-dim and 64-dim vectors.
    """

    def __init__(self) -> None:
        self._model = None
        self._fallback = None
        self._unavailable = False
        self._lock = threading.Lock()

    def _local_fallback(self):
        if self._fallback is None:
            self._fallback = LocalEmbeddingFunction()
        return self._fallback

    def _encoder(self):
        """Return the loaded model, or None when it is unreachable offline."""
        with self._lock:
            if self._model is None and not self._unavailable:
                from sentence_transformers import SentenceTransformer
                import torch

                # Ensure we are on CPU before loading
                torch.set_default_device("cpu")
                try:
                    self._model = SentenceTransformer("all-MiniLM-L6-v2", device="cpu")
                except Exception as e:
                    if "meta tensor" in str(e):
                        # Attempt recovery if somehow still on meta
                        try:
                            self._model = SentenceTransformer(
                                "all-MiniLM-L6-v2", device="cpu", trust_remote_code=True
                            )
                        except Exception:
                            raise e
                    elif _is_offline_error(e):
                        self._unavailable = True
                        logger.warning(
                            "Could not fetch the semantic embedding model (%s: %s). "
                            "Falling back to LocalEmbeddingFunction for this process; "
                            "retrieval quality will be reduced.",
                            type(e).__name__,
                            e,
                        )
                    else:
                        raise e
        return self._model

    @property
    def dim(self) -> int:
        enc = self._encoder()
        if enc is None:
            return self._local_fallback()._dim
        return int(enc.get_sentence_embedding_dimension())

    def name(self) -> str:
        return "semantic_minilm"

    def embed_query(self, input=None):
        """Single-string embedding. Parameter name matches Chroma's protocol."""
        if input is None:
            raise TypeError("embed_query requires a text input")
        enc = self._encoder()
        if enc is None:
            return self._local_fallback().embed_query(input)
        if isinstance(input, list):
            if not input:
                raise TypeError("embed_query requires a non-empty text input")
            batch = enc.encode(input, convert_to_numpy=True)
            return [np.asarray(v, dtype=np.float64) for v in batch]
        v = enc.encode(input, convert_to_numpy=True)
        return np.asarray(v, dtype=np.float64)

    def embed_documents(self, texts: List[str]) -> List[np.ndarray]:
        if not texts:
            return []
        enc = self._encoder()
        if enc is None:
            return self._local_fallback().embed_documents(texts)
        batch = enc.encode(texts, convert_to_numpy=True)
        return [np.asarray(row, dtype=np.float64) for row in batch]

    def __call__(self, input: Documents) -> Embeddings:
        raw = self.embed_documents(list(input))
        # raw is ndarrays from the model, or plain lists from the offline fallback.
        return [e.tolist() if hasattr(e, "tolist") else list(e) for e in raw]

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

    def embed_query(self, input=None):
        if input is None:
            raise TypeError("embed_query requires a text input")
        if isinstance(input, list):
            if not input:
                raise TypeError("embed_query requires a non-empty text input")
            return [self._vec(t) for t in input]
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


def get_default_embedding_function():
    # Allow forcing local embeddings for offline/test environments.
    # INFJ_EMBEDDING_MODE=local is the documented switch used by scripts/run_mcp.sh.
    if os.environ.get("DRIFT_USE_LOCAL_EMBEDDINGS", "").lower() in ("1", "true", "yes"):
        return LocalEmbeddingFunction()
    if os.environ.get("INFJ_EMBEDDING_MODE", "").strip().lower() == "local":
        return LocalEmbeddingFunction()

    try:
        import sentence_transformers  # noqa: F401
    except ImportError:
        return LocalEmbeddingFunction()
    # SemanticEmbeddingFunction loads lazily and degrades to the local hash
    # embedder on its own if the model turns out to be unreachable.
    return SemanticEmbeddingFunction()
