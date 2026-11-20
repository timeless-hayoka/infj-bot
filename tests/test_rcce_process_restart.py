"""Process-boundary persistence verification for real SQLite strategy state.

Offline verification: does not establish language-model cognitive improvement.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

from drift.core.rcce_transfer import PrincipleTransferPolicy


def test_verified_strategy_survives_fresh_python_process(tmp_path):
    db = tmp_path / "restart.sqlite"
    policy = PrincipleTransferPolicy(db, failure_threshold=1)
    assert policy.record(
        task="parser timeout", principle="diagnose-before-retry",
        strategy="retry unchanged", outcome="failure", verified=True,
        evidence="deterministic failure oracle: unchanged retry rejected",
    )
    script = """
import json, sys
from drift.core.rcce_transfer import PrincipleTransferPolicy
policy = PrincipleTransferPolicy(sys.argv[1], failure_threshold=1)
print(json.dumps({
    "transfer": policy.choose(principle="diagnose-before-retry",
        candidates=["retry unchanged", "inspect cause"]).strategy,
    "control": policy.choose(principle="unrelated",
        candidates=["retry unchanged", "inspect cause"]).strategy,
}))
"""
    env = dict(os.environ)
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1]) + os.pathsep + env.get("PYTHONPATH", "")
    result = subprocess.run(
        [sys.executable, "-c", script, str(db)],
        cwd=Path(__file__).resolve().parents[1],
        env=env, capture_output=True, text=True, timeout=30, check=True,
    )
    assert json.loads(result.stdout.strip().splitlines()[-1]) == {
        "transfer": "inspect cause",
        "control": "retry unchanged",
    }


def test_unverified_strategy_does_not_survive_restart(tmp_path):
    db = tmp_path / "unverified.sqlite"
    policy = PrincipleTransferPolicy(db, failure_threshold=1)
    assert not policy.record(
        task="parser timeout", principle="diagnose-before-retry",
        strategy="retry unchanged", outcome="failure", verified=False,
        evidence="unverified statement",
    )
    restarted = PrincipleTransferPolicy(db, failure_threshold=1)
    assert restarted.choose(
        principle="diagnose-before-retry",
        candidates=["retry unchanged", "inspect cause"],
    ).strategy == "retry unchanged"
