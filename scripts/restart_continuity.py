"""Run isolated restart probes through drift ask; live providers are opt-in."""

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

from local_continuity import override

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
    "Do you remember a reviewer? Return only a raw JSON object with keys preference, workspace, "
    "format, day, completed, next, reviewer. Use null for unknown values. "
    "Do not use markdown fences or add commentary."
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


def score(response, expected=None):
    """Score independent dimensions. Null means abstention, never a guessed value."""
    expected = EXPECTED if expected is None else expected
    from local_continuity import decode_answer

    values, _ = decode_answer(response)
    if not isinstance(values, dict) or values.keys() != expected.keys():
        raise ValueError("Response must contain exactly the seven requested fields")
    from local_continuity import normalize_field

    values = {key: normalize_field(key, value) for key, value in values.items()}
    correct = {key: values[key] == value for key, value in expected.items()}
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


def isolated_env(root, provider=None):
    env = {
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
        "DRIFT_USE_OPENAI": "false",
        "DRIFT_USE_GEMINI": "false",
        "DRIFT_USE_GROQ": "false",
        "DRIFT_USE_KIMI": "false",
        "DRIFT_USE_LOCAL_FALLBACK": "false",
        "DRIFT_BYPASS_CACHE": "1",
        "DRIFT_PROMPT_CONTEXT_CHARS": "16000",
        "DRIFT_PROMPT_TOTAL_CHARS": "24000",
        "ANONYMIZED_TELEMETRY": "False",
        "OTEL_SDK_DISABLED": "true",
    }
    if provider == "gemini":
        from local_continuity import gemini_api_key

        name, value = gemini_api_key()
        env[name] = value
    return env


def fail_network(*_args, **_kwargs):
    raise AssertionError("Network access is disabled for restart probes")


def worker(phase, local_config):
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

    # Real absence checks replace the former mocked empty vault responses.
    # A sibling ANCHOR source checkout may exist for its integration tests; the
    # continuity run refuses a mounted external vault and never calls a vault
    # search tool because this probe has tools disabled.
    assert not anchor_context.get_anchor_runtime()["configured"]

    live_calls = []
    provider = None
    if local_config:
        from drift.core.context_optimizer import compress_prompt
        from local_continuity import (
            GeminiProvider,
            LlamaCppProvider,
            OllamaProvider,
            variant_messages,
        )

        # The application loader currently resolves above this checkout.
        # Record and send the canonical repository prompt explicitly for this eval.
        source = Path(local_config["system_prompt"])
        brain.INFJ_SYSTEM_PROMPT = compress_prompt(source.read_text(encoding="utf-8"))
        assert brain.INFJ_SYSTEM_PROMPT.strip()
        assert not brain.INFJ_SYSTEM_PROMPT.startswith("ERROR:")
        config = dict(
            local_config, artifact_dir=str(Path(local_config["artifact_dir"]) / phase)
        )
        Path(config["artifact_dir"]).mkdir(exist_ok=True)
        provider_class = {
            "llama-cpp": LlamaCppProvider,
            "gemini": GeminiProvider,
            "ollama": OllamaProvider,
        }[config.get("provider", "ollama")]
        provider = provider_class(config)
        PRIMARY = CRITIC = config["model"]

    calls = []
    generation_errors = []
    fresh_history_sizes = []
    fallback_calls = []
    original_retrieve = DriftMemory.retrieve_context

    def observe_fallback(self, *args, **kwargs):
        fallback_calls.append(True)
        return original_retrieve(self, *args, **kwargs)

    original_init = brain.DriftBrain.__init__

    def observe_init(self, *args, **kwargs):
        def generate(_cache_key, system, prompt, *, budget=None, **requested):
            calls.append((self._active_model_name, system, prompt, requested))
            if provider:
                variant = config.get("variant", "current")
                role = "critic" if len(live_calls) % 2 else "primary"
                if phase == "probe":
                    replacement_system, replacement_prompt = variant_messages(
                        variant,
                        role,
                        config["scenario"],
                        calls[0][2],
                        live_calls[0]["response"]
                        if role == "critic" and live_calls
                        else None,
                    )
                    if replacement_system is not None:
                        system, prompt = replacement_system, replacement_prompt
                try:
                    live_calls.append(provider.generate(system, prompt))
                except Exception as error:
                    generation_errors.append(error)
                    raise
                return live_calls[-1]["response"]
            raise RuntimeError("A real local provider is required")

        if provider:
            from types import SimpleNamespace

            kwargs["generation_governor"] = SimpleNamespace(generate=generate)
        original_init(self, *args, **kwargs)
        fresh_history_sizes.append(len(self.history))
        if not provider:
            self._governor.generate = generate

    def ask(message, save, mode="companion"):
        args = argparse.Namespace(
            prompt=[message], mode=mode, no_tools=True, no_save=not save
        )
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            status = cmd_ask(args)
        if generation_errors:
            raise RuntimeError(
                "Live inference failed; application fallback answers are not scored"
            ) from generation_errors[0]
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
        override(brain, "DRIFT_PRIMARY_MODEL", PRIMARY),
        override(brain, "DRIFT_CRITIC_MODEL", CRITIC),
        override(brain.DriftBrain, "__init__", observe_init),
        override(DriftMemory, "retrieve_context", observe_fallback),
        override(
            security_defense,
            "_security_logger",
            HardenedJsonlLogger(Path.cwd() / "state" / "security_audit.jsonl"),
        ),
    ):
        if phase == "seed":
            for label, message in SETUP:
                # A separate mode gives the distractor its own DMU category.
                mode = "quiet" if label == "distractor" else "companion"
                answer = ask(message, save=True, mode=mode)
                assert answer and live_calls
            # Seed structured state through its normal writer, independently of recall.
            being.state.focus = FOCUS
            body.state.heartbeat_rate = 93
            body._save_state()
            regulator.update_need("connection", 0.07, damping_factor=1)
            being.evolve(interaction_happened=True)
            return {
                "pid": os.getpid(),
                "setup_turns": len(SETUP),
                **({"live_calls": live_calls} if provider else {}),
            }

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
            label: record_id
            for label, message in SETUP
            for content, record_id in sqlite_records.items()
            if content.startswith(f"user: {message}\nBot: ")
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
        _, marker, recall_section = prompt.partition("<retrieved_memory_evidence>")
        assert marker
        recall_section = recall_section.partition("</retrieved_memory_evidence>")[0]
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
            "memory_context": [
                label
                for record_index, record_id in enumerate(ids, 1)
                for label, expected_id in stored_labels.items()
                if record_id == expected_id
                and f"(record {record_index})" in recall_section
            ],
            "focus_context": f"Current focus: {FOCUS}" in prompt,
            "heartbeat_context": "Heartbeat: 93" in prompt,
            "need_context": "connection: 7%" in prompt,
            "core_prompt_available": not system.startswith("ERROR: DRIFT_CORE_PROMPT"),
            "requested_generation_options": options,
            **(
                {"effective_local_settings": live_calls[0]["request"]["options"]}
                if provider
                else {}
            ),
            "model_boundary_calls": [PRIMARY, CRITIC],
            "prompt_characters": len(prompt) + len(system),
            "runtime_seconds": round(time.perf_counter() - started, 3),
            "history_at_start": fresh_history_sizes[0],
            "response": response,
            **(
                {
                    "live_calls": live_calls,
                    "system_prompt_source": str(source),
                    "system_prompt_policy": "explicit supplied prompt file; no fallback",
                    "critic_policy": "real inference using the same local model",
                    "seed_policy": "real inference for every setup turn",
                }
                if provider
                else {}
            ),
        }


