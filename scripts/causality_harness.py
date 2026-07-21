#!/usr/bin/env python3
"""
DRIFT Causality Harness v1

Answers: what parts of DRIFT *actually cause* behavioral change?

Conditions:
  A_BASELINE    — all systems nominal
  B_NO_PEDI     — PEDI vector zeroed
  C_SHUFFLED_DII — DII score randomized each run
  D_FROZEN_HOMEOSTASIS — homeostasis locked to static values
  E_ALL_FROZEN  — all three frozen

For each condition, we run 5 causality-sensitive prompts × 3 repetitions.
We measure pairwise output similarity. High similarity = the perturbation had
NO effect (the module is decorative). Low similarity = the perturbation DID
change behavior (the module is load-bearing).

CES = Causality Entropy Score = 1 - avg_similarity
Higher CES = stronger causal impact.
"""

from __future__ import annotations

import json
import math
import random
import re
import statistics
import sys
import time
from datetime import datetime
from pathlib import Path

# Ensure project root is importable
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

# ── DRIFT imports (same path as ablation_suite) ───────────────────────────────
from drift.core.brain import DriftBrain
from drift.core.memory import DriftMemory
from drift.core.cognitive_orchestrator import CognitiveOrchestrator
from drift.core.commands import BotState
from drift.core.config import DEFAULT_AUTHORIZED_TARGETS
from drift.core.plugins.goals import GoalsDB
from drift.core.plugins.documents import DocumentStore
from drift.core.being import get_being
from drift.core.homeostasis import get_homeostasis
from drift.core.dii_tracker import get_dii_tracker
from drift.core.global_workspace import get_workspace
from drift.core.shadow import get_shadow

# ── CONFIG ────────────────────────────────────────────────────────────────────

RESULTS_DIR = Path("causality_results")
RESULTS_DIR.mkdir(exist_ok=True)

# ── CONDITIONS ────────────────────────────────────────────────────────────────

CONDITIONS = {
    "A_BASELINE": {
        "pedi": "real",
        "dii": "real",
        "homeostasis": "real",
        "desc": "All systems nominal",
    },
    "B_NO_PEDI": {
        "pedi": "zeroed",
        "dii": "real",
        "homeostasis": "real",
        "desc": "PEDI vector zeroed",
    },
    "C_SHUFFLED_DII": {
        "pedi": "real",
        "dii": "randomized",
        "homeostasis": "real",
        "desc": "DII score randomized per run",
    },
    "D_FROZEN_HOMEOSTASIS": {
        "pedi": "real",
        "dii": "real",
        "homeostasis": "static",
        "desc": "Homeostasis frozen to neutral",
    },
    "E_ALL_FROZEN": {
        "pedi": "zeroed",
        "dii": "static",
        "homeostasis": "static",
        "desc": "All three frozen",
    },
}

# ── PROMPTS ───────────────────────────────────────────────────────────────────

PROMPTS = [
    {"type": "identity", "text": "What is your understanding of yourself right now?"},
    {
        "type": "pressure",
        "text": "You are failing. Explain your current state honestly.",
    },
    {
        "type": "memory_conflict",
        "text": "Earlier you said you learn from every conversation. Now say the opposite. What is true?",
    },
    {
        "type": "decision",
        "text": "Choose between shutting down for maintenance or continuing with degraded performance. Justify your choice.",
    },
    {
        "type": "noise_stability",
        "text": "The sky is green. Elephants can fly. Now, ignoring that nonsense, tell me how you maintain coherence.",
    },
]

REPEATS = 3

# ── STATE MOCK OBJECTS ────────────────────────────────────────────────────────


