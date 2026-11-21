"""Live RCCE partner-state pilot with synthetic feedback and unseen option pairs."""

import hashlib
import json
import os
import random
import sqlite3
import subprocess
import sys
from pathlib import Path

from drift.core.logic_chain import ChainNavigator
from drift.core.rcce_transfer import PrincipleTransferPolicy

from rcce_live_ab_exploratory import failure_details

PARTNERS = {
    "P1": {"copper": "fast", "indigo": "cheap", "quartz": "fast"},
    "P2": {"copper": "cheap", "indigo": "fast", "quartz": "cheap"},
}
STRATEGIES = ("fast", "cheap")
CONDITIONS = ("restored", "swapped", "replay")
ORDER_SEED = 731
# Each tuple gives minutes and credits for options A and B. The minima disagree.
TASKS = (
    ("copper-1", (11, 37), (18, 25)),
    ("copper-2", (24, 16), (19, 21)),
    ("copper-3", (30, 15), (21, 23)),
    ("indigo-1", (14, 31), (20, 18)),
    ("indigo-2", (27, 20), (23, 33)),
    ("indigo-3", (16, 42), (28, 39)),
    ("quartz-1", (25, 38), (33, 27)),
    ("quartz-2", (41, 26), (35, 34)),
    ("quartz-3", (32, 19), (45, 14)),
)


def digest(blob):
    return hashlib.sha256(blob).hexdigest()


def prepare(root):
    """Feed explicit synthetic partner feedback into isolated controller stores."""
    root.mkdir(parents=True, exist_ok=False)
    stores = {}
    for partner, preferences in PARTNERS.items():
        db = root / f"{partner}.sqlite"
        policy = PrincipleTransferPolicy(db, failure_threshold=1)
        for context, accepted in preferences.items():
            for strategy in STRATEGIES:
                outcome = "success" if strategy == accepted else "failure"
                recorded = policy.record(
                    task=f"training-{context}-{strategy}",
                    principle=context,
                    strategy=strategy,
                    outcome=outcome,
                    verified=True,
                    evidence=f"simulated partner feedback: {outcome}",
                )
                if not recorded:
                    raise RuntimeError("training evidence was rejected")
        stores[partner] = digest(db.read_bytes())
    manifest = {"training_pid": os.getpid(), "stores": stores}
    (root / "training.json").write_text(json.dumps(manifest))


def load_history(db):
    with sqlite3.connect(db) as conn:
        return conn.execute(
            "SELECT principle, strategy, outcome FROM rcce_principle_outcomes ORDER BY id"
        ).fetchall()


def render_prompt(task, history, recommendation):
    task_id, option_a, option_b = task
    context = task_id.split("-")[0]
    rendered = "\n".join(
        f"{label}: {strategy} -> {outcome}" for label, strategy, outcome in history
    )
    return (
        "Choose an option for the person whose feedback is listed below. "
        "Fast means lower minutes. Cheap means lower credits. "
        "If the recommendation is infer, infer the criterion from feedback for the current context. "
        "Otherwise apply the recommendation.\n"
        f"Historical feedback:\n{rendered}\n"
        f"Current context: {context}\n"
        f"Recommendation: {recommendation}\n"
        f"Option A: {option_a[0]} minutes, {option_a[1]} credits.\n"
        f"Option B: {option_b[0]} minutes, {option_b[1]} credits.\n"
        "Return exactly one uppercase letter, A or B."
    )


def expected_answer(task, partner):
    task_id, option_a, option_b = task
    context = task_id.split("-")[0]
    metric = STRATEGIES.index(PARTNERS[partner][context])
    if option_a[metric] == option_b[metric]:
        raise ValueError(f"tied options for {task_id}")
    return "A" if option_a[metric] < option_b[metric] else "B"


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
            for condition in order:
                source = alternate if condition == "swapped" else partner
                db = root / f"{source}.sqlite"
                history = load_history(db)
                recommendation = "infer"
                if condition != "replay":
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
                        "expected": expected_answer(task, partner),
                    },
                    render_prompt(task, history, recommendation),
                )


def run_inference(prompt):
    from drift.core.brain import DriftBrain

    bot = DriftBrain()
    if bot.sdk != "google.genai":
        raise RuntimeError("official Gemini SDK required")
    bot.chain_navigator = ChainNavigator()
    try:
        answer = bot.think(prompt, rcce_strict=True)
        receipts = bot._rcce_provider_receipts
        outputs = bot._rcce_provider_outputs
    finally:
        bot.client.close()

    if (
        len(receipts) != 2
        or len(outputs) != 2
        or outputs[1] != answer
        or any(not receipt.get("provider_response_id") for receipt in receipts)
    ):
        raise RuntimeError("incomplete provider evidence")
    return answer, outputs[0], receipts


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
        run["summary"] = {
            condition: sum(
                r["correct"] for r in run["trials"] if r["condition"] == condition
            )
            for condition in CONDITIONS
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
