import pytest
import datetime
import tempfile
import os
import anyio

from drift.core.unified_memory import MemoryManager, Event


@pytest.fixture
def temp_dirs():
    with tempfile.TemporaryDirectory() as sqlite_dir:
        with tempfile.TemporaryDirectory() as chroma_dir:
            yield sqlite_dir, chroma_dir


@pytest.mark.anyio
async def test_memory_manager_remember_and_recall(temp_dirs):
    sqlite_dir, chroma_dir = temp_dirs
    db_path = os.path.join(sqlite_dir, "test.db")
    mm = MemoryManager(db_path=db_path, chroma_path=chroma_dir)

    event = Event(
        type="test_event",
        content="The sky is blue today.",
        timestamp=datetime.datetime.now(),
    )
    uid = await mm.remember(event, metadata={"importance": 0.8})
    assert uid is not None

    results = await mm.recall("sky color")
    assert len(results) >= 1
    assert results[0].unified_id == uid
    assert results[0].event.content == "The sky is blue today."
    assert results[0].metadata["importance"] == 0.8


@pytest.mark.anyio
async def test_memory_manager_get_set_state(temp_dirs):
    sqlite_dir, chroma_dir = temp_dirs
    db_path = os.path.join(sqlite_dir, "test.db")
    mm = MemoryManager(db_path=db_path, chroma_path=chroma_dir)

    await mm.set_state("mode", "focus")
    val = await mm.get_state("mode")
    assert val == "focus"

    # TTL test
    await mm.set_state("temp", "value", ttl=datetime.timedelta(milliseconds=1))
    await anyio.sleep(0.01)
    val = await mm.get_state("temp", default="missing")
    assert val == "missing"


@pytest.mark.anyio
async def test_memory_manager_ebbinghaus_prune(temp_dirs):
    sqlite_dir, chroma_dir = temp_dirs
    db_path = os.path.join(sqlite_dir, "test.db")
    mm = MemoryManager(db_path=db_path, chroma_path=chroma_dir)

    # Save an old, low importance memory
    old_ts = datetime.datetime.now() - datetime.timedelta(days=365)
    event1 = Event(type="test", content="Forgot this long ago.", timestamp=old_ts)
    uid1 = await mm.remember(event1, metadata={"importance": 0.01})

    # Save a recent, high importance memory
    recent_ts = datetime.datetime.now()
    event2 = Event(type="test", content="Remember this always.", timestamp=recent_ts)
    uid2 = await mm.remember(event2, metadata={"importance": 0.99})

    # Prune evaluated AT current time
    stats = await mm.prune(now=datetime.datetime.now(), threshold=0.1, force=True)
    # The old memory should be pruned, the recent high importance one kept
    assert stats.chroma_deleted == 1
    assert stats.sqlite_deleted == 1

    # Query fidelity check: verify exact deletion
    res1 = await mm.recall("Forgot this long ago.")
    res2 = await mm.recall("Remember this always.")

    assert not any(r.unified_id == uid1 for r in res1)
    assert len(res2) > 0
    assert res2[0].unified_id == uid2


def test_initialization_without_chromadb_preserves_sqlite_state(monkeypatch, tmp_path):
    from drift.core import unified_memory

    monkeypatch.setattr(unified_memory, "_CHROMADB_AVAILABLE", False)
    monkeypatch.setattr(unified_memory, "chromadb", None)
    db_path = tmp_path / "nested" / "state.db"
    mm = MemoryManager(db_path=str(db_path), chroma_path=str(tmp_path / "chroma"))

    assert mm.collection is None
    assert mm.embedding_function is None
    mm.set_state_sync("mode", "offline")
    assert mm.get_state_sync("mode") == "offline"
    assert mm.get_state_sync("missing", default="unknown") == "unknown"
    assert db_path.is_file()


def test_initialization_with_chromadb_uses_default_embedding(monkeypatch, tmp_path):
    from types import SimpleNamespace
    from unittest.mock import Mock
    from drift.core import embeddings, unified_memory

    embedding = object()
    collection = object()
    client = Mock()
    client.get_or_create_collection.return_value = collection
    persistent_client = Mock(return_value=client)
    monkeypatch.setattr(unified_memory, "_CHROMADB_AVAILABLE", True)
    monkeypatch.setattr(unified_memory, "chromadb", SimpleNamespace(PersistentClient=persistent_client))
    monkeypatch.setattr(embeddings, "get_default_embedding_function", lambda: embedding)
    chroma_path = str(tmp_path / "chroma")

    mm = MemoryManager(db_path=str(tmp_path / "state.db"), chroma_path=chroma_path)

    persistent_client.assert_called_once_with(path=chroma_path)
    client.get_or_create_collection.assert_called_once_with(
        name="infj_unified_memory_v2", embedding_function=embedding
    )
    assert mm.embedding_function is embedding
    assert mm.collection is collection
