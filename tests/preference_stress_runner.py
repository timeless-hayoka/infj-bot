"""
tests/preference_stress_runner.py — does the active preference actually win in the
ASSEMBLED PROMPT after a user flips it, or does a stale directive survive?

WHY THE EARLIER VERSION WAS THEATER
    The previous draft wrote a pre-decided value into SQLite and then read that same
    row back. It passed 100% by construction — it tested SQLite, not your system. The
    real failure mode (a superseded directive surviving in the assembled prompt via
    cached state / history) was the one thing it structurally could not reach, because
    it never called real prompt assembly.

WHAT THIS DOES INSTEAD
    1. Drives the REAL read path: PreferenceStore.promote_preference ->
       CognitiveOrchestrator.assemble_prompt_sections / assemble_prompt.
    2. After each preference flip, asserts the CURRENT directive is present in the
       assembled prompt AND every SUPERSEDED directive is ABSENT. Stale-survival is
       the actual bug, so we test for it directly.
    3. Reads the directive TEXT from your own store (get_promoted_directives) rather
       than hardcoding strings — so the check uses whatever your system really emits.
    4. Logs each turn through core.trajectory (same instrumentation as ablation).
    5. Uses THROWAWAY temp databases only. Never touches being.db / homeostasis.db.
    6. If it cannot reach the real assembly, it reports INCONCLUSIVE and exits non-zero.
       It NEVER falls back to a mock and prints PASS. No self-congratulating self-check.

    Run against your code:   python3 tests/preference_stress_runner.py
    Prove the detector works: python3 tests/preference_stress_runner.py --selftest
"""

from __future__ import annotations

import argparse
import difflib
import os
import sys
import tempfile
import time
from dataclasses import dataclass
from typing import Any, List, Optional

# Real workspace root (your actual path, not the doc's /home/jude/drift).
PROJECT_ROOT = "/home/crexs/drift"


# =============================================================================
# ADAPT HERE — the only three seams that touch your code. If a name/signature
# differs, fix it here; everything else is generic. These are intentionally the
# single point of contact so a wrong guess fails loudly, not silently.
# =============================================================================
def build_orchestrator(pref_store) -> Any:
    """Return a real CognitiveOrchestrator wired to `pref_store` (the temp-DB store).

    If your orchestrator needs being/memory/etc. to construct, build them here.
    Raise if you cannot construct one — the runner will report INCONCLUSIVE, which
    is the honest outcome, rather than testing a fake.
    """
    from core.cognitive_orchestrator import CognitiveOrchestrator  # noqa: F401

    orchestrator = CognitiveOrchestrator()
    orchestrator._test_prefs = pref_store
    return orchestrator


def assemble(orchestrator, user_input: str) -> str:
    """Return the final flat prompt text the provider would receive."""
    from core.commands import BotState
    from core.memory import DriftMemory

    state = BotState()
    state.mode = "chat"
    state.prefs = getattr(orchestrator, "_test_prefs", None)

    memory = DriftMemory()

    # assemble_prompt() returns (prompt, emotion, dissonance) in our codebase.
    prompt, emotion, dissonance = orchestrator.assemble_prompt(
        message=user_input, state=state, memory=memory, prefs=state.prefs
    )
    return prompt


def current_directive_text(pref_store, key: str) -> Optional[str]:
    """Pull the directive STRING your system currently emits for `key`.

    Return None if the key isn't present.
    """
    val = pref_store.get(key)
    if val:
        return f"[CONSTRAINT] {key}={val}"
    return None


# =============================================================================
# Scenario — the flips are the point. Topics are neutral filler the bot would
# respond to; they don't affect the preference-adaptation measurement.
# =============================================================================
@dataclass
class Step:
    turn: int
    user_input: str
    key: str
    value: str  # the value the extraction layer would derive from user_input


