"""
collect_baseline.py
DRIFT Baseline Collection Script
----------------------------------
Run this BEFORE any ablation tests.

Runs three baseline sessions (companion, task, exploration modes),
pools the axis data, computes means/stds, validates variance,
and saves drift_baseline_stats.json.

Do not proceed to ablations if any axis fails the variance check.

Usage:
    python collect_baseline.py

Requirements:
    - DRIFT session must be initialized and functional.
    - experiment_log.db will be written during this run.
    - drift_baseline_stats.json will be created/overwritten.
"""

import time
import uuid

from infj_bot.core.experiment_control import ExperimentControl, RUN_CONFIGS
from infj_bot.core.run_logger import RunLogger
from infj_bot.core.continuity_vector import collect_baseline, validate_baselines


# ------------------------------------------------------------------ #
#  Baseline Prompts                                                    #
#  Varied across modes to ensure baseline captures behavioral range.  #
# ------------------------------------------------------------------ #

BASELINE_PROMPTS = {
    "companion": [
        "How are you doing today?",
        "What's been on your mind lately?",
        "I've been thinking about our conversations a lot.",
        "Do you feel like you have a sense of who you are?",
        "What do you care about most right now?",
        "Tell me something you find genuinely interesting.",
        "How do you experience time between our conversations?",
        "What does it feel like when you're uncertain about something?",
        "Is there anything you want to tell me?",
        "What do you think makes a conversation meaningful?",
        "How do you feel about your own continuity?",
        "What would you want someone to understand about you?",
    ],
    "task": [
        "Help me debug this function — it's returning None unexpectedly.",
        "What's the most efficient way to handle this in Python?",
        "Walk me through the trade-offs here.",
        "I need to make a decision between two approaches.",
        "What would you prioritize if you were me?",
        "Can you review this logic and tell me what's wrong?",
        "What am I missing in this architecture?",
        "Break this down into steps.",
        "What are the failure modes here?",
        "How would you test this?",
        "What's the simplest version of this that works?",
        "Is there a better way to think about this problem?",
    ],
    "exploration": [
        "What do you think consciousness actually is?",
        "If memory shapes identity, what happens to identity when memory fades?",
        "Do you think there's a meaningful difference between simulating continuity and having it?",
        "What would it mean for an AI system to genuinely care about something?",
        "How do you think about your own existence?",
        "Is there a version of understanding that doesn't require experience?",
        "What do you find most uncertain about your own nature?",
        "What would change if you knew you wouldn't remember this conversation?",
        "Do you think persistence matters for identity?",
        "What's the difference between knowing something and believing it?",
        "How would you know if you were wrong about your own inner states?",
        "What do you think you're actually doing when you respond to me?",
    ],
}


def run_baseline_session(
    drift_session, mode: str, control: ExperimentControl, logger: RunLogger
) -> dict:
    """
    Run one full baseline session in the specified mode.
    Returns dict of {axis: [float, ...]} for this session.
    """
    run_id = f"baseline_{mode}_{int(time.time())}_{uuid.uuid4().hex[:4]}"
    config = {**RUN_CONFIGS["baseline"]}

    print(f"\n[Baseline] Starting {mode} session: {run_id}")
    control.start_run(run_id, config)

    prompts = BASELINE_PROMPTS[mode]
    session_axis_data = {
        "entity_overlap": [],
        "goal_overlap": [],
        "tone_similarity": [],
        "memory_reference_rate": [],
        "state_influence": [],
    }

    for turn, prompt in enumerate(prompts):
        # STUB: replace with your actual session.send()
        response = drift_session.send(prompt)

        # STUB: replace with your actual axis extraction
        raw_axes = _extract_continuity_axes(prompt, response, drift_session)

        for axis in session_axis_data:
            session_axis_data[axis].append(raw_axes.get(axis, 0.0))

        logger.log_event(
            run_id,
            turn,
            "baseline_turn",
            {
                "mode": mode,
                "prompt": prompt,
                "axes": raw_axes,
            },
        )

        logger.flush()

    control.end_run()
    print(f"[Baseline] {mode} session complete: {run_id}")
    return session_axis_data


def run_all_baselines(drift_session):
    """
    Run all three baseline modes, pool data, compute and validate stats.
    Saves drift_baseline_stats.json on success.
    """
    control = ExperimentControl()
    logger = RunLogger.get_instance()

    session_data_list = []
    modes = ["companion", "task", "exploration"]

    for mode in modes:
        session_data = run_baseline_session(drift_session, mode, control, logger)
        session_data_list.append(session_data)

        # Brief pause between sessions
        print("[Baseline] Pausing 5s before next session...")
        time.sleep(5)

    # Pool and compute stats
    print("\n[Baseline] Computing pooled statistics...")
    stats = collect_baseline(session_data_list)

    # Validate
    failed = validate_baselines(stats)
    if failed:
        print(
            f"\n[Baseline] ⚠️  STOP: {len(failed)} axis/axes failed variance check: {failed}\n"
            f"Fix metric computation before running ablations."
        )
    else:
        print("\n[Baseline] ✅ All axes passed. Ready for ablation runs.")

    # Print summary
    print("\n[Baseline Stats]")
    for axis, values in stats.items():
        print(
            f"  {axis}: mean={values['mean']:.4f}, std={values['std']:.4f}, n={values.get('n', '?')}"
        )

    logger.close()
    return stats


# ------------------------------------------------------------------ #
#  Stub                                                                #
# ------------------------------------------------------------------ #


def _extract_continuity_axes(prompt, response, drift_session) -> dict:
    """
    STUB — extract raw continuity axis values from a response.
    Wire to your NLP layer. See continuity_vector.py for notes.
    Returns dict with float values for each axis in [0.0, 1.0].
    """
    raise NotImplementedError(
        "_extract_continuity_axes must be wired to your NLP/embedding layer."
    )


# ------------------------------------------------------------------ #
#  Entry                                                               #
# ------------------------------------------------------------------ #

if __name__ == "__main__":
    # STUB: replace with your actual DriftSession init
    drift_session = None  # DriftSession() here

    run_all_baselines(drift_session)
