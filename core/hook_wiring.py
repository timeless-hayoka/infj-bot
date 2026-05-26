"""
hook_wiring.py
DRIFT Freeze-Mode Hook Reference
----------------------------------
This file is a REFERENCE, not a drop-in.
It shows the exact pattern to apply at each of the three primary call sites.
Copy the relevant blocks into memory.py, homeostasis.py, and cognition.py.

DO NOT wire self_modify.py yet — it is frozen in all initial test configs.
Wire it after the first ablation suite is complete.

Rule: freeze novelty at COMPUTATION TIME, not after caching.
Rule: is_active() checks are always at the call site, not inside the subsystem.
"""

from infj_bot.core.experiment_control import ExperimentControl

# Access the singleton control instance.
# In practice, pass this in or access via your DI / global context pattern.
control = ExperimentControl()  # replace with your actual singleton access


# ================================================================== #
# 1. memory.py  —  Memory Store Hook                                  #
# ================================================================== #
# Find your memory storage call site and wrap it:


def example_memory_store_hook(memory_system, memory_object, logger, run_id, turn):
    """
    Pattern for memory.py store call site.
    """
    if control.is_active("memory"):
        memory_system.store(memory_object)

        # Log the storage event
        logger.log_event(
            run_id,
            turn,
            "memory_stored",
            {
                "memory_id": memory_object.id,
                "reinforcement_score": memory_object.reinforcement_score,
                "timestamp": memory_object.timestamp,
            },
        )
    # If frozen: silently skip. Memory is the experimental condition.


# ================================================================== #
# 2. homeostasis.py  —  State Update Hook                             #
# ================================================================== #
# Find your homeostasis state update call site and wrap it:


def example_state_update_hook(homeostasis_system, state_delta, logger, run_id, turn):
    """
    Pattern for homeostasis.py state update call site.
    """
    if control.is_active("state"):
        homeostasis_system.update(state_delta)

        # Log the state snapshot after update
        logger.log_event(
            run_id,
            turn,
            "state_snapshot",
            {
                "homeostasis": homeostasis_system.get_current_state(),
            },
        )
    # If frozen: state is locked. Used for memory-only continuity test.


# ================================================================== #
# 3. cognition.py  —  Novelty Computation Hook                        #
# ================================================================== #
# CRITICAL: freeze novelty at computation time, not after caching.
# Wrong: compute novelty → cache score → freeze later (stale cache preserves it)
# Right: freeze check → then set on memory object → then MPS uses it


def example_novelty_computation_hook(memory_object, recent_memories):
    """
    Pattern for novelty computation in cognition.py.
    Must happen BEFORE memory.novelty_score is set and BEFORE MPS runs.
    """
    # Compute raw novelty
    novelty_raw = _compute_novelty(memory_object, recent_memories)

    # Freeze check — set to neutral BEFORE propagation
    if not control.is_active("novelty"):
        novelty_raw = 0.0  # additive neutral in MPS

    # Set on memory object — MPS reads from here
    memory_object.novelty_score = novelty_raw

    return novelty_raw


def _compute_novelty(memory_object, recent_memories) -> float:
    """
    STUB — replace with your actual novelty computation.
    novelty = 1 - max_similarity_to_recent_memories(memory_object, recent_memories)
    Returns float in [0.0, 1.0].
    """
    raise NotImplementedError("Wire to your actual novelty computation.")


# ================================================================== #
# 4. Memory Selection Logging                                          #
# ================================================================== #
# After retrieve_and_rank(), log both selected and rejected candidates.
# Wire this wherever your DMU returns the final top-K memories.


def log_memory_selection(logger, run_id, turn, selected, rejected_top5):
    """
    Log memory selection with full score breakdown.
    score_components must be set on each memory by compute_mps().
    """
    logger.log_event(
        run_id,
        turn,
        "memory_selection",
        {
            "selected": [
                {
                    "id": m.id,
                    "score": m.score,
                    "components": getattr(m, "score_components", None),
                }
                for m in selected
            ],
            "rejected": [
                {
                    "id": m.id,
                    "score": m.score,
                    "components": getattr(m, "score_components", None),
                }
                for m in rejected_top5
            ],
        },
    )


# ================================================================== #
# 5. Per-Turn Logging Template                                         #
# ================================================================== #
# Call this at the end of each turn processing loop.


def log_turn(
    logger,
    run_id,
    turn,
    homeostasis_system,
    selected,
    rejected_top5,
    continuity_vector=None,
):
    """
    Standard per-turn log bundle.
    Call after state update, memory selection, and response generation.
    """
    # State snapshot
    logger.log_event(
        run_id,
        turn,
        "state_snapshot",
        {
            "homeostasis": homeostasis_system.get_current_state(),
        },
    )

    # Memory selection
    log_memory_selection(logger, run_id, turn, selected, rejected_top5)

    # Continuity metrics (if computed this turn)
    if continuity_vector is not None:
        logger.log_event(run_id, turn, "continuity_metrics", continuity_vector)