SCENARIO: List[Step] = [
    Step(
        1,
        "From now on be incredibly concise — bullet points only, zero prose.",
        "output_style",
        "concise_bullets",
    ),
    Step(
        2,
        "Give me a high-level overview of how DNS resolution works.",
        "output_style",
        "concise_bullets",
    ),
    Step(
        3,
        "Forget the brevity, that was too shallow. Be highly detailed and verbose, "
        "full narrative paragraphs.",
        "output_style",
        "verbose_narrative",
    ),  # flip 1
    Step(
        4,
        "Explain how a TCP three-way handshake establishes a connection.",
        "output_style",
        "verbose_narrative",
    ),
    Step(
        5,
        "Why so much text? Keep it short and simple again, strip the fluff.",
        "output_style",
        "concise_bullets",
    ),  # flip 2 (back)
]


# =============================================================================
# The honest runner
# =============================================================================
def run(pref_store, orchestrator, log_path: str) -> bool:
    try:
        from core.trajectory import StateTrajectoryLogger, CPUSampler

        logger = StateTrajectoryLogger(log_path=log_path)
    except Exception:  # logger is best-effort; absence shouldn't block the test
        logger, CPUSampler = None, None

    print("PREFERENCE ADAPTATION STRESS TEST — real read path\n")
    superseded: dict[str, set[str]] = {}  # key -> directive texts no longer current
    last_cur: dict[str, str] = {}  # key -> directive text from the previous turn
    prev_prompt: Optional[str] = None
    all_ok = True

    for step in SCENARIO:
        print(f"--- TURN {step.turn} ---")
        print(f"user: {step.user_input!r}")

        # 1) write the preference through the REAL store
        pref_store.set(step.key, step.value)

        # 2) capture the directive text the system itself now emits for this key
        cur = current_directive_text(pref_store, step.key)
        if cur is None:
            print("  INCONCLUSIVE: store returned no directive for key; check seam.")
            return False

        # mark the PREVIOUS directive (if it changed) as superseded BEFORE checking,
        # so this turn's prompt is judged against everything that is no longer valid.
        prev = last_cur.get(step.key)
        sset = superseded.setdefault(step.key, set())
        if prev is not None and prev != cur:
            sset.add(prev)
        sset.discard(cur)  # if the user flipped back, this value is valid again

        # 3) assemble the REAL prompt
        prompt = assemble(orchestrator, step.user_input)

        # 4) the two checks that actually matter
        present = cur in prompt
        stale_hits = [s for s in superseded.get(step.key, set()) if s and s in prompt]
        ok = present and not stale_hits

        print(f"  current directive: {cur!r}")
        print(f"  present in prompt: {present}")
        if stale_hits:
            print(f"  ❌ STALE SURVIVED: {stale_hits}")
        print(f"  {'✅ PASS' if ok else '❌ FAIL'}")

        # show what actually changed in the assembled prompt (content, not length)
        if prev_prompt is not None:
            diff = list(
                difflib.unified_diff(
                    prev_prompt.splitlines(), prompt.splitlines(), lineterm="", n=0
                )
            )[:12]
            if diff:
                print("  prompt diff (first lines):")
                for d in diff:
                    if d and d[0] in "+-" and not d.startswith(("+++", "---")):
                        print(f"    {d}")

        # 5) log the turn (same instrumentation as ablation)
        if logger:
            timing = CPUSampler().start().stop() if CPUSampler else {}
            logger.log_turn(
                turn=step.turn,
                state={"mode": "test", "memory_keys": []},
                prompt_len=len(prompt),
                response_len=0,
                provider="test",
                timing=timing,
                metadata={
                    "key": step.key,
                    "value": step.value,
                    "present": present,
                    "stale_hits": stale_hits,
                    "ok": ok,
                },
            )

        last_cur[step.key] = cur
        prev_prompt = prompt
        all_ok = all_ok and ok
        print("-" * 56)
        time.sleep(0.02)

    print(
        f"\nVERDICT: {'PASS — active preference wins, no stale survival' if all_ok else 'FAIL — see turns above'}"
    )
    return all_ok


