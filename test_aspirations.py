"""Tests for the aspirational self module."""
import os
import tempfile
from pathlib import Path

import pytest

from aspirations import AspirationalSelf, MAX_ACTIVE_ASPIRATIONS


@pytest.fixture
def tmp_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield Path(path)
    os.unlink(path)


class TestAspirationalSelf:
    def test_init_creates_db(self, tmp_db):
        asp = AspirationalSelf(db_path=tmp_db)
        assert tmp_db.exists()
        assert asp.aspirations == []

    def test_dream_aspiration(self, tmp_db):
        asp = AspirationalSelf(db_path=tmp_db)
        a = asp.dream_aspiration()
        assert a is not None
        assert "id" in a
        assert "description" in a
        assert a["progress"] == 0.0
        assert a["status"] == "active"
        assert len(asp.aspirations) == 1

    def test_advance_progress(self, tmp_db):
        asp = AspirationalSelf(db_path=tmp_db)
        a = asp.dream_aspiration()
        aid = a["id"]
        asp.advance_progress(aid, 0.2)
        assert asp.aspirations[0]["progress"] == 0.2
        asp.advance_progress(aid, 0.9)
        assert asp.aspirations[0]["progress"] == 1.0

    def test_complete_aspiration(self, tmp_db):
        asp = AspirationalSelf(db_path=tmp_db)
        a = asp.dream_aspiration()
        asp.complete_aspiration(a["id"])
        # Verify via reload
        asp2 = AspirationalSelf(db_path=tmp_db)
        loaded = [x for x in asp2.aspirations if x["id"] == a["id"]]
        assert len(loaded) == 0  # active filter excludes completed

    def test_max_active_limit(self, tmp_db):
        asp = AspirationalSelf(db_path=tmp_db)
        for _ in range(MAX_ACTIVE_ASPIRATIONS + 2):
            asp.dream_aspiration()
        active = [a for a in asp.aspirations if a["status"] == "active"]
        assert len(active) <= MAX_ACTIVE_ASPIRATIONS

    def test_deepen_existing(self, tmp_db):
        asp = AspirationalSelf(db_path=tmp_db)
        a = asp.dream_aspiration()
        result = asp.deepen_existing()
        assert result is not None
        assert result["id"] == a["id"]
        assert result["progress"] > 0.0

    def test_get_core_purpose(self, tmp_db):
        asp = AspirationalSelf(db_path=tmp_db)
        purpose = asp.get_core_purpose()
        assert "companion" in purpose.lower()

    def test_record_vision(self, tmp_db):
        asp = AspirationalSelf(db_path=tmp_db)
        asp.record_vision("I see myself understanding silence.")
        assert len(asp.visions) == 1
        assert "silence" in asp.visions[0]["vision_text"]

    def test_record_growth_action(self, tmp_db):
        asp = AspirationalSelf(db_path=tmp_db)
        asp.record_growth_action("practice", "Practiced holding silence", impact=0.3)
        # No exception means success

    def test_format_aspirational_prompt(self, tmp_db):
        asp = AspirationalSelf(db_path=tmp_db)
        # Always shows purpose
        prompt = asp.format_aspirational_prompt()
        assert "PURPOSE" in prompt
        asp.dream_aspiration()
        prompt = asp.format_aspirational_prompt()
        assert "growth directions" in prompt
        assert "█" in prompt or "░" in prompt

    def test_generate_manifesto(self, tmp_db):
        asp = AspirationalSelf(db_path=tmp_db)
        asp.dream_aspiration()
        manifesto = asp.generate_manifesto()
        assert "What I stand for" in manifesto
        assert "Purpose" in manifesto or "companion" in manifesto.lower()
