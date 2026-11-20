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

from drift.core.rcce_transfer import PrincipleTransferPolicy


TASKS = (
    ("t1", "What is 17 + 25? Answer with the integer only.", "42"),
    ("t2", "What is 9 multiplied by 8? Answer with the integer only.", "72"),
    ("t3", "What is 100 minus 37? Answer with the integer only.", "63"),
    ("t4", "What is 12 squared? Answer with the integer only.", "144"),
)


def evaluate():
    if not os.environ.get("GEMINI_API_KEY"):
        raise RuntimeError("GEMINI_API_KEY required")
    from drift.core import brain as module
    from drift.core.brain import DriftBrain

    module.API_KEY = os.environ["GEMINI_API_KEY"]
    module.DRIFT_PREFER_LOCAL = False
    module.DRIFT_USE_LOCAL_FALLBACK = False
    module.DRIFT_USE_HF = False
    module.DRIFT_PRIMARY_MODEL = os.environ.get("DRIFT_PRIMARY_MODEL", "gemini-3.5-flash-lite")
    module.DRIFT_CRITIC_MODEL = module.DRIFT_PRIMARY_MODEL
    records = []
    with tempfile.TemporaryDirectory(prefix="rcce-live-ab-") as directory:
        paths = {
            "enabled": Path(directory) / "enabled.sqlite",
            "disabled": Path(directory) / "disabled.sqlite",
        }
        trained = PrincipleTransferPolicy(paths["enabled"], failure_threshold=1)
        assert trained.record(
            task="training-parser", principle="verify-before-answer",
            strategy="answer without checking", outcome="failure",
            verified=True, evidence="training oracle rejected unverified answer",
        )
        for index, (task_id, question, expected) in enumerate(TASKS):
            # Alternate condition order to reduce order effects.
            order = ("enabled", "disabled") if index % 2 == 0 else ("disabled", "enabled")
            for condition in order:
                policy = PrincipleTransferPolicy(paths[condition], failure_threshold=1)
                choice = policy.choose(
                    principle="verify-before-answer",
                    candidates=["answer without checking", "check arithmetic before answering"],
                )
                prompt = question + "\\nMethod: " + choice.strategy + "."
                bot = DriftBrain()
                if bot.sdk != "google.genai":
                    raise RuntimeError("RCCE_INVALID: non-Gemini SDK")
                answer = bot.think(prompt, rcce_strict=True).strip()
                receipts = bot._rcce_provider_receipts
                if len(receipts) != 2 or any(not r.get("provider_response_id") for r in receipts):
                    raise RuntimeError("RCCE_INVALID: missing provider receipts")
                records.append({
                    "task_id": task_id, "condition": condition,
                    "model": module.DRIFT_PRIMARY_MODEL,
                    "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
                    "strategy": choice.strategy,
                    "answer": answer,
                    "expected": expected,
                    "exact_match": answer == expected,
                    "provider_receipts": receipts,
                })
    print("RCCE_LIVE_AB_EXPLORATORY_NOT_SCORED: " + json.dumps(records, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(evaluate())
    except Exception as exc:
        print("FAIL: " + type(exc).__name__, file=sys.stderr)
        sys.exit(1)
