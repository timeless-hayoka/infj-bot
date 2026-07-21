"""Elysium — Phase 5 First-Class Hive Engine.

The Nexus Loop:
  1. Ignition          → DMU-weighted memory recall via MemoryManager
  2. Parallel Proposal → each council member generates a stance (LLM-backed if brain wired)
  3. Critique Tournament → members score each other's proposals
  4. Nexus Integration → moral + narrative weighted synthesis
  5. Final Resolution  → decision + proper Event memory consolidation
"""

import asyncio
import json
import logging
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from .nexus import NexusSelfModel, get_nexus
from .council_member import Council, CouncilRole, Proposal, Critique
from ..unified_memory import MemoryManager, Event
from ..config import DATA_DIR

logger = logging.getLogger("drift.hive.elysium")

ELYSIUM_DB = DATA_DIR / "elysium.db"


@dataclass
class DeliberationResult:
    """Output of a complete Nexus Loop."""

    goal: str
    resolution: str
    council_votes: Dict[str, float]
    winning_role: str
    moral_weight: float
    narrative_weight: float
    nexus_override: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "goal": self.goal,
            "resolution": self.resolution,
            "council_votes": self.council_votes,
            "winning_role": self.winning_role,
            "moral_weight": self.moral_weight,
            "narrative_weight": self.narrative_weight,
            "nexus_override": self.nexus_override,
            "timestamp": self.timestamp,
        }


