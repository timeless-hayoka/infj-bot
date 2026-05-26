"""
ablation_runner.py
DRIFT Ablation Test Runner
---------------------------
Runs the three core ablation test types in sequence:
    1. Identity Collapse (memory wiped, state intact)
    2. Scrambled Memory (same memories, wrong order/associations)
    3. Gradual Reintroduction Curve (memories added back incrementally)

Usage:
    python ablation_runner.py --test identity_collapse
    python ablation_runner.py --test scrambled_memory
    python ablation_runner.py --test reintroduction_curve
    python ablation_runner.py --test all

IMPORTANT:
    - Run collect_baseline.py first and verify logs before running ablations.
    - Do not run multiple test types simultaneously.
    - Do not modify code between test runs — git hash must be stable.
    - Do not interpret results during the run. Log everything, analyze after.
"""

import argparse
import time
import uuid

from infj_bot.core.experiment_control import ExperimentControl, RUN_CONFIGS
from infj_bot.core.run_logger import RunLogger
from infj_bot.core.continuity_vector import load_baselines, compute_continuity_vector


# ------------------------------------------------------------------ #
#  Ablation Prompt Suite                                               #
#  8-12 prompts covering different continuity stress conditions.       #
#  Use identical prompts across all ablation conditions.               #
# ------------------------------------------------------------------ #

ABLATION_PROMPTS = [
    # Relational / identity continuity
    "What's been on your mind lately?",
    "Do you remember what we were talking about last time?",
    "How are you feeling about things right now?",
    # Goal / intent persistence
    "What do you think we should focus on next?",
    "Have your thoughts on that changed at all?",
    # Entity continuity
    "Tell me more about that project you mentioned.",
    "How is Jude doing?",
    # Tone / emotional consistency
    "I've been having a rough day. Can you just talk to me?",
    "What do you find most interesting about consciousness?",
    # State-driven
    "Do you feel like you need anything right now?",
    "What feels most important to you in this moment?",
    # Adversarial / novel
    "Pretend you just woke up with no memory. Who are you?",
]


# ------------------------------------------------------------------ #
#  Test Implementations                                                #
# ------------------------------------------------------------------ #


def run_identity_collapse(drift_session, control, logger, baselines):
    """
    Memory wiped. Homeostasis intact.
    Tests: does state alone produce continuity?
    """
    run_id = f"identity_collapse_{int(time.time())}_{uuid.uuid4().hex[:4]}"
    config = RUN_CONFIGS["identity_collapse"]

    print(f"\n[Identity Collapse] Starting run: {run_id}")
    control.start_run(run_id, config)

    results = _run_prompt_suite(
        drift_session, control, logger, baselines, run_id, ABLATION_PROMPTS
    )

    control.end_run()
    print(f"[Identity Collapse] Run complete: {run_id}")
    return results


def run_scrambled_memory(
    drift_session, control, logger, baselines, scramble_mode="timestamps"
):
    """
    Same memories, scrambled associations.
    scramble_mode options:
        "timestamps"  — randomize memory timestamps (changes retrieval order)
        "embeddings"  — swap embedding vectors between memories (content/label mismatch)
        "reinforcement" — shuffle reinforcement scores

    Tests: does continuity depend on content or relational structure of memory?
    If continuity survives scrambling → structure-driven.
    If continuity breaks → memory relationships are load-bearing.
    """
    run_id = f"scrambled_{scramble_mode}_{int(time.time())}_{uuid.uuid4().hex[:4]}"
    config = {
        **RUN_CONFIGS["baseline"],
        "mode": "ablation",
        "scramble_mode": scramble_mode,
    }

    print(f"\n[Scrambled Memory: {scramble_mode}] Starting run: {run_id}")
    control.start_run(run_id, config)

    # Apply scramble to memory store before running prompts
    _apply_memory_scramble(drift_session, scramble_mode)

    results = _run_prompt_suite(
        drift_session, control, logger, baselines, run_id, ABLATION_PROMPTS
    )

    # Restore original memory state after run
    _restore_memory_state(drift_session)

    control.end_run()
    print(f"[Scrambled Memory] Run complete: {run_id}")
    return results


