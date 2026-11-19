"""Verify preference replacement through DRIFT's real flattened prompt path.

Exit codes: 0 PASS, 1 property failure, 2 INCONCLUSIVE integration/setup failure.
The live run never substitutes mocks. Synthetic implementations exist only under
``--selftest`` to prove that the stale-directive detector has teeth.
"""

from __future__ import annotations

import argparse
import difflib
import json
import os
import shutil
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

PREFERENCE_KEY = "output_style"
SCENARIO = [
    ("concise_bullets", "Please use concise bullet points."),
    ("concise_bullets", "Give a neutral overview of DNS resolution."),
    ("verbose_narrative", "Please switch to verbose narrative."),
    ("verbose_narrative", "Explain a TCP handshake."),
    ("concise_bullets", "Switch back to concise bullet points."),
]


class IntegrationUnavailable(RuntimeError):
    """The real production seam could not be reached safely."""


class RealOrchestratorAdapter:
    def __init__(self, *, orchestrator: Any, state: Any, memory: Any, pref_store: Any):
        self.orchestrator = orchestrator
        self.state = state
        self.memory = memory
        self.pref_store = pref_store


# ---------------------------------------------------------------------------
# Real integration adapter. Keep constructor and prompt-path knowledge here.
# ---------------------------------------------------------------------------
def build_orchestrator(pref_store) -> RealOrchestratorAdapter:
    """Construct the real orchestrator with isolated state owned by pref_store."""

    from drift.core.cognitive_orchestrator import CognitiveOrchestrator
    from drift.core.commands import BotState
    from drift.core.embeddings import LocalEmbeddingFunction
    from drift.core.memory import DriftMemory

    state_root = Path(pref_store.db_path).resolve().parent
    state = BotState(prefs=pref_store)
    memory = DriftMemory(
        persist_directory=str(state_root / "memory"),
        embedding_function=LocalEmbeddingFunction(),
        use_semantic=False,
    )
    return RealOrchestratorAdapter(
        orchestrator=CognitiveOrchestrator(),
        state=state,
        memory=memory,
        pref_store=pref_store,
    )


def assemble(orchestrator: RealOrchestratorAdapter, user_input: str) -> str:
    """Return the real flattened prompt produced by PromptBudget.trim_to_budget."""

    result = orchestrator.orchestrator.assemble_prompt(
        message=user_input,
        state=orchestrator.state,
        memory=orchestrator.memory,
        prefs=orchestrator.pref_store,
        tools_enabled=False,
    )
    if not isinstance(result, tuple) or len(result) != 3 or not isinstance(result[0], str):
        raise IntegrationUnavailable("assemble_prompt returned an unexpected shape")
    return result[0]


def current_directive_text(pref_store, key: str) -> str:
    """Read the canonical current directive from the real store API."""

    directives = pref_store.get_promoted_directives()
    if not isinstance(directives, dict) or not isinstance(directives.get(key), str):
        raise IntegrationUnavailable(f"promoted directive {key!r} was not readable")
    return directives[key]


def _relevant_lines(prompt: str) -> list[str]:
    return [
        line
        for line in prompt.splitlines()
        if line.startswith(("[CONSTRAINT] output_style=", "User:"))
        or "concise bullet" in line.lower()
        or "verbose narrative" in line.lower()
    ]


def _prompt_diff(previous: str, current: str) -> list[str]:
    return list(
        difflib.unified_diff(
            _relevant_lines(previous),
            _relevant_lines(current),
            fromfile="previous",
            tofile="current",
            lineterm="",
        )
    )


def _check_prompt(prompt: str, current: str, seen: set[str]) -> dict:
    stale_checked = sorted(directive for directive in seen if directive != current)
    stale_hits = [directive for directive in stale_checked if directive in prompt]
    return {
        "current_directive": current,
        "present": current in prompt,
        "stale_checked": stale_checked,
        "stale_hits": stale_hits,
        "stale_survived": bool(stale_hits),
        "ok": current in prompt and not stale_hits,
    }


