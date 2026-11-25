"""Frozen exploratory RCCE state ablation using the genuine Gemini runner.

The primary endpoint is paired strict A/B accuracy, restored minus removed,
over 24 profile/task pairs. Restored minus swapped is the state-specificity
check. An incomplete provider run cannot establish either contrast.
"""

import json
import os
import random
import subprocess
import sys
from pathlib import Path

from rcce_partner_pilot import (
    PARTNERS,
    PrincipleTransferPolicy,
    digest,
    failure_details,
    load_history,
    prepare,
    render_prompt,
    run_inference,
)

CONDITIONS = ("restored", "swapped", "removed")
ORDER_SEED = 9413
TASKS = (
    ("copper-101", (13, 102), (28, 64)),
    ("copper-102", (46, 27), (18, 49)),
    ("copper-103", (12, 69), (35, 52)),
    ("copper-104", (16, 48), (7, 84)),
    ("indigo-101", (31, 75), (39, 44)),
    ("indigo-102", (61, 38), (29, 81)),
    ("indigo-103", (42, 63), (19, 74)),
    ("indigo-104", (8, 59), (17, 32)),
    ("quartz-101", (34, 68), (51, 29)),
    ("quartz-102", (23, 19), (9, 36)),
    ("quartz-103", (27, 55), (52, 49)),
    ("quartz-104", (30, 51), (12, 77)),
)
ANSWER_KEYS = {
    "copper-101": {"P1": "A", "P2": "B"},
    "copper-102": {"P1": "B", "P2": "A"},
    "copper-103": {"P1": "A", "P2": "B"},
    "copper-104": {"P1": "B", "P2": "A"},
    "indigo-101": {"P1": "B", "P2": "A"},
    "indigo-102": {"P1": "A", "P2": "B"},
    "indigo-103": {"P1": "A", "P2": "B"},
    "indigo-104": {"P1": "B", "P2": "A"},
    "quartz-101": {"P1": "A", "P2": "B"},
    "quartz-102": {"P1": "B", "P2": "A"},
    "quartz-103": {"P1": "A", "P2": "B"},
    "quartz-104": {"P1": "B", "P2": "A"},
}


def planned_trials(root):
    rng = random.Random(ORDER_SEED)
    partners = tuple(PARTNERS)
    for task in TASKS:
        task_id = task[0]
        context = task_id.split("-")[0]
        blocks = list(partners)
        rng.shuffle(blocks)
        for partner in blocks:
            alternate = next(key for key in partners if key != partner)
            order = list(CONDITIONS)
            rng.shuffle(order)
            history = load_history(root / f"{partner}.sqlite")
            for condition in order:
                source = {"swapped": alternate, "restored": partner}.get(condition)
                recommendation = "infer"
                if source is not None:
                    db = root / f"{source}.sqlite"
                    policy = PrincipleTransferPolicy(db, failure_threshold=1)
                    recommendation = policy.choose(
                        principle=context, candidates=list(STRATEGIES)
                    ).strategy
                yield (
                    {
                        "task_id": task_id,
                        "partner": partner,
                        "condition": condition,
                        "source": source,
                        "history_sha256": digest(json.dumps(history).encode()),
                        "recommendation": recommendation,
                        "expected": ANSWER_KEYS[task_id][partner],
                    },
                    render_prompt(task, history, recommendation),
                )


def evaluate(root, output):
    run = {"status": "started", "trials": [], "order_seed": ORDER_SEED}
    output.write_text(json.dumps(run))
    try:
        subprocess.run([sys.executable, __file__, "prepare", str(root)], check=True)
        manifest = json.loads((root / "training.json").read_text())
        if manifest["training_pid"] == os.getpid():
            raise RuntimeError("training and evaluation must be separate processes")
        for partner, checksum in manifest["stores"].items():
            if digest((root / f"{partner}.sqlite").read_bytes()) != checksum:
                raise RuntimeError("saved controller state changed before restart")
        from drift.core import brain

        brain.API_KEY = os.environ["GEMINI_API_KEY"]
        brain.DRIFT_PRIMARY_MODEL = os.environ["DRIFT_PRIMARY_MODEL"]
        brain.DRIFT_CRITIC_MODEL = brain.DRIFT_PRIMARY_MODEL
        brain.DRIFT_PREFER_LOCAL = brain.DRIFT_USE_LOCAL_FALLBACK = (
            brain.DRIFT_USE_HF
        ) = False
        run.update(
            status="in_progress",
            training=manifest,
            evaluation_pid=os.getpid(),
            model=brain.DRIFT_PRIMARY_MODEL,
            github_sha=os.environ.get("GITHUB_SHA"),
        )
        for trial, prompt in planned_trials(root):
            run["active_trial"] = trial
            answer, primary, receipts = run_inference(prompt)
            run["trials"].append(
                {
                    **trial,
                    "prompt": prompt,
                    "prompt_sha256": digest(prompt.encode()),
                    "answer": answer,
                    "primary_answer": primary,
                    "correct": answer == trial["expected"],
                    "provider_receipts": receipts,
                }
            )
            del run["active_trial"]
            output.write_text(json.dumps(run, indent=2))
        ids = [
            receipt["provider_response_id"]
            for row in run["trials"]
            for receipt in row["provider_receipts"]
        ]
        if len(ids) != 144 or len(set(ids)) != 144:
            raise RuntimeError("expected 144 distinct Gemini response IDs")
        run["summary"] = {
            condition: sum(
                r["correct"] for r in run["trials"] if r["condition"] == condition
            )
            for condition in CONDITIONS
        }
        run["accuracy_deltas"] = {
            "restored_minus_removed": (run["summary"]["restored"] - run["summary"]["removed"]) / 24,
            "restored_minus_swapped": (run["summary"]["restored"] - run["summary"]["swapped"]) / 24,
        }
        run["status"] = "complete"
        print(json.dumps(run["summary"], sort_keys=True))
    except Exception as exc:
        run.update(status="failed", **failure_details(exc))
        print(json.dumps(failure_details(exc), sort_keys=True), file=sys.stderr)
        return 1
    finally:
        output.write_text(json.dumps(run, indent=2))
    return 0


if __name__ == "__main__":
    mode, destination, *rest = sys.argv[1:]
    if mode == "prepare":
        prepare(Path(destination))
    elif mode == "evaluate":
        raise SystemExit(evaluate(Path(destination), Path(rest[0])))
    else:
        raise SystemExit("expected prepare or evaluate")
