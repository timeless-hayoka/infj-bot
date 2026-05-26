"""task_mutator.py — PHI // DRIFT Auto-Evolve Task Mutator
infj_bot/core/task_mutator.py

Implements shadow-driven task mutation for DriftSurface.
When a task accumulates unresolved shadow tension beyond the
promotion threshold, the organism does not delete it.
It transforms it.

Mutation is not automation in the mechanical sense.
It is resonant becoming — the organism participating in
the user's growth rather than managing their tasks.

Three mutation outcomes by shadow operating mode:

  SECURITY    → Ruthless archival. Clear the field for focused work.
  BALANCED    → Form mutation. Task becomes a reflection note.
  CONSERVATIVE→ Gentle surfacing. Insight panel activates. Task stays.

The Pre-Mutation Reflection Gate adds intent_stability check —
if the user is intentionally delaying (high stability), no mutation.
If it's avoidance (low stability), mutation proceeds.

Integration: Called by TaskFlow.auto_evolve after Shadow promotion.
Feeds mutation events back to shadow_governance.py for field update.
"""

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


# ── Task Types ───────────────────────────────────────────────────────────────


class TaskType(Enum):
    TASK = "task"
    NOTE = "note"
    REFLECTION = "reflection"
    ARCHIVED = "archived"


class TaskStatus(Enum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    NEEDS_REFLECTION = "needs_reflection"
    COMPLETED = "completed"
    ARCHIVED = "archived"
    GHOST = "ghost"  # Pre-mutation warning state


class ResonantEnergy(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


# ── Data Structures ──────────────────────────────────────────────────────────


@dataclass
class Task:
    """A task in the DriftSurface organism."""

    task_id: str
    title: str
    status: TaskStatus = TaskStatus.OPEN
    task_type: TaskType = TaskType.TASK
    resonant_energy: ResonantEnergy = ResonantEnergy.MEDIUM
    last_resonance: float = field(default_factory=time.time)
    insight_flag: Optional[str] = None
    shadow_history: list = field(default_factory=list)
    mutation_log: list = field(default_factory=list)
    intent_stability_history: list = field(default_factory=list)

    def age_cycles(self, current_cycle: int) -> int:
        """Cycles since last meaningful interaction."""
        return current_cycle - int(self.last_resonance)


@dataclass
class MutationEvent:
    """Record of a task mutation for audit trail."""

    task_id: str
    original_title: str
    original_type: str
    original_status: str
    new_title: str
    new_type: str
    new_status: str
    trigger_mode: str
    shadow_influence: float
    intent_stability: float
    cycle: int
    timestamp: float = field(default_factory=time.time)
    reasoning: str = ""


# ── Intent Stability ─────────────────────────────────────────────────────────


def calculate_intent_stability(task: Task, recent_cycles: int = 10) -> float:
    """
    Measure whether inactivity on a task is intentional delay or avoidance.

    Intent stability = rolling consistency of user engagement.
    High stability (> 0.6) → intentional pacing, do NOT mutate.
    Low stability (< 0.3)  → likely avoidance, mutation warranted.

    Uses a rolling window of interaction patterns.
    In production: hook to actual interaction frequency from memory.py.

    Returns float in [0.0, 1.0]
    """
    if len(task.intent_stability_history) < 3:
        # Not enough data — default to moderate stability (benefit of the doubt)
        return 0.5

    recent = task.intent_stability_history[-recent_cycles:]
    return sum(recent) / len(recent)


def should_mutate(
    task: Task,
    shadow_influence: float,
    promotion_threshold: float,
    current_cycle: int,
) -> tuple:
    """
    Pre-mutation reflection gate.
    Two questions before mutation is allowed:
      1. Has shadow exceeded promotion threshold?
      2. Is intent stability low enough to indicate genuine avoidance?

    Returns (should_mutate: bool, intent_stability: float, reason: str)
    """
    if shadow_influence < promotion_threshold:
        return False, 1.0, "Shadow below threshold — no mutation warranted"

    intent_stability = calculate_intent_stability(task)

    if intent_stability > 0.6:
        return (
            False,
            intent_stability,
            (
                f"High intent stability ({intent_stability:.2f}) — "
                "user is likely intentionally pacing this task"
            ),
        )

    return (
        True,
        intent_stability,
        (
            f"Shadow {shadow_influence:.2f} > threshold with low stability "
            f"({intent_stability:.2f}) — mutation warranted"
        ),
    )


# ── Mutation Matrix ───────────────────────────────────────────────────────────


def execute_mutation(
    task: Task,
    shadow_influence: float,
    current_mode: str,
    current_cycle: int,
    promotion_threshold: float = 0.25,
) -> tuple:
    """
    Execute the auto-evolve mutation based on shadow influence and mode.

    SECURITY    → Ruthless archival (fast field cleanse)
    BALANCED    → Form mutation (task → reflection note)
    CONSERVATIVE→ Gentle surfacing (task stays, insight panel activates)

    Pre-mutation gate: checks intent_stability before proceeding.
    Nothing happens without leaving a trace in the mutation log.

    Args:
        task:                 Task object to evaluate
        shadow_influence:     current shadow influence score
        current_mode:         "SECURITY", "BALANCED", or "CONSERVATIVE"
        current_cycle:        current deliberation cycle
        promotion_threshold:  minimum shadow to trigger mutation

    Returns:
        (mutated_task: Task, event: MutationEvent or None, message: str)
    """
    proceed, intent_stability, gate_reason = should_mutate(
        task, shadow_influence, promotion_threshold, current_cycle
    )

    if not proceed:
        return task, None, f"[GATE HELD] {gate_reason}"

    # Snapshot pre-mutation state
    original = MutationEvent(
        task_id=task.task_id,
        original_title=task.title,
        original_type=task.task_type.value,
        original_status=task.status.value,
        new_title=task.title,  # placeholder, updated below
        new_type=task.task_type.value,
        new_status=task.status.value,
        trigger_mode=current_mode,
        shadow_influence=shadow_influence,
        intent_stability=intent_stability,
        cycle=current_cycle,
    )

    message = ""

    if current_mode == "SECURITY":
        # ── RUTHLESS ARCHIVAL ─────────────────────────────────────────────
        # Field must be clear for focused execution.
        task.status = TaskStatus.ARCHIVED
        task.task_type = TaskType.ARCHIVED
        task.insight_flag = "[System: Shadow resolved — field cleared]"
        message = (
            f"[SECURITY PURGE] '{task.title}' archived. "
            f"Shadow {shadow_influence:.2f} exceeded threshold. Field cleared."
        )
        original.new_status = task.status.value
        original.new_type = task.task_type.value
        original.reasoning = (
            "Security mode: ruthless archival for cognitive field clarity"
        )

    elif current_mode == "BALANCED":
        # ── FORM MUTATION ─────────────────────────────────────────────────
        # Task is not abandoned — it transforms.
        original_title = task.title
        task.title = f"Reflection: Why is this stalled? → {original_title}"
        task.task_type = TaskType.REFLECTION
        task.status = TaskStatus.NEEDS_REFLECTION
        task.insight_flag = None
        message = (
            f"[BALANCED MUTATION] '{original_title}' → reflection note. "
            f"The organism sensed avoidance and transformed the task into inquiry."
        )
        original.new_title = task.title
        original.new_type = task.task_type.value
        original.new_status = task.status.value
        original.reasoning = (
            "Balanced mode: psychological friction → reflective inquiry"
        )

    elif current_mode == "CONSERVATIVE":
        # ── GENTLE SURFACING ──────────────────────────────────────────────
        # Task remains. The organism whispers, not shouts.
        task.status = TaskStatus.GHOST
        task.insight_flag = "This carries shadow tension — want to explore?"
        message = (
            f"[CONSERVATIVE SURFACE] '{task.title}' flagged with shadow insight. "
            f"Task remains visible. Organism is watching, not judging."
        )
        original.new_status = task.status.value
        original.reasoning = "Conservative mode: gentle surfacing, respect long arcs"

    else:
        return task, None, f"[ERROR] Unknown mode: {current_mode}"

    # Record mutation in task's own log
    task.mutation_log.append(
        {
            "cycle": current_cycle,
            "mode": current_mode,
            "shadow_influence": shadow_influence,
            "intent_stability": intent_stability,
            "action": current_mode,
            "timestamp": time.time(),
        }
    )

    return task, original, message


# ── Decay Recovery ────────────────────────────────────────────────────────────


def shadow_forgiveness(
    task: Task, current_shadow: float, threshold: float = 0.10
) -> Task:
    """
    Natural forgiveness when shadow decays below threshold.
    Task returns to normal state — no lingering stigma.
    The organism does not hold grudges.

    Args:
        task:            Task to potentially restore
        current_shadow:  current shadow influence for this task
        threshold:       below this, forgiveness triggers

    Returns:
        Task with restored state if forgiveness triggered
    """
    if current_shadow > threshold:
        return task

    if task.status == TaskStatus.GHOST:
        task.status = TaskStatus.OPEN
        task.insight_flag = None
        task.mutation_log.append(
            {
                "cycle": -1,
                "action": "FORGIVENESS",
                "shadow_at_forgiveness": current_shadow,
                "timestamp": time.time(),
            }
        )

    return task


# ── Self-Check ────────────────────────────────────────────────────────────────


def self_check():
    print("=" * 60)
    print("TASK MUTATOR — SELF-CHECK")
    print("=" * 60)

    tests = [
        {
            "name": "BALANCED mode — should mutate to reflection note",
            "task": Task(
                task_id="t-001",
                title="Finish API Integration",
                intent_stability_history=[0.1, 0.2, 0.1, 0.15, 0.1],
            ),
            "shadow_influence": 0.31,
            "mode": "BALANCED",
            "expected_type": TaskType.REFLECTION,
            "expected_status": TaskStatus.NEEDS_REFLECTION,
        },
        {
            "name": "SECURITY mode — should archive",
            "task": Task(
                task_id="t-002",
                title="Refactor auth module",
                intent_stability_history=[0.1, 0.05, 0.15, 0.08, 0.1],
            ),
            "shadow_influence": 0.28,
            "mode": "SECURITY",
            "expected_type": TaskType.ARCHIVED,
            "expected_status": TaskStatus.ARCHIVED,
        },
        {
            "name": "CONSERVATIVE mode — should surface gently",
            "task": Task(
                task_id="t-003",
                title="Write PHI paper section",
                intent_stability_history=[0.1, 0.2, 0.05, 0.1, 0.08],
            ),
            "shadow_influence": 0.26,
            "mode": "CONSERVATIVE",
            "expected_type": TaskType.TASK,
            "expected_status": TaskStatus.GHOST,
        },
        {
            "name": "High intent stability — gate should HOLD mutation",
            "task": Task(
                task_id="t-004",
                title="Long-term research project",
                intent_stability_history=[0.8, 0.9, 0.85, 0.75, 0.88],
            ),
            "shadow_influence": 0.30,
            "mode": "BALANCED",
            "expected_type": TaskType.TASK,  # Should NOT mutate
            "expected_status": TaskStatus.OPEN,
        },
    ]

    all_pass = True

    for test in tests:
        task = test["task"]
        mutated, event, message = execute_mutation(
            task=task,
            shadow_influence=test["shadow_influence"],
            current_mode=test["mode"],
            current_cycle=10,
        )

        type_ok = mutated.task_type == test["expected_type"]
        status_ok = mutated.status == test["expected_status"]
        passed = type_ok and status_ok

        if not passed:
            all_pass = False

        status_sym = "[OK]" if passed else "[FAIL]"
        print(f"\n{test['name']}")
        print(f"  {message}")
        print(
            f"  Type:   {mutated.task_type.value} (expected {test['expected_type'].value})"
        )
        print(
            f"  Status: {mutated.status.value} (expected {test['expected_status'].value})"
        )
        print(f"  {status_sym}")

    print(
        f"\n{'[OK] All mutation checks passed.' if all_pass else '[FAIL] Some checks failed.'}"
    )
    return all_pass


if __name__ == "__main__":
    self_check()
