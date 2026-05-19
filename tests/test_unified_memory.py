import pytest
import datetime
import tempfile
import os
import anyio
from typing import Any

from infj_bot.core.unified_memory import MemoryManager, Event, MemoryEntry

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
    
    event = Event(type="test_event", content="The sky is blue today.", timestamp=datetime.datetime.now())
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
