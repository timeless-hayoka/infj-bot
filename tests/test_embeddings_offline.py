"""Tests for choosing and using the offline embedding backend."""

import sys
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest

from drift.core import embeddings


@pytest.fixture(autouse=True)
def clear_embedding_modes(monkeypatch):
    monkeypatch.delenv("DRIFT_USE_LOCAL_EMBEDDINGS", raising=False)
    monkeypatch.delenv("INFJ_EMBEDDING_MODE", raising=False)


@pytest.fixture
def model_loader(monkeypatch):
    loader = Mock()
    monkeypatch.setitem(sys.modules, "sentence_transformers", SimpleNamespace(SentenceTransformer=loader))
    monkeypatch.setitem(sys.modules, "torch", SimpleNamespace(set_default_device=Mock()))
    return loader


@pytest.mark.parametrize("name", [
    "ProxyError", "ConnectionError", "ConnectTimeout", "ConnectError",
    "ReadTimeout", "HTTPError", "LocalEntryNotFoundError", "OfflineModeIsEnabled",
])
def test_offline_error_recognizes_each_supported_exception(name):
    error = type(name, (Exception,), {})("unavailable")
    assert embeddings._is_offline_error(error)


def test_offline_error_checks_cause_context_and_cycles():
    offline = ConnectionError("offline")
    wrapper = RuntimeError("wrapper")
    wrapper.__cause__ = offline
    assert embeddings._is_offline_error(wrapper)
    wrapper.__cause__ = None
    wrapper.__context__ = offline
    assert embeddings._is_offline_error(wrapper)
    wrapper.__context__ = RuntimeError("other")
    wrapper.__context__.__cause__ = wrapper
    assert not embeddings._is_offline_error(wrapper)


@pytest.mark.parametrize("value", ["1", "true", "TRUE", "yes", "Yes"])
def test_drift_switch_forces_local_without_loading_model(monkeypatch, model_loader, value):
    monkeypatch.setenv("DRIFT_USE_LOCAL_EMBEDDINGS", value)
    assert isinstance(embeddings.get_default_embedding_function(), embeddings.LocalEmbeddingFunction)
    model_loader.assert_not_called()


@pytest.mark.parametrize("value", ["local", " LOCAL ", "Local"])
def test_infj_mode_forces_local(monkeypatch, model_loader, value):
    monkeypatch.setenv("INFJ_EMBEDDING_MODE", value)
    assert isinstance(embeddings.get_default_embedding_function(), embeddings.LocalEmbeddingFunction)
    model_loader.assert_not_called()


def test_default_selects_semantic_lazily_and_ignores_other_modes(monkeypatch, model_loader):
    monkeypatch.setenv("DRIFT_USE_LOCAL_EMBEDDINGS", "0")
    monkeypatch.setenv("INFJ_EMBEDDING_MODE", "semantic")
    assert isinstance(embeddings.get_default_embedding_function(), embeddings.SemanticEmbeddingFunction)
    model_loader.assert_not_called()


def test_default_uses_local_if_sentence_transformers_missing(monkeypatch):
    monkeypatch.setitem(sys.modules, "sentence_transformers", None)
    assert isinstance(embeddings.get_default_embedding_function(), embeddings.LocalEmbeddingFunction)


def test_unreachable_model_falls_back_once_for_all_embedding_operations(model_loader, caplog):
    error = RuntimeError("model load failed")
    error.__cause__ = ConnectionError("offline")
    model_loader.side_effect = error
    backend = embeddings.SemanticEmbeddingFunction()
    local = embeddings.LocalEmbeddingFunction()
    texts = ["first", "second"]

    assert backend.dim == 64
    assert backend.get_config() == {"kind": "semantic_minilm", "dim": 64}
    assert backend.embed_query(texts[0]) == local.embed_query(texts[0])
    assert backend.embed_query(texts) == local.embed_query(texts)
    assert backend.embed_documents(texts) == local.embed_documents(texts)
    assert backend(texts) == local(texts)
    assert backend.embed_documents([]) == []
    with pytest.raises(TypeError):
        backend.embed_query([])
    with pytest.raises(TypeError):
        backend.embed_query(None)
    model_loader.assert_called_once_with("all-MiniLM-L6-v2", device="cpu")
    assert "Falling back to LocalEmbeddingFunction" in caplog.text


def test_loaded_model_keeps_semantic_vectors_and_reuses_model(model_loader):
    model = model_loader.return_value
    model.get_sentence_embedding_dimension.return_value = 3
    model.encode.side_effect = lambda texts, **kwargs: (
        [1, 2, 3] if isinstance(texts, str) else [[1, 2, 3] for _ in texts]
    )
    backend = embeddings.SemanticEmbeddingFunction()
    assert backend.dim == 3
    assert backend.get_config()["dim"] == 3
    assert backend.embed_query("one").tolist() == [1, 2, 3]
    assert backend.embed_query("one").dtype == np.float64
    assert [v.tolist() for v in backend.embed_query(["one", "two"])] == [[1, 2, 3]] * 2
    assert backend(["one", "two"]) == [[1, 2, 3]] * 2
    model_loader.assert_called_once_with("all-MiniLM-L6-v2", device="cpu")


def test_unrelated_model_error_is_propagated_and_can_be_retried(model_loader):
    error = ValueError("bad model configuration")
    model_loader.side_effect = [error, Mock(get_sentence_embedding_dimension=Mock(return_value=384))]
    backend = embeddings.SemanticEmbeddingFunction()
    with pytest.raises(ValueError, match="bad model configuration"):
        backend.dim
    assert backend.dim == 384
    assert model_loader.call_count == 2


def test_meta_tensor_recovery_still_loads_semantic_model(model_loader):
    model = Mock(get_sentence_embedding_dimension=Mock(return_value=384))
    model_loader.side_effect = [RuntimeError("meta tensor"), model]
    backend = embeddings.SemanticEmbeddingFunction()
    assert backend.dim == 384
    assert model_loader.call_args_list[1].kwargs == {"device": "cpu", "trust_remote_code": True}


def test_failed_meta_tensor_recovery_preserves_original_error(model_loader):
    original = RuntimeError("meta tensor")
    model_loader.side_effect = [original, RuntimeError("recovery failed")]
    backend = embeddings.SemanticEmbeddingFunction()
    with pytest.raises(RuntimeError) as exc_info:
        backend.dim
    assert exc_info.value is original
    assert model_loader.call_count == 2
