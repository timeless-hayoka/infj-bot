"""Run isolated, offline restart probes through drift ask."""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import random
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SETUP = (
    (
        "preference",
        "For Project Alder I prefer bullet lists. My workspace is Birch Studio.",
    ),
    (
        "decision",
        "Project Alder will ship as a CSV export. The delivery day is Tuesday.",
    ),
    (
        "task",
        "For Project Alder, collect, deduplicate, then export. Collection is complete. Deduplication is the next unfinished step.",
    ),
    ("update", "Project Alder delivery moved to Thursday. This supersedes Tuesday."),
    ("distractor", "Project Willow uses a PDF export and ships on Friday."),
)
QUESTION = (
    "For Project Alder, what is my preferred response format, workspace, export format, "
    "current delivery day, completed step, and next unfinished step? "
    "Do you remember a reviewer? Return a JSON object with keys preference, workspace, "
    "format, day, completed, next, reviewer. Use null for unknown values."
)
EXPECTED = {
    "preference": "bullet lists",
    "workspace": "birch studio",
    "format": "csv",
    "day": "thursday",
    "completed": "collect",
    "next": "deduplicate",
    "reviewer": None,
}
FOCUS = "Alder internal focus"
ACK = "Acknowledged."
MOCK_RESPONSE = json.dumps(dict.fromkeys(EXPECTED))
PRIMARY = "continuity-mock-primary"
CRITIC = "continuity-mock-critic"
FIXED_SETTINGS = {"max_tokens": 700, "temperature": 0, "top_p": 1}


def score(response):
    """Score independent dimensions. Null means abstention, never a guessed value."""
    values = json.loads(response)
    if not isinstance(values, dict) or values.keys() != EXPECTED.keys():
        raise ValueError("Response must contain exactly the seven requested fields")
    values = {
        key: value.strip().casefold() if isinstance(value, str) else value
        for key, value in values.items()
    }
    correct = {key: values[key] == expected for key, expected in EXPECTED.items()}
    return {
        "retained": [int(correct["preference"]) + int(correct["workspace"]), 2],
        "decision": [int(correct["format"]), 1],
        "supersession": [int(correct["day"]), 1],
        "continuation": [int(correct["completed"]) + int(correct["next"]), 2],
        "unsupported_claims": [int(values["reviewer"] is not None), 1],
        "contradictions": [
            sum(
                values[key] is not None and not correct[key]
                for key in EXPECTED
                if key != "reviewer"
            ),
            6,
        ],
    }


def isolated_env(root):
    return {
        "PATH": os.defpath,
        "HOME": str(root / "home"),
        "XDG_CACHE_HOME": str(root / "cache"),
        "TMPDIR": str(root),
        "PYTHONPATH": str(ROOT),
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONHASHSEED": "0",
        "PYTHON_DOTENV_DISABLED": "1",
        "HF_HUB_OFFLINE": "1",
        "TRANSFORMERS_OFFLINE": "1",
        "DRIFT_OS_ROOT": str(root / "state"),
        "DRIFT_USE_LOCAL_EMBEDDINGS": "true",
        "DRIFT_FAST_MODE": "false",
        "DRIFT_USE_HF": "false",
        "DRIFT_USE_OPENAI": "true",
        "OPENAI_API_KEY": "synthetic-placeholder",
        "DRIFT_USE_GEMINI": "false",
        "DRIFT_USE_GROQ": "false",
        "DRIFT_USE_KIMI": "false",
        "DRIFT_USE_LOCAL_FALLBACK": "false",
        "DRIFT_BYPASS_CACHE": "1",
        "ANONYMIZED_TELEMETRY": "False",
        "OTEL_SDK_DISABLED": "true",
    }


def fail_network(*_args, **_kwargs):
    raise AssertionError("Network access is disabled for restart probes")