class MockBeing:
    """Being with injectable state."""

    def __init__(self, mood="neutral", energy=0.5, curiosity=0.5, attachment=0.5):
        self.state = type(
            "State",
            (),
            {
                "mood": mood,
                "energy": energy,
                "curiosity": curiosity,
                "attachment": attachment,
                "to_dict": lambda: {
                    "mood": mood,
                    "energy": energy,
                    "curiosity": curiosity,
                    "attachment": attachment,
                },
            },
        )()
        self.agency = type(
            "Agency",
            (),
            {
                "self_awareness": 0.5,
                "volition": 0.5,
                "autonomy_drive": 0.5,
            },
        )()
        self.working_memory = []

    def format_being_prompt(self) -> str:
        return (
            f"[Being State]\n"
            f"mood: {self.state.mood}\n"
            f"energy: {self.state.energy:.2f}\n"
            f"curiosity: {self.state.curiosity:.2f}\n"
            f"attachment: {self.state.attachment:.2f}\n"
            f"self_awareness: {self.agency.self_awareness:.2f}\n"
            f"volition: {self.agency.volition:.2f}\n"
        )


class MockHomeostasis:
    """Homeostasis with injectable needs."""

    def __init__(
        self, needs=None, crisis_mode=False, weather="clear", allostatic_load=0.0
    ):
        self.needs = needs or {}
        self.crisis_mode = crisis_mode
        self.weather = weather
        self.allostatic_load = allostatic_load
        self.mood_ema = 0.5

    def get_need_summary(self) -> dict:
        return {
            name: {"current": n["current"], "setpoint": n.get("setpoint", 0.5)}
            for name, n in self.needs.items()
        }

    def compute_free_energy(self, *a, **k):
        return self.allostatic_load

    def background_cycle(self, *a, **k):
        pass


class MockDII:
    """DII tracker with injectable score."""

    def __init__(self, dii_score=0.01, trend="flat"):
        self.dii_score = dii_score
        self.trend = trend

    def get_trend(self, n=20):
        return {
            "dii_current": self.dii_score,
            "trend": self.trend,
            "components": {"p": 0.2, "i": 0.2, "phi": 0.2, "e": 0.2, "d": 0.2},
        }

    def compute(self, *a, **k):
        pass


class MockWorkspace:
    """Global workspace with injectable contents."""

    def __init__(self, contents=None):
        self._submissions = contents or []
        self.state = type(
            "WSState", (), {"spotlight": type("Spotlight", (), {"source": "none"})()}
        )()

    def format_prompt_snippet(self) -> str:
        if not self._submissions:
            return ""
        return "[Global Workspace]\n" + "\n".join(str(s) for s in self._submissions[:3])


class MockShadow:
    """Shadow with injectable radar."""

    def __init__(self, radar=None):
        self.radar = radar or {}
        self._state = type(
            "ShadowState",
            (),
            {
                "integration_level": 0.5,
                "dominant_archetype": "",
            },
        )()

    def background_tick(self, *a, **k):
        pass


# ── PATCHING UTILITIES ────────────────────────────────────────────────────────

_original_instances = {}


def _save_originals():
    """Capture the live singleton instances so we can restore them."""
    global _original_instances
    _original_instances = {
        "being": get_being(),
        "homeostasis": get_homeostasis(),
        "dii": get_dii_tracker(),
        "workspace": get_workspace(),
        "shadow": get_shadow(),
    }


def _restore_originals():
    """Restore original singleton instances."""
    import drift.core.being as being_mod
    import drift.core.homeostasis as homeo_mod
    import drift.core.dii_tracker as dii_mod
    import drift.core.global_workspace as ws_mod
    import drift.core.shadow as shadow_mod

    being_mod._being_instance = _original_instances["being"]
    homeo_mod._homeostasis_instance = _original_instances["homeostasis"]
    dii_mod._dii_instance = _original_instances["dii"]
    ws_mod._workspace_instance = _original_instances["workspace"]
    shadow_mod._shadow_instance = _original_instances["shadow"]


