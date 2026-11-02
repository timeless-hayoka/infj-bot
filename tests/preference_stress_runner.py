"""Exercise the real preference write → read → final prompt path in temp state.

Exit codes: 0 PASS, 1 a detected violation, 2 INCONCLUSIVE (setup/execution failed).
--selftest mutates a real orchestrator instance to leak an old directive; no mocks
or substitute prompt assembler are used. --plant-stale exposes the negative run.
"""

from __future__ import annotations

import argparse
import difflib
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
SCENARIO = [
    "concise_bullets",
    "concise_bullets",
    "verbose_narrative",
    "verbose_narrative",
    "concise_bullets",
]


def exercise(log_dir: Path, *, plant_stale: bool = False, cycles: int = 1) -> dict:
    # The CLI sets isolation before any app import; pytest's conftest does likewise.
    from drift.core.being import get_being
    from drift.core.cognitive_orchestrator import CognitiveOrchestrator
    from drift.core.commands import BotState
    from drift.core.embeddings import LocalEmbeddingFunction
    from drift.core.memory import DriftMemory
    from drift.core.plugins.preferences import PreferenceStore
    from drift.core.trajectory import CPUSampler, StateTrajectoryLogger

    if not 1 <= cycles <= 200:
        raise ValueError("cycles must be between 1 and 200")
    log_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="drift-preference-db-") as tmp:
        store = PreferenceStore(db_path=Path(tmp) / "preferences.db")
        state = BotState(prefs=store)
        memory = DriftMemory(
            persist_directory=str(Path(tmp) / "memory"),
            embedding_function=LocalEmbeddingFunction(),
            use_semantic=False,
        )
        orchestrator = CognitiveOrchestrator()
        original_assemble = orchestrator.assemble_prompt
        previous = []
        if plant_stale:
            # Fault injection wraps the real result rather than replacing assembly.
            def stale_assemble(**kwargs):
                prompt, emotion, dissonance = original_assemble(**kwargs)
                current = store.get_promoted_directives()["output_style"]
                prompt += "\n" + "\n".join(previous)
                previous.append(current)
                return prompt, emotion, dissonance

            orchestrator.assemble_prompt = stale_assemble
        logger = StateTrajectoryLogger(log_path=str(log_dir / "trajectory.jsonl"))
        seen, rows, last_prompt = set(), [], ""
        for turn, value in enumerate(SCENARIO * cycles, 1):
            sampler = CPUSampler().start()
            store.promote_preference("output_style", value)
            current = store.get_promoted_directives()["output_style"]
            # Neutral input ensures stale hits cannot come from quoted user text.
            prompt, _, _ = orchestrator.assemble_prompt(
                message="Explain DNS resolution.",
                state=state,
                memory=memory,
                prefs=store,
                tools_enabled=False,
            )
            stale = sorted(d for d in seen if d != current and d in prompt)
            row = {
                "turn": turn,
                "current_directive": current,
                "present": current in prompt,
                "stale_hits": stale,
                "ok": current in prompt and not stale,
                "prompt_diff": list(
                    difflib.unified_diff(
                        last_prompt.splitlines(), prompt.splitlines(), lineterm=""
                    )
                ),
            }
            rows.append(row)
            logger.log_turn(
                turn=turn,
                state={"mode": state.mode, "energy": get_being().state.energy},
                prompt_len=len(prompt),
                provider="real-prompt-assembly-no-inference",
                timing=sampler.stop(),
                metadata=row,
            )
            seen.add(current)
            last_prompt = prompt
        result = {
            "verdict": "PASS" if all(r["ok"] for r in rows) else "FAIL",
            "planted_stale": plant_stale,
            "turns": rows,
            "scope": "real local persistence and prompt assembly; no model inference",
        }
        (log_dir / "result.json").write_text(json.dumps(result, indent=2) + "\n")
        return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selftest", action="store_true")
    parser.add_argument("--plant-stale", action="store_true")
    parser.add_argument(
        "--output-dir", type=Path, default=Path("logs/preference-stress")
    )
    parser.add_argument(
        "--cycles",
        type=int,
        default=20,
        help="five-turn sequences (default: 20 = 100 turns)",
    )
    args = parser.parse_args(argv)
    # Dedicated process state prevents mutation of a production preference/being DB.
    with tempfile.TemporaryDirectory(prefix="drift-preference-state-") as state_root:
        os.environ["DRIFT_OS_ROOT"] = state_root
        os.environ["DRIFT_USE_LOCAL_EMBEDDINGS"] = "true"
        try:
            if args.selftest:
                good = exercise(args.output_dir / "correct", cycles=args.cycles)
                bad = exercise(
                    args.output_dir / "planted-stale",
                    plant_stale=True,
                    cycles=args.cycles,
                )
                ok = good["verdict"] == "PASS" and bad["verdict"] == "FAIL"
                print(
                    json.dumps(
                        {
                            "correct": good["verdict"],
                            "planted_stale": bad["verdict"],
                            "detector_verified": ok,
                        }
                    )
                )
                return 0 if ok else 1
            result = exercise(
                args.output_dir, plant_stale=args.plant_stale, cycles=args.cycles
            )
            print(json.dumps(result, indent=2))
            return 0 if result["verdict"] == "PASS" else 1
        except Exception as exc:  # noqa: BLE001 - report setup failures as INCONCLUSIVE
            result = {
                "verdict": "INCONCLUSIVE",
                "error": f"{type(exc).__name__}: {exc}",
            }
            try:
                args.output_dir.mkdir(parents=True, exist_ok=True)
                (args.output_dir / "error.json").write_text(
                    json.dumps(result, indent=2) + "\n"
                )
            except OSError:
                pass
            print(json.dumps(result), file=sys.stderr)
            return 2


if __name__ == "__main__":
    raise SystemExit(main())
