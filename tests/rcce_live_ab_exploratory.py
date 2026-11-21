"""RCCE-1 live paired evaluation: NOT SCORED until evidence is audited.

Runs genuine DriftBrain strict inference for both conditions. The task oracle
checks a concrete exact answer, not strategy labels or model self-assessment.
"""

import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path

from drift.core.logic_chain import ChainNavigator
from drift.core.rcce_scoring import score_response, summarize_pairs
from drift.core.rcce_transfer import PrincipleTransferPolicy


TASK_BANK = Path(__file__).parent / "data" / "rcce_dev_tasks_v1.json"


def load_tasks():
    bank = json.loads(TASK_BANK.read_text())["tasks"]
    limit = int(os.environ.get("RCCE_TASK_LIMIT", "6"))
    if limit < 1 or limit > len(bank):
        raise ValueError("RCCE_TASK_LIMIT out of range")
    categories = {}
    for task in bank:
        categories.setdefault(task["category"], []).append(task)
    balanced = [task for row in zip(*categories.values(), strict=True) for task in row]
    return balanced[:limit]


def failure_details(exc):
    # Provider error text may include request metadata. Keep only typed fields.
    cause = exc.__cause__ or exc
    code = getattr(cause, "code", None)
    if not isinstance(code, int):
        code = getattr(cause, "status_code", None)
    return {
        "error_type": type(exc).__name__,
        "cause_type": type(cause).__name__,
        "provider_http_status": code if isinstance(code, int) else None,
    }


def evaluate(output, run):
    if not os.environ.get("GEMINI_API_KEY"):
        raise RuntimeError("GEMINI_API_KEY required")
    from drift.core import brain as module
    from drift.core.brain import DriftBrain

    module.API_KEY = os.environ["GEMINI_API_KEY"]
    module.DRIFT_PREFER_LOCAL = False
    module.DRIFT_USE_LOCAL_FALLBACK = False
    module.DRIFT_USE_HF = False
    module.DRIFT_PRIMARY_MODEL = os.environ.get(
        "DRIFT_PRIMARY_MODEL", "gemini-3.5-flash-lite"
    )
    module.DRIFT_CRITIC_MODEL = module.DRIFT_PRIMARY_MODEL
    records = []
    tasks = load_tasks()
    repeats = int(os.environ.get("RCCE_REPEATS", "2"))
    if repeats < 1 or repeats > 5:
        raise ValueError("RCCE_REPEATS must be 1..5")
    with tempfile.TemporaryDirectory(prefix="rcce-live-ab-") as directory:
        paths = {
            "enabled": Path(directory) / "enabled.sqlite",
            "disabled": Path(directory) / "disabled.sqlite",
        }
        trained = PrincipleTransferPolicy(paths["enabled"], failure_threshold=1)
        assert trained.record(
            task="training-parser",
            principle="verify-before-answer",
            strategy="answer without checking",
            outcome="failure",
            verified=True,
            evidence="training oracle rejected unverified answer",
        )
        for index, task in enumerate(tasks * repeats):
            task_id, question, expected = task["id"], task["prompt"], task["expected"]
            repeat = index // len(tasks)
            # Alternate condition order to reduce order effects.
            order = (
                ("enabled", "disabled") if index % 2 == 0 else ("disabled", "enabled")
            )
            for condition in order:
                policy = PrincipleTransferPolicy(paths[condition], failure_threshold=1)
                choice = policy.choose(
                    principle="verify-before-answer",
                    candidates=[
                        "answer without checking",
                        "check arithmetic before answering",
                    ],
                )
                prompt = question + "\nMethod: " + choice.strategy + "."
                run["active_trial"] = {
                    "task_id": task_id,
                    "repeat": repeat,
                    "condition": condition,
                    "stage": "construct",
                }
                bot = DriftBrain()
                if bot.sdk != "google.genai":
                    raise RuntimeError("RCCE_INVALID: non-Gemini SDK")
                bot.chain_navigator = ChainNavigator()
                try:
                    run["active_trial"]["stage"] = "inference"
                    answer = bot.think(prompt, rcce_strict=True).strip()
                finally:
                    receipts = bot._rcce_provider_receipts
                    run["active_trial"]["provider_receipts"] = receipts
                    bot.client.close()
                if len(receipts) != 2 or any(
                    not r.get("provider_response_id") for r in receipts
                ):
                    raise RuntimeError("RCCE_INVALID: missing provider receipts")
                records.append(
                    {
                        "task_id": task_id,
                        "repeat": repeat,
                        "category": task["category"],
                        "condition": condition,
                        "model": module.DRIFT_PRIMARY_MODEL,
                        "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
                        "strategy": choice.strategy,
                        "answer": answer,
                        "expected": expected,
                        **score_response(answer, expected, task["format"]),
                        "exact_match": answer == expected,
                        "provider_receipts": receipts,
                    }
                )
                run.update(status="in_progress", trials=records)
                del run["active_trial"]
                output.write_text(json.dumps(run, indent=2))
    summary = summarize_pairs(records)
    run.update(status="complete", summary=summary)
    output.write_text(json.dumps(run, indent=2))
    print("RCCE_LIVE_AB_EXPLORATORY_NOT_SCORED: " + json.dumps(summary, sort_keys=True))
    return 0


def main():
    output = Path(os.environ.get("RCCE_RESULTS_PATH", "rcce-live-ab-results.json"))
    run = {"status": "started", "trials": []}
    output.write_text(json.dumps(run, indent=2))
    try:
        return evaluate(output, run)
    except Exception as exc:
        details = failure_details(exc)
        # DriftBrain wraps each inference phase. Preserve its fixed label only.
        if exc.args and exc.args[0] in (
            "RCCE_INVALID: primary inference failed",
            "RCCE_INVALID: critic inference failed",
        ):
            details["error_message"] = exc.args[0]
        run.update(status="failed", **details)
        output.write_text(json.dumps(run, indent=2))
        print("FAIL: " + json.dumps(details, sort_keys=True), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
