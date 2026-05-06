"""Tests for semantic and legacy embedding functions."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pytest

from embeddings import (
    LocalEmbeddingFunction,
    SemanticEmbeddingFunction,
    get_default_embedding_function,
)


class TestSemanticEmbeddingFunction:
    @pytest.fixture(scope="class")
    def embedder(self):
        return SemanticEmbeddingFunction()

    def test_name(self, embedder):
        assert "semantic" in embedder.name()

    def test_embed_single(self, embedder):
        emb = embedder.embed_query("coffee and quiet mornings")
        assert isinstance(emb, np.ndarray)
        assert emb.ndim == 1
        assert emb.shape[0] == embedder.dim

    def test_embed_documents(self, embedder):
        docs = ["coffee", "tea", "fox jumps"]
        embs = embedder.embed_documents(docs)
        assert len(embs) == 3
        for emb in embs:
            assert emb.shape[0] == embedder.dim

    def test_semantic_similarity(self, embedder):
        emb1 = embedder.embed_query("I love drinking coffee in the morning")
        emb2 = embedder.embed_query("A cup of tea at dawn is peaceful")
        emb3 = embedder.embed_query("The quick brown fox jumps over the lazy dog")

        def cosine(a, b):
            return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))

        sim_coffee_tea = cosine(emb1, emb2)
        sim_coffee_fox = cosine(emb1, emb3)
        assert sim_coffee_tea > sim_coffee_fox
        assert sim_coffee_tea > 0.2  # Related concepts should have some similarity

    def test_callable(self, embedder):
        embs = embedder(["hello world", "goodbye world"])
        assert len(embs) == 2

    def test_empty_documents(self, embedder):
        assert embedder.embed_documents([]) == []

    def test_config_roundtrip(self, embedder):
        config = embedder.get_config()
        restored = SemanticEmbeddingFunction.build_from_config(config)
        assert restored.name() == embedder.name()


class TestLocalEmbeddingFunction:
    def test_name(self):
        assert LocalEmbeddingFunction.name() == "local_hash_embedding"

    def test_embed_single(self):
        emb = LocalEmbeddingFunction().embed_query("hello")
        assert len(emb) == 64

    def test_embed_documents(self):
        embs = LocalEmbeddingFunction().embed_documents(["a", "b"])
        assert len(embs) == 2
        assert len(embs[0]) == 64

    def test_normalization(self):
        emb = LocalEmbeddingFunction().embed_query("test")
        magnitude = sum(v * v for v in emb) ** 0.5
        assert abs(magnitude - 1.0) < 1e-6


class TestDefaultEmbeddingFunction:
    def test_returns_semantic(self):
        emb_fn = get_default_embedding_function()
        assert isinstance(emb_fn, SemanticEmbeddingFunction)