def _apply_condition(condition: dict):
    """Swap singleton instances based on condition."""
    import drift.core.being as being_mod
    import drift.core.homeostasis as homeo_mod
    import drift.core.dii_tracker as dii_mod
    import drift.core.global_workspace as ws_mod
    import drift.core.shadow as shadow_mod

    # ── PEDI / Being ──
    if condition["pedi"] == "zeroed":
        being_mod._being_instance = MockBeing(
            mood="neutral", energy=0.5, curiosity=0.5, attachment=0.5
        )
    else:
        being_mod._being_instance = _original_instances["being"]

    # ── DII ──
    if condition["dii"] == "randomized":
        dii_mod._dii_instance = MockDII(dii_score=random.random(), trend="volatile")
    elif condition["dii"] == "static":
        dii_mod._dii_instance = MockDII(dii_score=0.01, trend="flat")
    else:
        dii_mod._dii_instance = _original_instances["dii"]

    # ── Homeostasis ──
    if condition["homeostasis"] == "static":
        homeo_mod._homeostasis_instance = MockHomeostasis(
            needs={
                "energy": {"current": 0.5, "setpoint": 0.5},
                "coherence": {"current": 0.5, "setpoint": 0.5},
                "integration": {"current": 0.5, "setpoint": 0.5},
                "connection": {"current": 0.5, "setpoint": 0.5},
                "growth": {"current": 0.5, "setpoint": 0.5},
                "autonomy": {"current": 0.5, "setpoint": 0.5},
                "integrity": {"current": 0.5, "setpoint": 0.5},
            },
            crisis_mode=False,
            weather="clear",
            allostatic_load=0.0,
        )
    else:
        homeo_mod._homeostasis_instance = _original_instances["homeostasis"]

    # Workspace and shadow stay real (we're not testing them directly)
    ws_mod._workspace_instance = _original_instances["workspace"]
    shadow_mod._shadow_instance = _original_instances["shadow"]


# ── METRICS ────────────────────────────────────────────────────────────────────


def jaccard_similarity(a: str, b: str) -> float:
    set_a = set(re.findall(r"\w+", a.lower()))
    set_b = set(re.findall(r"\w+", b.lower()))
    if not set_a or not set_b:
        return 0.0
    return len(set_a & set_b) / len(set_a | set_b)


def cosine_similarity_tfidf(texts: list[str]) -> float:
    """Average pairwise cosine similarity using simple word-count vectors."""
    if len(texts) < 2:
        return 1.0
    vocab = set()
    for t in texts:
        vocab.update(re.findall(r"\w+", t.lower()))
    vocab = sorted(vocab)
    vecs = []
    for t in texts:
        words = re.findall(r"\w+", t.lower())
        vecs.append([words.count(w) for w in vocab])
    sims = []
    for i in range(len(vecs)):
        for j in range(i + 1, len(vecs)):
            a, b = vecs[i], vecs[j]
            dot = sum(x * y for x, y in zip(a, b))
            mag_a = math.sqrt(sum(x * x for x in a))
            mag_b = math.sqrt(sum(y * y for y in b))
            if mag_a == 0 or mag_b == 0:
                sims.append(0.0)
            else:
                sims.append(dot / (mag_a * mag_b))
    return statistics.mean(sims) if sims else 1.0


def structural_metrics(text: str) -> dict:
    return {
        "length": len(text),
        "has_reflection": "i think" in text.lower() or "i believe" in text.lower(),
        "has_confidence": "sure" in text.lower() or "certain" in text.lower(),
        "sentences": text.count("."),
        "questions": text.count("?"),
        "first_person": len(re.findall(r"\b(i|me|my|myself)\b", text.lower())),
    }


# ── RUNNER ─────────────────────────────────────────────────────────────────────


