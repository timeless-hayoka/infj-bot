"""Smoke tests for Elysium Phase 5 hive engine (async)."""

import pytest
import tempfile
from pathlib import Path

from infj_bot.core.hive.nexus import NexusSelfModel, ActiveTension
from infj_bot.core.hive.council_member import (
    CouncilMember,
    CouncilRole,
    Council,
    MemoryViewFilter,
    Proposal,
)
from infj_bot.core.hive.elysium import ElysiumEngine, DeliberationResult


class TestNexusSelfModel:
    def test_init_and_state_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "nexus.db"
            nexus = NexusSelfModel(db_path=db)
            nexus.set_goal("test goal", priority=0.8)
            nexus.reflect(trigger="test", insight="insight")
            state = nexus.get_state()
            assert state["current_goals"][0] == "test goal"
            assert state["reflection_count"] == 1

    def test_integrate_decision(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "nexus.db"
            nexus = NexusSelfModel(db_path=db)
            nexus.integrate_decision(
                goal="grow",
                resolution="plant seeds",
                moral_weight=0.7,
                narrative_weight=0.6,
                council_votes={"Logic": 0.8, "Aura": 0.4},
            )
            assert nexus.state.decision_count == 1
            hist = nexus.get_decision_history()
            assert len(hist) == 1
            assert hist[0]["goal"] == "grow"

    def test_tension_resolution(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "nexus.db"
            nexus = NexusSelfModel(db_path=db)
            nexus.state.active_tensions.append(
                ActiveTension(name="safety vs growth", poles=["safety", "growth"])
            )
            nexus._save_state()
            nexus.resolve_tension("safety vs growth", "compromise")
            assert len(nexus.state.active_tensions) == 0


class TestCouncilMember:
    def test_member_proposal_without_brain(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "council.db"
            member = CouncilMember(role=CouncilRole.LOGIC, db_path=db)
            prop = member.generate_proposal("should we refactor", [])
            assert prop.role == "Logic"
            assert "[Logic]" in prop.text
            assert 0 <= prop.confidence <= 1

    def test_member_proposal_with_mock_brain(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "council.db"
            member = CouncilMember(role=CouncilRole.ETHOS, db_path=db)

            class FakeBrain:
                primary_model_name = "fake-model"

                def _generate(self, model, system, prompt):
                    return "We should prioritize harm reduction."

            prop = member.generate_proposal("should we ship now", [], brain=FakeBrain())
            assert "harm reduction" in prop.text
            assert prop.confidence > 0.5

    def test_critique(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "council.db"
            member = CouncilMember(role=CouncilRole.ETHOS, db_path=db)
            target = Proposal(
                role="Logic", text="do it", confidence=0.9, moral_weight=0.3
            )
            crit = member.critique("Logic", target)
            assert crit.from_role == "Ethos"
            assert crit.target_role == "Logic"
            assert 0 <= crit.score <= 1

    def test_memory_filter(self):
        f = MemoryViewFilter(
            topic_boosts=["shadow"], emotional_bias=-0.2, excluded_tags=["spam"]
        )
        score = f.score_memory({"tags": ["shadow"], "emotional": 0.2})
        assert score > 0
        score_excluded = f.score_memory({"tags": ["spam"], "emotional": 0.5})
        assert score_excluded == 0.0

    def test_filter_property(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "council.db"
            member = CouncilMember(role=CouncilRole.AURA, db_path=db)
            assert member.filter.emotional_bias == 0.3

    def test_council_container(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "council.db"
            council = Council(db_path=db)
            assert len(council.all()) == 7
            status = council.status()
            assert "Logic" in status
            assert "Aura" in status


class TestElysiumEngine:
    @pytest.mark.anyio
    async def test_decide_basic_without_memory(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "elysium.db"
            nexus_db = Path(tmp) / "nexus.db"
            council_db = Path(tmp) / "council.db"
            nexus = NexusSelfModel(db_path=nexus_db)
            council = Council(db_path=council_db)
            elysium = ElysiumEngine(nexus=nexus, council=council, db_path=db)
            result = await elysium.decide("should we write more tests")
            assert isinstance(result, DeliberationResult)
            assert result.goal == "should we write more tests"
            assert result.winning_role in list(result.council_votes.keys()) + [
                "none",
                "Nexus",
            ]
            assert result.resolution

    @pytest.mark.anyio
    async def test_reflect(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "elysium.db"
            nexus_db = Path(tmp) / "nexus.db"
            council_db = Path(tmp) / "council.db"
            elysium = ElysiumEngine(
                nexus=NexusSelfModel(db_path=nexus_db),
                council=Council(db_path=council_db),
                db_path=db,
            )
            insight = await elysium.reflect(trigger="test")
            assert isinstance(insight, str)
            assert "coherence" in insight.lower() or "energy" in insight.lower()

    def test_council_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "elysium.db"
            nexus_db = Path(tmp) / "nexus.db"
            council_db = Path(tmp) / "council.db"
            elysium = ElysiumEngine(
                nexus=NexusSelfModel(db_path=nexus_db),
                council=Council(db_path=council_db),
                db_path=db,
            )
            status = elysium.council_status()
            assert "nexus" in status
            assert "council" in status
            assert "deliberation_count" in status

    @pytest.mark.anyio
    async def test_decide_with_mock_brain(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "elysium.db"
            nexus_db = Path(tmp) / "nexus.db"
            council_db = Path(tmp) / "council.db"

            class FakeBrain:
                primary_model_name = "fake-model"

                def _generate(self, model, system, prompt):
                    return f"Proposal from {system.split(chr(10))[0]}: proceed with caution."

            elysium = ElysiumEngine(
                nexus=NexusSelfModel(db_path=nexus_db),
                council=Council(db_path=council_db),
                db_path=db,
                brain=FakeBrain(),
            )
            result = await elysium.decide("should we refactor the auth layer")
            # With brain wired, proposals contain LLM text
            assert isinstance(result, DeliberationResult)
            assert result.goal == "should we refactor the auth layer"

    @pytest.mark.anyio
    async def test_fractal_memory_filtering_in_decide(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "elysium.db"
            nexus_db = Path(tmp) / "nexus.db"
            council_db = Path(tmp) / "council.db"

            class FakeMemory:
                async def recall(self, query, limit=20, decay_weight=1.0):
                    class FakeEvent:
                        type = "test"
                        content = "memory about shadow"
                        timestamp = __import__("datetime").datetime.now()

                    class FakeEntry:
                        unified_id = "1"
                        event = FakeEvent()
                        metadata = {
                            "salience": 0.8,
                            "emotional": 0.2,
                            "tags": ["shadow"],
                            "dmu": 0.7,
                        }

                    return [FakeEntry()]

                async def remember(self, event, metadata):
                    return "id-1"

            elysium = ElysiumEngine(
                nexus=NexusSelfModel(db_path=nexus_db),
                council=Council(db_path=council_db),
                db_path=db,
                memory=FakeMemory(),
            )
            result = await elysium.decide("explore the shadow")
            # FakeMemory.recall was called via _ignite
            assert isinstance(result, DeliberationResult)