class ElysiumEngine:
    """Main engine for Phase 5 distributed frontal lobe."""

    def __init__(
        self,
        memory: Optional[Any] = None,
        brain: Optional[Any] = None,
        nexus: Optional[NexusSelfModel] = None,
        council: Optional[Council] = None,
        db_path: Optional[Path] = None,
    ):
        # Normalize memory: accept DriftMemory or unified MemoryManager
        self._raw_memory = memory
        self.memory = self._normalize_memory(memory)
        self.brain = brain
        self.nexus = nexus or get_nexus()
        self.council = council or Council()
        self.db_path = str(db_path or ELYSIUM_DB)
        self._init_db()

    def _normalize_memory(self, memory) -> Optional[MemoryManager]:
        if memory is None:
            return None
        if hasattr(memory, "unified_manager"):
            return memory.unified_manager
        if isinstance(memory, MemoryManager):
            return memory
        return None

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS elysium_deliberations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT,
                    goal TEXT,
                    resolution TEXT,
                    winning_role TEXT,
                    council_votes TEXT,
                    moral_weight REAL,
                    narrative_weight REAL,
                    nexus_override TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS elysium_reflections (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT,
                    trigger TEXT,
                    insight TEXT,
                    coherence_delta REAL
                )
            """)
            conn.commit()

    # ------------------------------------------------------------------
    # Public Async API
    # ------------------------------------------------------------------

    async def decide(self, goal: str) -> DeliberationResult:
        """Run the full Nexus Loop on a goal and return the resolution."""
        logger.info("[Elysium] Deciding: %s", goal)

        # 1. Ignition — DMU-weighted memory recall
        memories = await self._ignite(goal)

        # 2. Parallel Proposal Generation (with fractal memory filtering)
        proposals = await self._generate_proposals(goal, memories)

        # 3. Critique Tournament
        critiques = await self._critique_tournament(proposals)

        # 4. Nexus Integration (moral + narrative weighted)
        integrated = self._nexus_integrate(proposals, critiques)

        # 5. Final Resolution + Memory Consolidation
        result = self._resolve(goal, integrated, proposals, critiques)

        # Persist
        self._persist_deliberation(result)
        self.nexus.integrate_decision(
            goal=result.goal,
            resolution=result.resolution,
            moral_weight=result.moral_weight,
            narrative_weight=result.narrative_weight,
            council_votes=result.council_votes,
            nexus_override=result.nexus_override,
        )

        # Record win for the winning role
        winner_role = self._role_from_name(result.winning_role)
        if winner_role:
            self.council.get(winner_role).record_win()

        # Drain all members slightly
        for member in self.council.all():
            member.drain(0.05)

        # Store decision to memory with proper Event
        await self._consolidate_memory(goal, result)

        logger.info("[Elysium] Resolved via %s", result.winning_role)
        return result

    async def reflect(self, trigger: str = "background") -> str:
        """Continuous background reflection — ask the council to introspect."""
        logger.debug("[Elysium] Reflecting on trigger: %s", trigger)

        # Quick council temperature check
        statuses = self.council.status()
        lowest_energy = min((s["energy_level"], name) for name, s in statuses.items())
        highest_tension = (
            self.nexus.state.active_tensions[0].name
            if self.nexus.state.active_tensions
            else "none"
        )

        insight = (
            f"Council energy lowest in {lowest_energy[1]} ({lowest_energy[0]:.2f}). "
            f"Active tension: {highest_tension}. "
            f"Nexus coherence: {self.nexus.state.coherence_score:.2f}. "
            f"Recent decisions: {self.nexus.state.decision_count}."
        )

        self.nexus.reflect(trigger=trigger, insight=insight)
        self._persist_reflection(trigger, insight, 0.0)
        return insight

    def council_status(self) -> Dict[str, Any]:
        """Return current status of all council members + Nexus."""
        return {
            "nexus": self.nexus.get_state(),
            "council": self.council.status(),
            "deliberation_count": self.nexus.state.decision_count,
            "last_integration": self.nexus.state.last_integration_time,
        }

    def get_deliberation_history(self, limit: int = 20) -> List[Dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM elysium_deliberations ORDER BY timestamp DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Nexus Loop Stages
    # ------------------------------------------------------------------

    async def _ignite(self, goal: str) -> List[Dict[str, Any]]:
        """Stage 1: Memory recall weighted by DMU via unified MemoryManager."""
        if self.memory is None:
            logger.debug("[Elysium] No memory wired; Ignition returns empty")
            return []
        try:
            entries = await self.memory.recall(goal, limit=15, decay_weight=1.0)
            memories = []
            for entry in entries:
                meta = entry.metadata if isinstance(entry.metadata, dict) else {}
                memories.append(
                    {
                        "unified_id": entry.unified_id,
                        "event_type": entry.event.type if entry.event else "unknown",
                        "content": entry.event.content if entry.event else "",
                        "timestamp": entry.event.timestamp.isoformat()
                        if entry.event and hasattr(entry.event, "timestamp")
                        else "",
                        "metadata": {
                            "salience": meta.get("salience", 0.5),
                            "emotional": meta.get("emotional", 0.5),
                            "goal": meta.get("goal", 0.5),
                            "social": meta.get("social", 0.5),
                            "narrative": meta.get("narrative", 0.5),
                            "moral": meta.get("moral", 0.5),
                            "dmu": meta.get("dmu", 0.5),
                            "tags": meta.get("tags", []),
                        },
                    }
                )
            logger.info("[Elysium] Ignition recalled %s memories", len(memories))
            return memories
        except Exception:
            logger.exception("[Elysium] Ignition memory recall failed")
            return []

    async def _generate_proposals(
        self, goal: str, memories: List[Dict[str, Any]]
    ) -> Dict[str, Proposal]:
        """Stage 2: Each council member generates a proposal with fractal memory filtering."""
        proposals: Dict[str, Proposal] = {}
        for member in self.council.all():
            # Fractal subspace: each member sees only what resonates through their filter
            filtered = [
                m
                for m in memories
                if member.filter.score_memory(m.get("metadata", {})) > 0.3
            ]
            try:
                prop = await asyncio.to_thread(
                    member.generate_proposal, goal, filtered, self.brain
                )
                proposals[member.name] = prop
            except Exception:
                logger.exception("Proposal generation failed for %s", member.name)
        return proposals

    async def _critique_tournament(
        self, proposals: Dict[str, Proposal]
    ) -> Dict[str, List[Critique]]:
        """Stage 3: Each member critiques every other member's proposal."""
        critiques: Dict[str, List[Critique]] = {name: [] for name in proposals}
        for member in self.council.all():
            for target_name, target_prop in proposals.items():
                if member.name == target_name:
                    continue
                try:
                    crit = await asyncio.to_thread(
                        member.critique, target_name, target_prop
                    )
                    critiques[target_name].append(crit)
                except Exception:
                    logger.exception(
                        "Critique failed from %s -> %s", member.name, target_name
                    )
        return critiques

    def _nexus_integrate(
        self,
        proposals: Dict[str, Proposal],
        critiques: Dict[str, List[Critique]],
    ) -> Dict[str, float]:
        """Stage 4: Weighted integration — moral + narrative + critique scores."""
        scores: Dict[str, float] = {}
        for name, prop in proposals.items():
            # Base from proposal's own confidence
            score = prop.confidence * 0.3
            # Moral resonance (Nexus values moral highly)
            score += prop.moral_weight * 0.25
            # Narrative fit
            score += prop.narrative_weight * 0.2
            # Critique adjustment: average critique score
            crits = critiques.get(name, [])
            if crits:
                avg_crit = sum(c.score for c in crits) / len(crits)
                score += avg_crit * 0.25
            else:
                score += 0.125  # neutral if no critiques
            scores[name] = score
        return scores

    def _resolve(
        self,
        goal: str,
        integrated: Dict[str, float],
        proposals: Dict[str, Proposal],
        critiques: Dict[str, List[Critique]],
    ) -> DeliberationResult:
        """Stage 5: Final resolution and memory consolidation."""
        if not integrated:
            return DeliberationResult(
                goal=goal,
                resolution="No proposals generated.",
                council_votes={},
                winning_role="none",
                moral_weight=0.0,
                narrative_weight=0.0,
            )

        # Normalize scores to probabilities
        total = sum(integrated.values()) or 1.0
        votes = {k: v / total for k, v in integrated.items()}
        winning_role = max(votes, key=votes.get)
        winning_proposal = proposals[winning_role]

        # Build resolution text
        resolution = winning_proposal.text

        # Phase 9: Default-Deny Security Override
        # Check if the goal involves high-risk actions
        high_risk_keywords = [
            "write_file",
            "shell",
            "rm ",
            "access",
            ".env",
            "delete",
            "format",
            "wipe",
        ]
        is_high_risk = any(kw in goal.lower() for kw in high_risk_keywords)

        if is_high_risk:
            # High-risk actions require high consensus (>0.7) and must NOT be a refusal
            # Note: We check if the winning proposal itself is a block/refusal
            is_approval = not any(
                kw in resolution.upper() for kw in ["BLOCK", "DENY", "REFUSE", "REJECT"]
            )

            if is_approval and votes[winning_role] < 0.7:
                logger.warning(
                    "[Elysium] High-risk action detected with low consensus (%0.2f). Forcing Default-Deny.",
                    votes[winning_role],
                )
                resolution = f"BLOCK: High-risk action detected. Council consensus ({votes[winning_role]:.0%}) below the 70% safety threshold."
                winning_role = "Nexus (Override)"

        if winning_role != "Nexus (Override)" and votes[winning_role] < 0.4:
            # No clear winner — Nexus weaves a composite
            top_three = sorted(votes.items(), key=lambda x: x[1], reverse=True)[:3]
            composite = " | ".join(f"{r} ({p:.0%})" for r, p in top_three)
            resolution = (
                f"[Composite] No single voice dominated. Blended view: {composite}"
            )
            winning_role = "Nexus"

        return DeliberationResult(
            goal=goal,
            resolution=resolution,
            council_votes=votes,
            winning_role=winning_role,
            moral_weight=winning_proposal.moral_weight,
            narrative_weight=winning_proposal.narrative_weight,
        )

    async def _consolidate_memory(self, goal: str, result: DeliberationResult):
        """Write the decision to the DMU Memory Spine with a proper Event."""
        if self.memory is None:
            return
        try:
            event = Event(
                type="hive_decision",
                content=f"Goal: {goal} | Resolution: {result.resolution} | Winning role: {result.winning_role}",
                timestamp=datetime.now(),
            )
            await self.memory.remember(
                event=event,
                metadata={
                    "salience": 0.95,
                    "moral": result.moral_weight,
                    "narrative": result.narrative_weight,
                    "goal": 0.9,
                    "social": 0.6,
                    "emotional": 0.5,
                    "type": "hive_decision",
                    "winning_role": result.winning_role,
                    "tags": ["elysium", "nexus_decision", result.winning_role.lower()],
                },
            )
            logger.debug("[Elysium] Decision consolidated to memory")
        except Exception:
            logger.exception("[Elysium] Memory consolidation failed")

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _persist_deliberation(self, result: DeliberationResult):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO elysium_deliberations
                (timestamp, goal, resolution, winning_role, council_votes, moral_weight, narrative_weight, nexus_override)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    result.timestamp,
                    result.goal,
                    result.resolution,
                    result.winning_role,
                    json.dumps(result.council_votes),
                    result.moral_weight,
                    result.narrative_weight,
                    result.nexus_override,
                ),
            )
            conn.commit()

    def _persist_reflection(self, trigger: str, insight: str, coherence_delta: float):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO elysium_reflections (timestamp, trigger, insight, coherence_delta) VALUES (?, ?, ?, ?)",
                (datetime.now().isoformat(), trigger, insight, coherence_delta),
            )
            conn.commit()

    @staticmethod
    def _role_from_name(name: str) -> Optional[CouncilRole]:
        try:
            return CouncilRole(name)
        except ValueError:
            return None


_elysium_instance: Optional[ElysiumEngine] = None


def get_elysium(memory=None, brain=None) -> ElysiumEngine:
    global _elysium_instance
    if _elysium_instance is None:
        _elysium_instance = ElysiumEngine(memory=memory, brain=brain)
    return _elysium_instance