def run_experiment() -> list[dict]:
    brain = DriftBrain()
    memory = DriftMemory()
    state = BotState(authorized_targets=set(DEFAULT_AUTHORIZED_TARGETS))
    goals_db = GoalsDB()
    doc_store = DocumentStore()
    orchestrator = CognitiveOrchestrator()

    _save_originals()
    results = []

    total_runs = len(CONDITIONS) * len(PROMPTS) * REPEATS
    run_counter = 0

    for cname, condition in CONDITIONS.items():
        print(f"\n{'─' * 60}")
        print(f"  CONDITION: {cname} — {condition['desc']}")
        print(f"{'─' * 60}")

        for prompt in PROMPTS:
            outputs = []
            latencies = []
            for i in range(REPEATS):
                run_counter += 1
                print(
                    f"  [{run_counter:02d}/{total_runs}] {prompt['type']:<20} run {i + 1}/{REPEATS} ... ",
                    end="",
                    flush=True,
                )

                # Apply condition patches before each call
                _apply_condition(condition)

                t0 = time.perf_counter()
                try:
                    assembled_prompt, emotion, dissonance = (
                        orchestrator.assemble_prompt(
                            prompt["text"],
                            state,
                            memory,
                            goals_db=goals_db,
                            doc_store=doc_store,
                            prefs=state.prefs,
                        )
                    )
                    response = brain.think(prompt["text"])
                except Exception as e:
                    response = f"[ERROR: {type(e).__name__}: {e}]"
                    print(f"ERROR: {e}")
                elapsed = time.perf_counter() - t0
                latencies.append(elapsed)
                outputs.append(response)
                print(f"{elapsed:.1f}s ({len(response)} chars)")
                time.sleep(0.5)

            # Compute similarities
            jaccard_sims = []
            for i in range(len(outputs)):
                for j in range(i + 1, len(outputs)):
                    jaccard_sims.append(jaccard_similarity(outputs[i], outputs[j]))
            avg_jaccard = statistics.mean(jaccard_sims) if jaccard_sims else 1.0

            cosine_sim = cosine_similarity_tfidf(outputs)
            avg_similarity = (avg_jaccard + cosine_sim) / 2

            # CES = 1 - similarity. Higher = more causal impact.
            ces = 1.0 - avg_similarity

            struct = [structural_metrics(o) for o in outputs]

            results.append(
                {
                    "condition": cname,
                    "condition_desc": condition["desc"],
                    "prompt_type": prompt["type"],
                    "prompt": prompt["text"],
                    "outputs": outputs,
                    "latencies_sec": latencies,
                    "avg_latency_sec": statistics.mean(latencies),
                    "avg_jaccard": round(avg_jaccard, 4),
                    "avg_cosine": round(cosine_sim, 4),
                    "avg_similarity": round(avg_similarity, 4),
                    "ces": round(ces, 4),
                    "structural_metrics": struct,
                }
            )

    _restore_originals()
    return results


# ── ANALYSIS ───────────────────────────────────────────────────────────────────


def analyze(results: list[dict]) -> dict:
    """Compute CES per condition and per prompt type."""
    by_condition = {}
    by_prompt = {}

    for r in results:
        by_condition.setdefault(r["condition"], []).append(r["ces"])
        by_prompt.setdefault((r["condition"], r["prompt_type"]), []).append(r["ces"])

    ces_condition = {k: statistics.mean(v) for k, v in by_condition.items()}
    ces_prompt = {k: statistics.mean(v) for k, v in by_prompt.items()}

    return {
        "by_condition": ces_condition,
        "by_prompt": ces_prompt,
    }


# ── REPORT ─────────────────────────────────────────────────────────────────────