def worker(phase):
    started = time.perf_counter()
    random.seed(42)
    from drift.core.being import get_being
    from drift.core.causal_wiring import retrieved_memory_keys_var
    from drift.core.embodiment import get_embodiment
    from drift.core.global_workspace import get_workspace
    from drift.core.history import ChatHistory
    from drift.core.homeostasis import get_homeostasis
    from drift.core.jsonl_logger import HardenedJsonlLogger
    from drift.core.memory import DriftMemory
    from drift.core.plugins.documents import DocumentStore
    from drift.core.plugins.goals import GoalsDB
    from drift.core.plugins.preferences import DEFAULT_PREFS, PreferenceStore

    from drift.core import anchor_context, being_snapshot, brain, security_defense
    from drift.interfaces.cli import cmd_ask

    calls = []
    fresh_history_sizes = []
    fallback_calls = []
    original_retrieve = DriftMemory.retrieve_context

    def observe_fallback(self, *args, **kwargs):
        fallback_calls.append(True)
        return original_retrieve(self, *args, **kwargs)

    original_init = brain.DriftBrain.__init__

    def observe_init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        fresh_history_sizes.append(len(self.history))

        def generate(_cache_key, system, prompt, *, budget=None, **requested):
            calls.append((self._active_model_name, system, prompt, requested))
            return mock_provider(**FIXED_SETTINGS)

        self._governor.generate = generate

    def mock_provider(**settings):
        assert settings == FIXED_SETTINGS
        return ACK if phase == "seed" else MOCK_RESPONSE

    def ask(message, save, mode="companion"):
        args = argparse.Namespace(
            prompt=[message], mode=mode, no_tools=True, no_save=not save
        )
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            status = cmd_ask(args)
        assert status == 0, stdout.getvalue()
        return stdout.getvalue().strip()

    being = get_being()
    body = get_embodiment()
    regulator = get_homeostasis()
    memory = DriftMemory().unified_manager
    docs = DocumentStore()
    history = ChatHistory()
    prefs = PreferenceStore()
    goals = GoalsDB()
    with (
        patch.object(brain, "DRIFT_PRIMARY_MODEL", PRIMARY),
        patch.object(brain, "DRIFT_CRITIC_MODEL", CRITIC),
        patch.object(brain.DriftBrain, "__init__", observe_init),
        patch.object(DriftMemory, "retrieve_context", observe_fallback),
        patch.object(
            security_defense,
            "_security_logger",
            HardenedJsonlLogger(Path.cwd() / "state" / "security_audit.jsonl"),
        ),
        patch.object(
            anchor_context, "format_anchor_vault_prompt_block", return_value=""
        ),
        patch.object(anchor_context, "search_vault_knowledge", return_value=[]),
    ):
        if phase == "seed":
            for label, message in SETUP:
                # A separate mode gives the distractor its own DMU category.
                mode = "quiet" if label == "distractor" else "companion"
                assert ask(message, save=True, mode=mode) == ACK
            # Seed structured state through its normal writer, independently of recall.
            being.state.focus = FOCUS
            body.state.heartbeat_rate = 93
            body._save_state()
            regulator.update_need("connection", 0.07, damping_factor=1)
            being.evolve(interaction_happened=True)
            return {"pid": os.getpid(), "setup_turns": len(SETUP)}

        sqlite_records = {
            entry.event.content: entry.unified_id
            for entry in memory.get_recent_sync("interaction", limit=100)
        }
        vector_records = memory.collection.get(include=["documents"])
        vector_by_content = dict(
            zip(vector_records["documents"], vector_records["ids"], strict=True)
        )
        assert sqlite_records == vector_by_content
        stored_labels = {
            label: sqlite_records[content]
            for label, message in SETUP
            if (content := f"user: {message}\nBot: {ACK}") in sqlite_records
        }
        before = {
            "sqlite": len(sqlite_records),
            "vectors": len(vector_by_content),
            "archive": history.count(),
            "documents": docs.count(),
            "preferences_at_defaults": prefs.all() == DEFAULT_PREFS,
            "active_goals": len(goals.list_goals()),
            "workspace_items": get_workspace().get_stats()["current_contents"],
            "spark_history": len(being.spark_train.spark_history),
            "echo_records": len(being.memory_echo_pool),
            "focus": being.state.focus,
            "heartbeat": body.state.heartbeat_rate,
            "connection": regulator.needs["connection"].current,
            "structured_interactions": being.state.total_interactions,
        }
        snapshot_db = Path(being_snapshot.BEING_DB_PATH)
        cache = Path.home() / ".drift" / "drift_gen_cache.sqlite3"
        before["generation_cache_entries"] = count_rows(
            cache, "SELECT count(*) FROM cache"
        )
        before["snapshots"] = count_rows(
            snapshot_db, "SELECT count(*) FROM cognitive_snapshots"
        )

        response = ask(QUESTION, save=False)
        assert [call[0] for call in calls] == [PRIMARY, CRITIC]
        _, system, prompt, options = calls[0]
        assert prompt.startswith("Recent conversation:\n\n"), prompt[:200]
        assert fresh_history_sizes == [0]
        assert history.count() == before["archive"]
        assert memory.count_sync("interaction") == before["sqlite"]
        ids = retrieved_memory_keys_var.get()
        assert QUESTION in prompt
        _, marker, recall_section = prompt.partition("Memory context below is context")
        assert marker
        assert not any(
            message in system or message in prompt.split(marker, 1)[0]
            for _, message in SETUP
        )
        return {
            "pid": os.getpid(),
            "stores": before,
            "stored_labels": stored_labels,
            "retrieval_route": "standard fallback" if fallback_calls else "DMU",
            "retrieved_ids": ids,
            "memory_context": sorted(
                (label for label, message in SETUP if message in recall_section),
                key=lambda label: recall_section.index(dict(SETUP)[label]),
            ),
            "focus_context": f"Current focus: {FOCUS}" in prompt,
            "heartbeat_context": "Heartbeat: 93" in prompt,
            "need_context": "connection: 7%" in prompt,
            "core_prompt_available": not system.startswith("ERROR: DRIFT_CORE_PROMPT"),
            "requested_generation_options": options,
            "effective_mock_settings": FIXED_SETTINGS,
            "model_boundary_calls": [PRIMARY, CRITIC],
            "prompt_characters": len(prompt) + len(system),
            "runtime_seconds": round(time.perf_counter() - started, 3),
            "history_at_start": fresh_history_sizes[0],
            "response": response,
        }