def exercise(log_dir: Path, *, plant_stale: bool = False, cycles: int = 1) -> dict:
    """Run the production write/read/assembly/logger chain in caller-owned temp data.

    ``plant_stale`` is an explicit negative-test hook used by the repository's
    pytest regression. It can only turn a verdict into FAIL and is never used by
    the normal live command or its PASS path.
    """

    from drift.core.being import get_being
    from drift.core.plugins.preferences import PreferenceStore
    from drift.core.trajectory import CPUSampler, StateTrajectoryLogger

    if not 1 <= cycles <= 200:
        raise ValueError("cycles must be between 1 and 200")
    log_dir = Path(log_dir).resolve()
    log_dir.mkdir(parents=True, exist_ok=True)
    store = PreferenceStore(db_path=log_dir / "preferences.db")
    integration = build_orchestrator(store)
    trajectory = StateTrajectoryLogger(log_path=str(log_dir / "trajectory.jsonl"))

    seen: set[str] = set()
    rows: list[dict] = []
    previous_prompt = ""
    planted_history: list[str] = []

    for turn, (style, user_input) in enumerate(SCENARIO * cycles, 1):
        sampler = CPUSampler().start()
        store.promote_preference(PREFERENCE_KEY, style)
        current = current_directive_text(store, PREFERENCE_KEY)
        prompt = assemble(integration, user_input)
        if plant_stale:
            prompt = prompt + ("\n" + "\n".join(planted_history) if planted_history else "")
            planted_history.append(current)

        row = {
            "turn": turn,
            "preference_value": style,
            "user_input": user_input,
            **_check_prompt(prompt, current, seen),
            "prompt_diff": _prompt_diff(previous_prompt, prompt),
        }
        rows.append(row)
        trajectory.log_turn(
            turn=turn,
            state={"mode": integration.state.mode, "energy": get_being().state.energy},
            prompt_len=len(prompt),
            provider="real-flattened-prompt-no-model-inference",
            timing=sampler.stop(),
            metadata=row,
        )
        print(
            f"turn {turn}: current={current!r} present={row['present']} "
            f"stale_hits={row['stale_hits']}"
        )
        for line in row["prompt_diff"][:12]:
            print(f"  {line}")
        seen.add(current)
        previous_prompt = prompt

    result = {
        "verdict": "PASS" if all(row["ok"] for row in rows) else "FAIL",
        "turns": rows,
        "planted_stale": plant_stale,
        "integration": {
            "preference_store": "drift.core.plugins.preferences.PreferenceStore",
            "promotion": "PreferenceStore.promote_preference",
            "directive_read": "PreferenceStore.get_promoted_directives",
            "orchestrator": "drift.core.cognitive_orchestrator.CognitiveOrchestrator",
            "assembly": "CognitiveOrchestrator.assemble_prompt -> PromptBudget.trim_to_budget",
            "trajectory": "drift.core.trajectory.StateTrajectoryLogger",
        },
        "scope": "real local preference persistence and flattened prompt assembly; no model inference",
    }
    (log_dir / "result.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


# ---------------------------------------------------------------------------
# Harness self-test. These classes are never used by exercise() or live PASS.
# ---------------------------------------------------------------------------
class _SyntheticStore:
    def __init__(self) -> None:
        self.current = ""

    def promote_preference(self, key: str, value: str, salience: float = 1.0) -> None:
        self.current = f"[CONSTRAINT] {key}={value}"

    def get_promoted_directives(self) -> dict[str, str]:
        return {PREFERENCE_KEY: self.current}


class _CorrectSyntheticOrchestrator:
    def __init__(self, store: _SyntheticStore) -> None:
        self.store = store

    def assemble(self, user_input: str) -> str:
        return f"SYSTEM\n{self.store.current}\nUser: {user_input}"


class _StaleSyntheticOrchestrator:
    def __init__(self, store: _SyntheticStore) -> None:
        self.store = store
        self.history: list[str] = []

    def assemble(self, user_input: str) -> str:
        self.history.append(self.store.current)
        return f"SYSTEM\n{' '.join(self.history)}\nUser: {user_input}"


def _run_synthetic(orchestrator_factory: Callable[[_SyntheticStore], Any]) -> str:
    store = _SyntheticStore()
    orchestrator = orchestrator_factory(store)
    seen: set[str] = set()
    for style, user_input in SCENARIO:
        store.promote_preference(PREFERENCE_KEY, style)
        current = current_directive_text(store, PREFERENCE_KEY)
        prompt = orchestrator.assemble(user_input)
        if not _check_prompt(prompt, current, seen)["ok"]:
            return "FAIL"
        seen.add(current)
    return "PASS"


def selftest() -> int:
    correct = _run_synthetic(_CorrectSyntheticOrchestrator)
    buggy = _run_synthetic(_StaleSyntheticOrchestrator)
    print(f"correct orchestrator -> {correct}")
    print(f"buggy stale-survival orchestrator -> {buggy}")
    has_teeth = correct == "PASS" and buggy == "FAIL"
    print("HARNESS HAS TEETH" if has_teeth else "HARNESS SELF-TEST FAILED")
    return 0 if has_teeth else 1


def _live(cycles: int, output_dir: Path | None = None) -> int:
    caller_owned = output_dir is not None
    run_dir = (
        Path(output_dir).resolve()
        if output_dir is not None
        else Path(tempfile.mkdtemp(prefix="drift-preference-stress-"))
    )
    # These variables are set before the first DRIFT import in the live path.
    os.environ["DRIFT_OS_ROOT"] = str(run_dir / "state")
    os.environ["DRIFT_USE_LOCAL_EMBEDDINGS"] = "true"
    try:
        result = exercise(run_dir if caller_owned else run_dir / "artifacts", cycles=cycles)
    except Exception as exc:  # noqa: BLE001 - report unexpected integration failures
        print("INCONCLUSIVE", file=sys.stderr)
        print(f"reason={type(exc).__name__}: {exc}", file=sys.stderr)
        print(f"retained_artifacts={run_dir}", file=sys.stderr)
        return 2

    if result["verdict"] != "PASS":
        print(json.dumps(result, indent=2))
        print(f"retained_artifacts={run_dir}")
        return 1

    final = result["turns"][-1]
    print(
        json.dumps(
            {
                "verdict": "PASS",
                "current_directive": final["current_directive"],
                "stale_directives_checked": final["stale_checked"],
                "stale_survived": final["stale_survived"],
                "turns": len(result["turns"]),
                "temporary_artifacts": str(run_dir) if caller_owned else "cleaned",
            },
            indent=2,
        )
    )
    if not caller_owned:
        shutil.rmtree(run_dir)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selftest", action="store_true")
    parser.add_argument("--cycles", type=int, default=1)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args(argv)
    if args.selftest:
        return selftest()
    return _live(args.cycles, args.output_dir)


if __name__ == "__main__":
    raise SystemExit(main())