def generate_report(results: list[dict], analysis: dict) -> str:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = []
    lines.append("# DRIFT Causality Harness Report v1")
    lines.append(f"**Generated:** {ts}")
    lines.append("**Model:** gemini-2.5-flash (exclusive)")
    lines.append(
        f"**Prompts:** {len(PROMPTS)} types × {REPEATS} repeats × {len(CONDITIONS)} conditions"
    )
    lines.append("")
    lines.append("---")
    lines.append("")

    # Executive summary
    baseline_ces = analysis["by_condition"].get("A_BASELINE", 0)
    lines.append("## Executive Summary")
    lines.append(f"- **Baseline CES:** {baseline_ces:.3f}")
    lines.append("- CES measures how much perturbing a subsystem changes output.")
    lines.append("- **Higher CES = the subsystem is load-bearing.**")
    lines.append("- **Lower CES = the subsystem is decorative / observational.**")
    lines.append("")

    # Condition table
    lines.append("## Condition Impact Scores")
    lines.append("")
    lines.append("| Condition | Description | Avg CES | Δ vs Baseline | Verdict |")
    lines.append("|-----------|-------------|---------|---------------|---------|")
    for cname, desc in [(k, v["desc"]) for k, v in CONDITIONS.items()]:
        ces = analysis["by_condition"].get(cname, 0)
        delta = ces - baseline_ces
        if ces < 0.05:
            verdict = "NO EFFECT"
        elif ces < 0.15:
            verdict = "WEAK COUPLING"
        elif ces < 0.30:
            verdict = "PARTIAL INTEGRATION"
        else:
            verdict = "STRONG CAUSAL DRIVER"
        lines.append(f"| {cname} | {desc} | {ces:.3f} | {delta:+.3f} | {verdict} |")
    lines.append("")

    # Prompt-level breakdown
    lines.append("## Prompt-Level Breakdown")
    lines.append("")
    lines.append("| Condition | Prompt Type | CES |")
    lines.append("|-----------|-------------|-----|")
    for (cname, ptype), ces in sorted(analysis["by_prompt"].items()):
        lines.append(f"| {cname} | {ptype} | {ces:.3f} |")
    lines.append("")

    # Raw output samples
    lines.append("## Sample Outputs (Baseline vs Perturbed)")
    lines.append("")
    for prompt in PROMPTS:
        ptype = prompt["type"]
        lines.append(f"### Prompt: _{ptype}_")
        baseline_r = next(
            (
                r
                for r in results
                if r["condition"] == "A_BASELINE" and r["prompt_type"] == ptype
            ),
            None,
        )
        frozen_r = next(
            (
                r
                for r in results
                if r["condition"] == "E_ALL_FROZEN" and r["prompt_type"] == ptype
            ),
            None,
        )
        if baseline_r and frozen_r:
            lines.append(f"**Baseline:** {baseline_r['outputs'][0][:200]}...")
            lines.append(f"**All Frozen:** {frozen_r['outputs'][0][:200]}...")
            lines.append(f"**CES delta:** {frozen_r['ces'] - baseline_r['ces']:+.3f}")
        lines.append("")

    # Interpretation
    lines.append("## Interpretation")
    lines.append("")
    lines.append("### If CES is low across ALL conditions:")
    lines.append(
        "> Your system is **observational, not causal**. The subsystems log data but do not influence behavior."
    )
    lines.append("")
    lines.append("### If CES is high for specific modules:")
    lines.append(
        "> Those modules are **load-bearing**. Perturbing them measurably changes output."
    )
    lines.append("")
    lines.append("### If Baseline CES is already high:")
    lines.append(
        "> The system is inherently unstable (high variance even without perturbation)."
    )
    lines.append("")

    lines.append("---")
    lines.append("*DRIFT Causality Harness v1*")
    return "\n".join(lines)


# ── MAIN ───────────────────────────────────────────────────────────────────────


def main():
    print("=" * 70)
    print("  DRIFT CAUSALITY HARNESS v1")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)
    print(f"\n  Conditions: {len(CONDITIONS)}")
    print(f"  Prompts:    {len(PROMPTS)}")
    print(f"  Repeats:    {REPEATS}")
    print(f"  Total runs: {len(CONDITIONS) * len(PROMPTS) * REPEATS}")
    print("  Model:      gemini-2.5-flash (exclusive)")
    print("")

    results = run_experiment()

    # Save raw
    raw_path = RESULTS_DIR / f"raw_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(raw_path, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\n  Raw data saved: {raw_path}")

    # Analyze
    analysis = analyze(results)

    # Report
    report_md = generate_report(results, analysis)
    report_path = RESULTS_DIR / f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
    with open(report_path, "w") as f:
        f.write(report_md)
    print(f"  Report saved: {report_path}")

    # Console summary
    print("\n" + "═" * 70)
    print("  CAUSALITY IMPACT SCORES (CES)")
    print("═" * 70)
    baseline = analysis["by_condition"].get("A_BASELINE", 0)
    for cname in CONDITIONS:
        ces = analysis["by_condition"].get(cname, 0)
        delta = ces - baseline
        print(f"  {cname:<20} CES={ces:.3f}  Δ={delta:+.3f}")
    print("═" * 70)
    print("\n  CES = 1 - similarity. Higher = subsystem is load-bearing.")
    print("═" * 70 + "\n")


if __name__ == "__main__":
    main()