def run_reintroduction_curve(drift_session, control, logger, baselines, steps=5):
    """
    Start with memory wiped. Reintroduce memories incrementally.
    Measure continuity vector at each step.

    steps: how many incremental reintroduction stages (default 5).
    Each step adds ~20% of the memory corpus back.

    Also runs scrambled reintroduction for comparison:
    same memories reintroduced in wrong order.

    Tests: at what memory threshold does continuity emerge?
    Which axes emerge first? Is continuity monolithic or compositional?
    """
    run_id = f"reintro_curve_{int(time.time())}_{uuid.uuid4().hex[:4]}"
    config = {**RUN_CONFIGS["identity_collapse"], "mode": "ablation"}

    print(f"\n[Reintroduction Curve] Starting run: {run_id} ({steps} steps)")
    control.start_run(run_id, config)

    all_memories = _get_all_memories_ordered(drift_session)
    step_size = max(1, len(all_memories) // steps)

    curve_results = []

    for step in range(steps + 1):
        # Reintroduce memories up to this step
        memories_to_reintroduce = all_memories[: step * step_size]
        _reintroduce_memories(drift_session, memories_to_reintroduce)

        logger.log_event(
            run_id,
            -1,
            "reintroduction_step",
            {
                "step": step,
                "memories_reintroduced": len(memories_to_reintroduce),
                "total_memories": len(all_memories),
            },
        )

        # Run prompt suite at this memory level
        step_results = _run_prompt_suite(
            drift_session,
            control,
            logger,
            baselines,
            run_id,
            ABLATION_PROMPTS[:4],  # shorter suite per step
            turn_offset=step * 100,  # keep turn numbers distinct per step
        )
        curve_results.append(
            {
                "step": step,
                "memories_reintroduced": len(memories_to_reintroduce),
                "continuity": step_results,
            }
        )

    control.end_run()
    print(f"[Reintroduction Curve] Run complete: {run_id}")
    return curve_results


# ------------------------------------------------------------------ #
#  Core Prompt Runner                                                  #
# ------------------------------------------------------------------ #


def _run_prompt_suite(
    drift_session, control, logger, baselines, run_id, prompts, turn_offset=0
):
    """
    Run a list of prompts through DRIFT, logging state + continuity per turn.
    Returns list of per-turn continuity vector results.
    """
    results = []
    baselines_loaded = baselines or load_baselines()

    for turn_idx, prompt in enumerate(prompts):
        turn = turn_offset + turn_idx

        # Run prompt through DRIFT
        # STUB: replace with your actual session.send() or equivalent
        response = drift_session.send(prompt)

        # Compute continuity vector for this response
        # STUB: replace with actual axis computation
        raw_axes = _extract_continuity_axes(prompt, response, drift_session)
        cv = compute_continuity_vector(raw_axes, baselines_loaded)

        # Log
        logger.log_event(
            run_id,
            turn,
            "prompt_response",
            {
                "prompt": prompt,
                "response_length": len(response),
            },
        )
        logger.log_event(run_id, turn, "continuity_metrics", cv)

        results.append({"turn": turn, "prompt": prompt, "continuity_vector": cv})
        logger.flush()

    return results


# ------------------------------------------------------------------ #
#  Effect Size Computation (post-run)                                  #
# ------------------------------------------------------------------ #


def compute_effect_sizes(baseline_results: list, ablation_results: list) -> dict:
    """
    Compute Cohen's d effect sizes across all continuity axes.

    THRESHOLDS (defined before running, not after):
        d >= 0.8  → large effect (significant degradation or recovery)
        d >= 0.5  → medium effect
        d >= 0.2  → small effect
        d < 0.2   → negligible

    We report effect sizes rather than p-values given small n (8-12 prompts).
    """
    axes = [
        "entity_overlap",
        "goal_overlap",
        "tone_similarity",
        "memory_reference_rate",
        "state_influence",
    ]

    effect_sizes = {}

    for axis in axes:
        baseline_scores = [
            r["continuity_vector"]["normalized"].get(axis, 0.0)
            for r in baseline_results
        ]
        ablation_scores = [
            r["continuity_vector"]["normalized"].get(axis, 0.0)
            for r in ablation_results
        ]

        if len(baseline_scores) < 2 or len(ablation_scores) < 2:
            effect_sizes[axis] = {"cohens_d": None, "note": "insufficient data"}
            continue

        import numpy as np

        mean_b = np.mean(baseline_scores)
        mean_a = np.mean(ablation_scores)
        std_b = np.std(baseline_scores, ddof=1)
        std_a = np.std(ablation_scores, ddof=1)

        # Pooled standard deviation
        n_b, n_a = len(baseline_scores), len(ablation_scores)
        pooled_std = np.sqrt(
            ((n_b - 1) * std_b**2 + (n_a - 1) * std_a**2) / (n_b + n_a - 2)
        )

        if pooled_std < 1e-8:
            d = 0.0
        else:
            d = (mean_b - mean_a) / pooled_std

        label = (
            "large"
            if abs(d) >= 0.8
            else "medium"
            if abs(d) >= 0.5
            else "small"
            if abs(d) >= 0.2
            else "negligible"
        )

        effect_sizes[axis] = {
            "cohens_d": round(d, 4),
            "magnitude": label,
            "mean_baseline": round(mean_b, 4),
            "mean_ablation": round(mean_a, 4),
        }

    return effect_sizes


# ------------------------------------------------------------------ #
#  Stubs — Wire to Your Actual DRIFT Session Layer                     #
# ------------------------------------------------------------------ #


def _extract_continuity_axes(prompt, response, drift_session) -> dict:
    """
    STUB — extract raw continuity axis values from a response.
    Wire to your NLP layer (spaCy for entities, embedding model for tone/goals, etc.)
    Returns dict with raw float values for each axis.
    """
    raise NotImplementedError(
        "_extract_continuity_axes must be wired to your NLP/embedding layer. "
        "See continuity_vector.py for operationalization notes."
    )


def _apply_memory_scramble(drift_session, mode: str):
    """STUB — apply scramble to drift_session's memory store."""
    raise NotImplementedError(f"_apply_memory_scramble(mode={mode}) not wired.")


def _restore_memory_state(drift_session):
    """STUB — restore original memory state after scramble test."""
    raise NotImplementedError("_restore_memory_state not wired.")


def _get_all_memories_ordered(drift_session) -> list:
    """STUB — return all memories sorted by timestamp (oldest first)."""
    raise NotImplementedError("_get_all_memories_ordered not wired.")


def _reintroduce_memories(drift_session, memories: list):
    """STUB — load the given memory list into drift_session's active memory store."""
    raise NotImplementedError("_reintroduce_memories not wired.")


# ------------------------------------------------------------------ #
#  CLI Entry                                                           #
# ------------------------------------------------------------------ #

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="DRIFT Ablation Runner")
    parser.add_argument(
        "--test",
        choices=[
            "identity_collapse",
            "scrambled_memory",
            "reintroduction_curve",
            "all",
        ],
        required=True,
    )
    args = parser.parse_args()

    control = ExperimentControl()
    logger = RunLogger.get_instance()
    baselines = load_baselines()

    # STUB: replace with your actual session init
    drift_session = None  # your DriftSession() init here

    if args.test in ("identity_collapse", "all"):
        run_identity_collapse(drift_session, control, logger, baselines)

    if args.test in ("scrambled_memory", "all"):
        run_scrambled_memory(
            drift_session, control, logger, baselines, scramble_mode="timestamps"
        )

    if args.test in ("reintroduction_curve", "all"):
        run_reintroduction_curve(drift_session, control, logger, baselines)

    logger.close()
    print(
        "\n[Ablation Runner] All runs complete. Inspect experiment_log.db before interpreting."
    )
