"""Structured reasoning cycle: goals, decomposition, uncertainty — tied to evidence board."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any
from uuid import uuid4

from drift.trinity.council.forge_council_schema import ClaimRecord, ClaimStatus, new_claim_id


class GoalStatus(str, Enum):
    PENDING = "pending"
    ACTIVE = "active"
    BLOCKED = "blocked"
    DONE = "done"
    CANCELLED = "cancelled"


@dataclass
class SubTask:
    id: str
    description: str
    status: GoalStatus = GoalStatus.PENDING
    uncertainty: float = 0.5
    evidence_refs: list[str] = field(default_factory=list)


@dataclass
class Goal:
    id: str
    title: str
    priority: float = 0.5
    status: GoalStatus = GoalStatus.PENDING
    uncertainty: float = 0.5
    subtasks: list[SubTask] = field(default_factory=list)
    claim_id: str | None = None

    @classmethod
    def create(cls, title: str, *, priority: float = 0.5) -> "Goal":
        return cls(id=str(uuid4()), title=title, priority=priority)


@dataclass
class ReasoningState:
    goals: list[Goal] = field(default_factory=list)
    active_goal_id: str | None = None
    error_model: list[dict[str, Any]] = field(default_factory=list)

    def add_goal(self, goal: Goal) -> Goal:
        self.goals.append(goal)
        if self.active_goal_id is None:
            self.active_goal_id = goal.id
            goal.status = GoalStatus.ACTIVE
        return goal

    def arbitrate(self) -> Goal | None:
        candidates = [
            g
            for g in self.goals
            if g.status in (GoalStatus.PENDING, GoalStatus.ACTIVE)
        ]
        if not candidates:
            return None
        chosen = max(candidates, key=lambda g: (g.priority, -g.uncertainty))
        self.active_goal_id = chosen.id
        chosen.status = GoalStatus.ACTIVE
        return chosen

    def decompose(self, goal: Goal, steps: list[str]) -> list[SubTask]:
        goal.subtasks = [
            SubTask(id=str(uuid4()), description=step) for step in steps if step.strip()
        ]
        return goal.subtasks

    def record_error(self, *, stage: str, message: str, recoverable: bool = True) -> None:
        self.error_model.append(
            {
                "stage": stage,
                "message": message,
                "recoverable": recoverable,
            }
        )

    def to_claim(self, goal: Goal, *, proposer: str = "reasoning_cycle") -> ClaimRecord:
        claim_id = goal.claim_id or new_claim_id()
        goal.claim_id = claim_id
        return ClaimRecord(
            id=claim_id,
            proposer=proposer,
            subject=goal.title,
            content={
                "goal_id": goal.id,
                "subtasks": [s.description for s in goal.subtasks],
                "uncertainty": goal.uncertainty,
                "error_model": self.error_model[-5:],
            },
            confidence=max(0.0, 1.0 - goal.uncertainty),
            status=ClaimStatus.PROPOSED,
        )


class ReasoningCycle:
    """Minimal cognitive loop for ANCHOR: plan → decompose → attach to evidence board."""

    def __init__(self) -> None:
        self.state = ReasoningState()

    def plan(self, title: str, *, steps: list[str] | None = None, priority: float = 0.5) -> Goal:
        goal = Goal.create(title, priority=priority)
        self.state.add_goal(goal)
        if steps:
            self.state.decompose(goal, steps)
        return goal

    def bind_evidence(self, goal: Goal, evidence_ref: str) -> None:
        for subtask in goal.subtasks:
            if subtask.status == GoalStatus.PENDING:
                subtask.evidence_refs.append(evidence_ref)
                subtask.uncertainty = max(0.0, subtask.uncertainty - 0.1)
                break
        if goal.subtasks:
            goal.uncertainty = sum(s.uncertainty for s in goal.subtasks) / len(goal.subtasks)

    def export_claim(self, goal: Goal) -> ClaimRecord:
        return self.state.to_claim(goal)


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(
        prog="drift.trinity.reasoning_cycle",
        description="Structured reasoning cycle: goals, decomposition, claim export.",
    )
    parser.add_argument("goal", nargs="?", default="Validate SARIF finding repro")
    parser.add_argument("--steps", nargs="*", default=["ingest", "filter", "proof"])
    args = parser.parse_args()

    cycle = ReasoningCycle()
    goal = cycle.plan(args.goal, steps=args.steps)
    claim = cycle.export_claim(goal)
    print(f"goal={goal.title} uncertainty={goal.uncertainty:.2f}")
    print(f"claim_id={claim.id} confidence={claim.confidence:.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