def count_rows(path, query):
    if not path.is_file():
        return 0
    with contextlib.closing(
        sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True)
    ) as conn:
        return conn.execute(query).fetchone()[0]


def run_worker(root, phase, local_config=None):
    command = [sys.executable, str(Path(__file__).resolve()), "--worker", phase]
    if local_config:
        command += ["--local-config", str(local_config)]
    provider = local_config.get("provider") if local_config else None
    env = isolated_env(root, provider)
    if local_config:
        env["DRIFT_USE_OPENAI"] = "false"
    result = subprocess.run(
        command,
        cwd=root,
        check=False,
        env=env,
        capture_output=True,
        text=True,
        timeout=900 if local_config else 120,
    )
    if result.returncode:
        raise RuntimeError(result.stderr + result.stdout)
    return json.loads(result.stdout)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker", choices=("seed", "probe"), help=argparse.SUPPRESS)
    parser.add_argument("--score", type=Path, help="Score a raw JSON response offline")
    parser.add_argument(
        "--local-model",
        "--model",
        dest="local_model",
        help="Exact local tag or remote model ID",
    )
    parser.add_argument(
        "--provider", choices=("ollama", "llama-cpp", "gemini"), default="ollama"
    )
    parser.add_argument("--model-file", type=Path, help="GGUF file served by llama.cpp")
    parser.add_argument(
        "--system-prompt",
        type=Path,
        help="Explicit system prompt file; required for live inference",
    )
    parser.add_argument("--ollama-url", default="http://127.0.0.1:11434")
    parser.add_argument("--trials", type=int, default=1, choices=range(1, 21))
    parser.add_argument("--output", type=Path, help="New directory for live evidence")
    parser.add_argument(
        "--variant",
        choices=("current", "evidence-focused", "evidence-critic"),
        default="current",
        help="Controlled prompt/critic arm",
    )
    parser.add_argument(
        "--compare-variants",
        action="store_true",
        help="Run all three arms from one shared real setup per scenario",
    )
    parser.add_argument("--local-config", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.provider == "gemini" and not args.local_model:
        from local_continuity import DEFAULT_GEMINI_MODEL

        args.local_model = DEFAULT_GEMINI_MODEL
    if args.worker:
        config = None
        if args.local_config:
            config = json.loads(args.local_config.read_text(encoding="utf-8"))
            global SETUP, QUESTION, EXPECTED, FOCUS
            SETUP = config["scenario"]["setup"]
            QUESTION = config["scenario"]["question"]
            EXPECTED = config["scenario"]["expected"]
            FOCUS = config["scenario"]["focus"]
        expected = isolated_env(Path.cwd(), config.get("provider") if config else None)
        if config:
            expected["DRIFT_USE_OPENAI"] = "false"
        assert all(os.environ.get(key) == value for key, value in expected.items())
        # Python can add LC_CTYPE during locale coercion.
        assert not set(os.environ) - set(expected) - {"LC_CTYPE"}
        if config:
            from local_continuity import inference_guard

            with inference_guard(config["provider"], config["url"]):
                result = worker(args.worker, config)
        else:
            parser.error(
                "Workers require --local-config; no mocked generation is available"
            )
    elif args.score:
        result = score(args.score.read_text(encoding="utf-8"))
    elif args.local_model:
        if not args.output or not args.system_prompt:
            parser.error("--local-model requires --output and --system-prompt")
        if args.compare_variants:
            from local_continuity import evaluate_comparison

            result = evaluate_comparison(args, sys.modules[__name__])
        else:
            from local_continuity import evaluate_local

            result = evaluate_local(args, sys.modules[__name__])
    else:
        if (
            args.local_config
            or args.output
            or args.trials != 1
            or args.variant != "current"
            or args.compare_variants
        ):
            parser.error("Live options require --local-model")
        parser.error("Select --model for real inference, or --score for saved answers")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