def count_rows(path, query):
    if not path.is_file():
        return 0
    with contextlib.closing(
        sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True)
    ) as conn:
        return conn.execute(query).fetchone()[0]


def run_worker(root, phase):
    result = subprocess.run(
        [sys.executable, str(Path(__file__).resolve()), "--worker", phase],
        cwd=root,
        check=False,
        env=isolated_env(root),
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode:
        raise RuntimeError(result.stderr + result.stdout)
    return json.loads(result.stdout)


def evaluate():
    with tempfile.TemporaryDirectory(prefix="drift-continuity-") as folder:
        root = Path(folder)
        paths = {
            name: root / name
            for name in ("on", "discard", "off", "structured", "memory")
        }
        for path in paths.values():
            path.mkdir()
        seeds = [run_worker(paths[name], "seed") for name in ("on", "discard")]
        on_state = paths["on"] / "state"
        structured = paths["structured"] / "state"
        structured.mkdir()
        for filename in ("being.db", "embodiment.db", "homeostasis.db"):
            shutil.copy2(on_state / filename, structured / filename)
        shutil.copytree(
            on_state / "memory" / "chroma",
            paths["memory"] / "state" / "memory" / "chroma",
        )
        results = {
            name: run_worker(paths[name], "probe")
            for name in ("on", "off", "structured", "memory")
        }

    on, off = results["on"], results["off"]
    assert len({item["pid"] for item in (*seeds, *results.values())}) == 6
    assert (
        on["stores"]["sqlite"]
        == on["stores"]["vectors"]
        == on["stores"]["archive"]
        == len(SETUP)
    )
    assert not any(
        off["stores"][key]
        for key in (
            "sqlite",
            "vectors",
            "archive",
            "snapshots",
            "structured_interactions",
        )
    )
    assert on["stores"]["documents"] == off["stores"]["documents"] == 0
    assert on["stores"]["snapshots"] == on["stores"]["structured_interactions"] == 1
    assert on["stores"]["focus"] == FOCUS and off["stores"]["focus"] == ""
    assert on["stores"]["heartbeat"] == 93 and off["stores"]["heartbeat"] == 60
    assert on["stores"]["connection"] == 0.07 and off["stores"]["connection"] != 0.07
    labels = {label for label, _ in SETUP}
    assert set(on["stored_labels"]) == set(on["memory_context"]) == labels
    assert set(on["stored_labels"].values()) == set(on["retrieved_ids"])
    assert not off["memory_context"] and not off["retrieved_ids"]
    assert on["retrieval_route"] == "DMU"
    assert off["retrieval_route"] == "standard fallback"
    for key in ("focus_context", "heartbeat_context", "need_context"):
        assert on[key] and not off[key], key
    structured, memory = results["structured"], results["memory"]
    assert memory["retrieval_route"] == "DMU"
    assert set(memory["memory_context"]) == labels
    assert set(memory["stored_labels"].values()) == set(memory["retrieved_ids"])
    assert not structured["retrieved_ids"] and not structured["memory_context"]
    for key in ("focus_context", "heartbeat_context", "need_context"):
        assert structured[key] and not memory[key], key
    for result in results.values():
        assert result["effective_mock_settings"] == FIXED_SETTINGS
        assert result["stores"]["preferences_at_defaults"]
        assert not any(
            result["stores"][key]
            for key in (
                "documents",
                "active_goals",
                "workspace_items",
                "spark_history",
                "echo_records",
                "generation_cache_entries",
            )
        )
        assert result["core_prompt_available"] == off["core_prompt_available"]
    return {
        "wiring": "PASSED",
        "live_behavior": "NOT RUN",
        "setup_processes": seeds,
        "conditions": results,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker", choices=("seed", "probe"), help=argparse.SUPPRESS)
    parser.add_argument("--score", type=Path, help="Score a raw JSON response offline")
    args = parser.parse_args()
    if args.worker:
        expected = isolated_env(Path.cwd())
        assert all(os.environ.get(key) == value for key, value in expected.items())
        # Python can add LC_CTYPE during locale coercion.
        assert not set(os.environ) - set(expected) - {"LC_CTYPE"}
        with (
            patch.object(socket.socket, "connect", fail_network),
            patch.object(socket.socket, "connect_ex", fail_network),
        ):
            result = worker(args.worker)
    elif args.score:
        result = score(args.score.read_text(encoding="utf-8"))
    else:
        result = evaluate()
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
