"""Tests for the self-modification module."""
import os
import tempfile
from pathlib import Path

import pytest

from self_modify import SelfModification, IMPROVEMENT_AREAS, MAX_PENDING_PROPOSALS


@pytest.fixture
def tmp_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield Path(path)
    os.unlink(path)


class TestSelfModification:
    def test_init_creates_db(self, tmp_db):
        sm = SelfModification(db_path=tmp_db)
        assert tmp_db.exists()

    def test_propose_improvement(self, tmp_db):
        sm = SelfModification(db_path=tmp_db)
        p = sm.propose_improvement()
        assert p is not None
        assert "id" in p
        assert p["status"] == "pending"
        assert p["area"] in IMPROVEMENT_AREAS
        assert len(p["description"]) > 10
        assert "observed_need" in p
        assert len(sm.proposals) == 1

    def test_propose_improvement_specific_area(self, tmp_db):
        sm = SelfModification(db_path=tmp_db)
        p = sm.propose_improvement(area="creativity")
        assert p["area"] == "creativity"

    def test_approve_reject_apply(self, tmp_db):
        sm = SelfModification(db_path=tmp_db)
        p = sm.propose_improvement()
        pid = p["id"]

        sm.approve_proposal(pid)
        sm2 = SelfModification(db_path=tmp_db)
        loaded = [x for x in sm2.proposals if x["id"] == pid]
        assert loaded[0]["status"] == "approved"

        sm.reject_proposal(pid)
        sm3 = SelfModification(db_path=tmp_db)
        loaded = [x for x in sm3.proposals if x["id"] == pid]
        assert loaded[0]["status"] == "rejected"

        sm.apply_proposal(pid)
        sm4 = SelfModification(db_path=tmp_db)
        loaded = [x for x in sm4.proposals if x["id"] == pid]
        assert loaded[0]["status"] == "applied"

    def test_get_pending_proposals(self, tmp_db):
        sm = SelfModification(db_path=tmp_db)
        assert sm.get_pending_proposals() == []
        p = sm.propose_improvement()
        assert len(sm.get_pending_proposals()) == 1
        sm.approve_proposal(p["id"])
        # Reload to see DB changes
        sm2 = SelfModification(db_path=tmp_db)
        assert len(sm2.get_pending_proposals()) == 0

    def test_max_pending_limit(self, tmp_db):
        sm = SelfModification(db_path=tmp_db)
        for _ in range(MAX_PENDING_PROPOSALS + 2):
            sm.propose_improvement()
        assert sm._count_pending() <= MAX_PENDING_PROPOSALS

    def test_format_self_modify_prompt(self, tmp_db):
        sm = SelfModification(db_path=tmp_db)
        assert sm.format_self_modify_prompt() == ""
        sm.propose_improvement()
        prompt = sm.format_self_modify_prompt()
        assert "IMPROVEMENTS" in prompt
        assert "pending" not in prompt  # status not in prompt format

    def test_format_self_modify_prompt_empty(self, tmp_db):
        sm = SelfModification(db_path=tmp_db)
        assert sm.format_self_modify_prompt() == ""