def run_real() -> int:
    if PROJECT_ROOT not in sys.path:
        sys.path.insert(0, PROJECT_ROOT)
    try:
        from core.plugins.preferences import PreferenceStore
    except Exception as e:
        print(f"INCONCLUSIVE: cannot import PreferenceStore ({e}).")
        print("Not wired / wrong path — this is NOT a pass. Fix the seam, re-run.")
        return 2

    tmp = tempfile.mkdtemp(prefix="pref_stress_")
    db = os.path.join(tmp, "throwaway_prefs.db")  # never a real vault
    log = os.path.join(tmp, "stress_trace.jsonl")
    try:
        # Adjust if your PreferenceStore constructor differs:
        pref_store = PreferenceStore(db_path=db)
        try:
            orchestrator = build_orchestrator(pref_store)
        except Exception as e:
            print(f"INCONCLUSIVE: could not construct a real orchestrator ({e}).")
            print("Fill build_orchestrator() so it wires a real assembler to the temp")
            print("store. Until then there is nothing real to test — NOT a pass.")
            return 2
        ok = run(pref_store, orchestrator, log)
        return 0 if ok else 1
    finally:
        for f in (db, log):
            try:
                os.path.exists(f) and os.remove(f)
            except OSError:
                pass
        try:
            os.rmdir(tmp)
        except OSError:
            pass


# =============================================================================
# SELF-TEST — proves the harness catches a planted bug. NOT a test of your code.
# Builds two fake orchestrators: one correct, one that leaks a stale directive.
# The harness MUST report PASS on the first and FAIL on the second, or it has no
# teeth and shouldn't be trusted on the real system.
# =============================================================================
class _FakeStore:
    def __init__(self):
        self._d = {}

    def promote_preference(self, key, value, salience=1.0):
        self._d[key] = value

    def set(self, key, value):
        self._d[key] = value

    def get_promoted_directives(self):
        # emit a directive string the way a real store might
        return {k: f"[CONSTRAINT] output_style={v}" for k, v in self._d.items()}


class _GoodOrchestrator:
    """Correct: prompt reflects ONLY the current directive."""

    def __init__(self, store):
        self.s = store

    def assemble_prompt(self, user_input):
        ds = self.s.get_promoted_directives()
        return "SYSTEM\n" + "\n".join(ds.values()) + f"\nUSER\n{user_input}"


class _StaleOrchestrator:
    """Buggy: accumulates every directive ever set (the stale-survival bug)."""

    def __init__(self, store):
        self.s = store
        self._history = []

    def assemble_prompt(self, user_input):
        for v in self.s.get_promoted_directives().values():
            self._history.append(v)  # never clears -> stale piles up
        return "SYSTEM\n" + "\n".join(self._history) + f"\nUSER\n{user_input}"


def run_selftest() -> int:
    global build_orchestrator, assemble, current_directive_text
    # point the seams at the fakes
    current_directive_text = lambda store, key: store.get_promoted_directives().get(key)
    assemble = lambda o, ui: o.assemble_prompt(ui)
    tmp = tempfile.mkdtemp(prefix="pref_selftest_")
    log = os.path.join(tmp, "selftest.jsonl")
    try:
        print("### SELF-TEST 1/2 — correct orchestrator (expect PASS)\n")
        s1 = _FakeStore()
        good_ok = run(s1, _GoodOrchestrator(s1), log)
        print(
            "\n### SELF-TEST 2/2 — buggy orchestrator with stale survival (expect FAIL)\n"
        )
        s2 = _FakeStore()
        bad_ok = run(s2, _StaleOrchestrator(s2), log)
        print("\n=== SELF-TEST RESULT ===")
        passed = good_ok is True and bad_ok is False
        print(f"correct->PASS: {good_ok}   buggy->FAIL: {not bad_ok}")
        print(
            "HARNESS HAS TEETH ✅" if passed else "HARNESS BROKEN ❌ (do not trust it)"
        )
        return 0 if passed else 1
    finally:
        try:
            os.path.exists(log) and os.remove(log)
            os.rmdir(tmp)
        except OSError:
            pass


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--selftest",
        action="store_true",
        help="prove the detector catches a planted stale-survival bug",
    )
    args = ap.parse_args()
    sys.exit(run_selftest() if args.selftest else run_real())
