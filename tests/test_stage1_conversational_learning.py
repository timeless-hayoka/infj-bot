"""Matched restart pilot at the real conversational prompt boundary (offline)."""
import json
import os
import secrets
import sqlite3
import subprocess
import sys

import pytest


CASES = [
    ("parser-repair", "retry-unchanged", "inspect-cause"),
    ("schema-repair", "guess-schema", "validate-schema"),
    ("cache-repair", "reuse-stale", "refresh-cache"),
    ("config-repair", "assume-default", "check-config"),
]


def _run(code, args, env):
    completed = subprocess.run(
        [sys.executable, "-c", code, *map(str, args)], env=env,
        capture_output=True, text=True, timeout=90, check=False,
    )
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout.splitlines()[-1])


WRITER = """
import json, os, sys
from drift.core.cognitive_learning_bridge import CognitiveLearningBridge
db, task, wrong, right, condition = sys.argv[1:]
bridge = CognitiveLearningBridge(db)
bridge.record(task, wrong, "success", verified=True, evidence="initial-observation", source="test-oracle")
if condition == "corrected":
    root = bridge.history(task)[0]["id"]
    bridge.correct(root, "failure", evidence="reviewed-observation", source="test-oracle")
print(json.dumps({"pid": os.getpid(), "history": bridge.history(task)}))
"""

READER = """
import json, os, sys
from drift.core.commands import BotState
from drift.core.cognitive_orchestrator import CognitiveOrchestrator
from drift.core.memory import DriftMemory
from drift.core.prompt_builder import build_chat_prompt
db, task, wrong, right = sys.argv[1:]
orchestrator = CognitiveOrchestrator()
orchestrator.enable_cognitive_learning(db)
memory = DriftMemory(use_semantic=False)
state = BotState(mode="engineer", proactive_enabled=False)
prompt, _, _ = build_chat_prompt(
    "What is the next troubleshooting step?", state, memory, tools_enabled=False,
    orchestrator=orchestrator, learning_task=task, learning_candidates=[wrong, right],
)
prefix = "[Verified strategy selection] "
lines = [line[len(prefix):] for line in prompt.splitlines() if line.startswith(prefix)]
assert len(lines) == 1, "expected one complete strategy block in actual conversational prompt"
data = json.loads(lines[0])
assert data["task"] == task
assert data["strategy"] in [wrong, right]
print(json.dumps({"pid": os.getpid(), "selection": data["strategy"], "prompt": prompt}))
"""


@pytest.mark.parametrize("task,wrong,right", CASES)
def test_corrected_feedback_improves_conversational_prompt_after_restart(tmp_path, task, wrong, right):
    observations = {}
    for condition in ("uncorrected", "corrected"):
        root = tmp_path / condition
        root.mkdir()
        db = root / "learning.db"
        env = dict(os.environ)
        env.update({
            "DRIFT_OS_ROOT": str(root / "state"),
            "DRIFT_VAULT_PATH": str(root / "state" / "vault.jsonl"),
            "DRIFT_VAULT_SECRET": secrets.token_hex(32),
            "DRIFT_USE_LOCAL_EMBEDDINGS": "1",
            "ANONYMIZED_TELEMETRY": "False",
            "HF_HUB_OFFLINE": "1",
        })
        for key in ("API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY"):
            env.pop(key, None)
        writer = _run(WRITER, [db, task, wrong, right, condition], env)
        reader = _run(READER, [db, task, wrong, right], env)
        assert writer["pid"] != reader["pid"]
        # Independent SQL inspection rather than reusing controller replay.
        with sqlite3.connect(db) as connection:
            events = connection.execute(
                "SELECT outcome,corrects_id FROM cognitive_evidence ORDER BY id"
            ).fetchall()
        assert events[0] == ("success", None)
        if condition == "corrected":
            assert len(events) == 2 and events[1][0] == "failure" and events[1][1] is not None
        else:
            assert len(events) == 1
        observations[condition] = reader["selection"]
        print(json.dumps({"task": task, "condition": condition, "writer_pid": writer["pid"],
                          "reader_pid": reader["pid"], "selected": reader["selection"],
                          "expected": right, "correct": reader["selection"] == right}))
    assert observations == {"uncorrected": wrong, "corrected": right}
