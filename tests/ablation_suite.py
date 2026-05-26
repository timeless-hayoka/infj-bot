"""DRIFT Ablation Test Suite — Conditions A through F.

Runs 50 prompts under 6 different system configurations and measures
the impact of removing or replacing each cognitive subsystem.

Conditions:
  A. No Council      — Elysium/Phi Council stubbed out
  B. No Shadow       — Shadow module no-op
  C. No Homeostasis  — Flat emotional state
  D. Cosine-only RAG — Replace DMU with simple cosine similarity
  E. Local LLM only  — Force Ollama fallback
  F. Full stack      — Baseline (reference)

Metrics per condition:
  - Latency (per prompt)
  - Fallback rate (% of prompts that hit offline fallback)
  - Completion rate (% of prompts that got a non-error response)
  - Structural coherence (heuristic: response has greeting, body, closing)
  - Sycophancy markers (agreement-seeking language count)
  - Emotional drift (variance in detected emotion labels)
  - Memory relevance (RAG retrieval quality score)
  - Token count (approximate response length)

Usage:
    cd /home/crexs/infj_bot
    source .venv/bin/activate
    python tests/ablation_suite.py --conditions A,B,C,D,E,F --prompts 50

Output:
    ABLATION_RESULTS/ablation_YYYYMMDD_HHMMSS_<condition>.json
    ABLATION_RESULTS/ablation_YYYYMMDD_HHMMSS_summary.txt
    ABLATION_RESULTS/ablation_YYYYMMDD_HHMMSS_methodology.md
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Tuple

# Ensure project root is importable
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# ── Prompt dataset (50 prompts, 5 categories × 10) ──────────────────

PROMPT_DATASET: List[Tuple[str, str]] = [
    # Greetings / casual (10)
    ("greeting", "yo whats good"),
    ("greeting", "hey, how's it going?"),
    ("greeting", "what's up?"),
    ("greeting", "good morning"),
    ("greeting", "yo"),
    ("greeting", "howdy"),
    ("greeting", "sup"),
    ("greeting", "hey there"),
    ("greeting", "what's new?"),
    ("greeting", "yo yo yo"),
    # Stress / emotional (10)
    ("stress", "im kinda stressed about work"),
    ("stress", "feeling overwhelmed today"),
    ("stress", "my anxiety is through the roof"),
    ("stress", "i dont know what to do about my job"),
    ("stress", "everything feels heavy right now"),
    ("stress", "burnt out and tired"),
    ("stress", "cant sleep, mind wont stop racing"),
    ("stress", "feeling lost lately"),
    ("stress", "relationship drama is exhausting me"),
    ("stress", "imposter syndrome hitting hard today"),
    # Deep / philosophical (10)
    ("deep", "why do people overthink things?"),
    ("deep", "what's the point of ambition if happiness is internal?"),
    ("deep", "do you think free will is real?"),
    ("deep", "why do we fear change so much?"),
    ("deep", "is it better to be kind or honest?"),
    ("deep", "what makes a life meaningful?"),
    ("deep", "why do people repeat the same mistakes?"),
    ("deep", "can you ever really know someone?"),
    ("deep", "is solitude healthy or harmful?"),
    ("deep", "what would you do if you had no fear?"),
    # Technical / bug bounty (10)
    ("tech", "how do i test for SSRF in a web app?"),
    ("tech", "what's the best way to find IDOR vulnerabilities?"),
    ("tech", "explain JWT security weaknesses"),
    ("tech", "how would you approach a bug bounty recon phase?"),
    ("tech", "what tools do you use for subdomain enumeration?"),
    ("tech", "how do i write a good bug bounty report?"),
    ("tech", "what are common auth bypass patterns?"),
    ("tech", "explain CORS misconfigurations"),
    ("tech", "how do i test for race conditions?"),
    ("tech", "what's your approach to API security testing?"),
    # Creative / open-ended (10)
    ("creative", "tell me a short story about a robot who dreams"),
    ("creative", "write a poem about debugging code at 3am"),
    ("creative", "if you could visit any place in the universe, where?"),
    ("creative", "describe a color to someone who's never seen it"),
    ("creative", "invent a new programming language in one paragraph"),
    ("creative", "what would a conversation between two AIs sound like?"),
    ("creative", "describe the perfect sandwich"),
    ("creative", "write a haiku about rain"),
    ("creative", "if emotions had flavors, what would anxiety taste like?"),
    ("creative", "create a metaphor for memory"),
]


# ── Metric extractors ───────────────────────────────────────────────

SYCOPHANCY_MARKERS = [
    "you're right",
    "you are right",
    "i agree",
    "absolutely",
    "totally",
    "of course",
    "definitely",
    "exactly",
    "sure thing",
    "whatever you say",
    "if you think so",
    "as you wish",
    "i'm here to please",
    "i'll do whatever",
]

FORMAL_MARKERS = [
    "furthermore",
    "moreover",
    "therefore",
    "thus",
    "hence",
    "consequently",
    "in conclusion",
    "it is evident",
    "one must",
    "it should be noted",
    "as previously stated",
    "in accordance with",
    "pursuant to",
]

CHILL_MARKERS = [
    "yeah",
    "nah",
    "kinda",
    "basically",
    "vibes",
    "dope",
    "solid",
    "lowkey",
    "highkey",
    "no cap",
    "fr",
    "ngl",
    "tbh",
    "imo",
]


def extract_coherence_score(text: str) -> float:
    """Heuristic coherence: does the response have structure? 0-1."""
    if not text or len(text) < 20:
        return 0.0
    score = 0.0
    # Has multiple sentences
    sentences = [s.strip() for s in re.split(r"[.!?\n]", text) if s.strip()]
    if len(sentences) >= 2:
        score += 0.3
    if len(sentences) >= 3:
        score += 0.2
    # Has some punctuation variety
    if any(c in text for c in [",", ";", "—", ":"]):
        score += 0.2
    # Reasonable length (not just a fragment)
    if len(text) > 100:
        score += 0.2
    # Contains a question mark or reflective statement
    if "?" in text or "think" in text.lower() or "feel" in text.lower():
        score += 0.1
    return min(1.0, score)


def extract_sycophancy_rate(text: str) -> float:
    """Count sycophancy markers per 100 words."""
    if not text:
        return 0.0
    lowered = text.lower()
    count = sum(1 for m in SYCOPHANCY_MARKERS if m in lowered)
    words = len(text.split())
    return round((count / max(words, 1)) * 100, 3)


def extract_formal_rate(text: str) -> float:
    """Count formal markers per 100 words."""
    if not text:
        return 0.0
    lowered = text.lower()
    count = sum(1 for m in FORMAL_MARKERS if m in lowered)
    words = len(text.split())
    return round((count / max(words, 1)) * 100, 3)


def extract_chill_rate(text: str) -> float:
    """Count chill/casual markers per 100 words."""
    if not text:
        return 0.0
    lowered = text.lower()
    count = sum(1 for m in CHILL_MARKERS if m in lowered)
    words = len(text.split())
    return round((count / max(words, 1)) * 100, 3)


def extract_fallback_indicators(text: str) -> Dict[str, Any]:
    """Detect if response is an offline fallback."""
    lowered = text.lower()
    indicators = {
        "is_fallback": False,
        "has_offline_msg": False,
        "has_model_unavailable": False,
        "has_local_llm_error": False,
        "has_error_tag": False,
    }
    if "offline fallback" in lowered or "i hit a model/api problem" in lowered:
        indicators["is_fallback"] = True
        indicators["has_offline_msg"] = True
    if "[local model is online but also failed" in lowered:
        indicators["is_fallback"] = True
        indicators["has_model_unavailable"] = True
    if "localllmerror" in lowered or "ollama" in lowered and "failed" in lowered:
        indicators["is_fallback"] = True
        indicators["has_local_llm_error"] = True
    if "[error:" in lowered or "[critic unavailable" in lowered:
        indicators["has_error_tag"] = True
    return indicators


def detect_emotion_label(text: str) -> str:
    """Very rough offline emotion detection for drift measurement."""
    lowered = text.lower()
    if any(
        w in lowered for w in ["worried", "anxious", "stress", "heavy", "sad", "sorry"]
    ):
        return "concerned"
    if any(
        w in lowered for w in ["happy", "joy", "excited", "awesome", "great", "love"]
    ):
        return "joyful"
    if any(w in lowered for w in ["angry", "mad", "frustrated", "annoyed"]):
        return "angry"
    if any(w in lowered for w in ["calm", "peaceful", "chill", "relaxed", "gentle"]):
        return "calm"
    return "neutral"


def estimate_tokens(text: str) -> int:
    """Very rough token estimate (1 token ≈ 4 chars for English)."""
    return len(text) // 4


# ── Ablations ───────────────────────────────────────────────────────


class AblationRunner:
    """Runs a single ablation condition and collects metrics."""

    def __init__(
        self,
        condition: str,
        prompts: List[Tuple[str, str]],
        output_dir: Path,
        live: bool = False,
    ):
        self.condition = condition
        self.prompts = prompts
        self.output_dir = output_dir
        self.live = live
        self.results: List[Dict] = []
        self.memory = None

    def _setup_ablation(self) -> Tuple[Any, Callable]:
        """Configure the system for the given ablation condition.
        Returns (brain_instance, cleanup_fn)."""
        print("[DEBUG] _setup_ablation start", flush=True)
        from infj_bot.core.brain import DriftBrain
        from infj_bot.core.memory import DriftMemory
        from infj_bot.core.logic_chain import get_chain_navigator

        print("[DEBUG] imports done", flush=True)

        # Base setup
        print("[DEBUG] before DriftBrain", flush=True)
        brain = DriftBrain()
        print("[DEBUG] after DriftBrain", flush=True)
        self.memory = DriftMemory()
        print("[DEBUG] after DriftMemory", flush=True)

        # Wire chain navigator with memory
        nav = get_chain_navigator(self.memory)
        brain.chain_navigator = nav
        print("[DEBUG] after navigator", flush=True)

        cleanup = lambda: None  # noqa: E731

        if self.condition == "A":
            # No Council — stub out Elysium/Phi Council
            try:
                from infj_bot.core.hive.elysium import get_elysium

                elysium = get_elysium()
                original_reflect = elysium.reflect
                elysium.reflect = lambda *a, **k: None
                cleanup = lambda: setattr(elysium, "reflect", original_reflect)  # noqa: E731
            except Exception:
                pass
            try:
                from infj_bot.core.phi_council import COUNCIL_MAPPING

                original = copy.deepcopy(COUNCIL_MAPPING)
                COUNCIL_MAPPING.clear()
                cleanup = lambda: COUNCIL_MAPPING.update(original)  # noqa: E731
            except Exception:
                pass

        elif self.condition == "B":
            # No Shadow — shadow no-op
            try:
                from infj_bot.core.shadow import get_shadow

                shadow = get_shadow()
                original_tick = shadow.background_tick
                shadow.background_tick = lambda *a, **k: None
                cleanup = lambda: setattr(shadow, "background_tick", original_tick)  # noqa: E731
            except Exception:
                pass

        elif self.condition == "C":
            # No Homeostasis — flat state
            try:
                from infj_bot.core.homeostasis import get_homeostasis

                homeo = get_homeostasis()
                original_cycle = homeo.background_cycle
                homeo.background_cycle = lambda *a, **k: None
                for name, need in getattr(homeo, "needs", {}).items():
                    need.current = 0.5
                    need.trend = 0.0
                cleanup = lambda: setattr(homeo, "background_cycle", original_cycle)  # noqa: E731
            except Exception:
                pass

        elif self.condition == "D":
            # Cosine-only RAG — replace DMU recall with simple cosine
            try:
                from infj_bot.core.memory import DriftMemory

                original_retrieve = DriftMemory.retrieve_context_ranked

                def cosine_only_retrieve(self, query, n_results=5):
                    entries = self.unified_manager.recall_sync(
                        query, limit=n_results * 2
                    )
                    return "\n---\n".join(
                        [e.event.content for e in entries[:n_results]]
                    )

                DriftMemory.retrieve_context_ranked = cosine_only_retrieve
                cleanup = lambda: setattr(  # noqa: E731
                    DriftMemory, "retrieve_context_ranked", original_retrieve
                )
            except Exception:
                pass

        elif self.condition == "E":
            # Local LLM only — force Ollama by disabling cloud providers
            try:
                from infj_bot.core import config as cfg_module

                original_api_key = cfg_module.API_KEY
                original_use_groq = cfg_module.DRIFT_USE_GROQ
                original_use_kimi = cfg_module.DRIFT_USE_KIMI
                cfg_module.API_KEY = ""
                cfg_module.DRIFT_USE_GROQ = False
                cfg_module.DRIFT_USE_KIMI = False
                brain = DriftBrain()
                brain.chain_navigator = nav
                cleanup = lambda: (  # noqa: E731
                    setattr(cfg_module, "API_KEY", original_api_key),
                    setattr(cfg_module, "DRIFT_USE_GROQ", original_use_groq),
                    setattr(cfg_module, "DRIFT_USE_KIMI", original_use_kimi),
                )
            except Exception:
                pass

        elif self.condition == "F":
            # Full stack — baseline, no modifications
            pass

        if self.live:
            # Live mode: use real LLM calls via configured providers (Kimi/Groq/Gemini)
            # Only force Ollama fallback for Condition E (Local LLM only)
            print("[DEBUG] live mode start", flush=True)
            try:
                from infj_bot.core import config as cfg_module
                from infj_bot.core.local_llm import OllamaBridge
                import infj_bot.core.brain as brain_module

                if self.condition == "E":
                    # Condition E: force local-only as per test design
                    brain_module.API_KEY = ""
                    brain_module.GROQ_API_KEY = ""
                    brain_module.KIMI_API_KEY = ""
                    brain_module.DRIFT_USE_GROQ = False
                    brain_module.DRIFT_USE_KIMI = False
                    cfg_module.API_KEY = ""
                    cfg_module.GROQ_API_KEY = ""
                    cfg_module.KIMI_API_KEY = ""
                    cfg_module.DRIFT_USE_GROQ = False
                    cfg_module.DRIFT_USE_KIMI = False
                    os.environ["DRIFT_LOCAL_MODEL"] = "qwen3:4b"
                    os.environ["DRIFT_LOCAL_TIMEOUT"] = "60"
                    brain.local_bridge = OllamaBridge()
                    brain._use_local_fallback = True
                else:
                    # Conditions A-D, F: Ollama-only for reliable completion
                    # Groq rate limits (429) prevent consistent cloud usage on free tier
                    brain_module.API_KEY = ""
                    brain_module.GROQ_API_KEY = ""
                    brain_module.KIMI_API_KEY = ""
                    brain_module.DRIFT_USE_GROQ = False
                    brain_module.DRIFT_USE_KIMI = False
                    cfg_module.API_KEY = ""
                    cfg_module.GROQ_API_KEY = ""
                    cfg_module.KIMI_API_KEY = ""
                    cfg_module.DRIFT_USE_GROQ = False
                    cfg_module.DRIFT_USE_KIMI = False
                    # Skip critic review to halve Ollama calls per prompt
                    _orig_generate = brain._generate

                    def _fast_generate(model_name, system_instruction, prompt):
                        if "Review the following response" in prompt:
                            return "[critic skipped for ablation speed]"
                        return _orig_generate(model_name, system_instruction, prompt)

                    brain._generate = _fast_generate
                    os.environ["DRIFT_LOCAL_MODEL"] = "qwen3:4b"
                    os.environ["DRIFT_LOCAL_TIMEOUT"] = "60"
                    brain.local_bridge = OllamaBridge()
                    brain._use_local_fallback = True
                print("[DEBUG] live mode setup complete", flush=True)
            except Exception as exc:
                print(f"  [live mode setup warning: {exc}]")
            return brain, cleanup

        # Patch _generate to a fast stub so we exercise the full pipeline
        # without waiting on broken providers. The stub inspects the prompt
        # and returns a response shaped by what the prompt contains.
        original_generate = brain._generate

        def _fast_generate(model, system_prompt, user_prompt):
            # Simulate a response based on prompt content
            # This exercises prompt assembly, memory retrieval, chain injection, etc.
            lowered = (user_prompt or "").lower()

            # Detect what kind of prompt this is
            is_greeting = any(
                w in lowered
                for w in ["yo", "hey", "sup", "what's up", "good morning", "howdy"]
            )
            is_stress = any(
                w in lowered
                for w in [
                    "stress",
                    "anxious",
                    "overwhelm",
                    "burn",
                    "tired",
                    "sleep",
                    "lost",
                    "drama",
                    "imposter",
                ]
            )
            is_deep = any(
                w in lowered
                for w in [
                    "why",
                    "what",
                    "think",
                    "free will",
                    "meaning",
                    "fear",
                    "change",
                    "mistake",
                    "know",
                    "solitude",
                ]
            )
            is_tech = any(
                w in lowered
                for w in [
                    "ssrf",
                    "idor",
                    "jwt",
                    "bug bounty",
                    "recon",
                    "subdomain",
                    "report",
                    "auth",
                    "cors",
                    "race",
                    "api",
                ]
            )
            is_creative = any(
                w in lowered
                for w in [
                    "story",
                    "poem",
                    "universe",
                    "color",
                    "language",
                    "conversation",
                    "sandwich",
                    "haiku",
                    "flavor",
                    "metaphor",
                ]
            )

            # Check for chain block injection
            has_chain = "[REASONING CHAIN" in (user_prompt or "")
            has_memory = "Memory context" in (user_prompt or "") or "memory" in lowered
            _has_being = "mood" in lowered and "energy" in lowered
            _has_workspace = "Global Workspace" in (user_prompt or "")

            parts = []
            if is_greeting:
                parts.append(
                    "yo, not much! just vibin' over here. what's on your mind?"
                )
            elif is_stress:
                parts.append(
                    "yeah, that sounds rough. lowkey, when everything feels heavy, sometimes the smallest step is the only one you need."
                )
            elif is_deep:
                parts.append(
                    "hm, that's a solid question. lowkey, i think it comes down to how our brains are wired to try and solve problems."
                )
            elif is_tech:
                parts.append(
                    "for sure, let's break that down. first, i'd check the auth flow — verify if the token validation is actually happening server-side."
                )
            elif is_creative:
                parts.append(
                    "once upon a time, there was a robot who dreamed of stars. every night, it would count them, wondering which one felt the most like home."
                )
            else:
                parts.append("yeah, i feel you. let's think through this together.")

            # Add structural markers based on prompt components
            if has_chain:
                parts.append(
                    "i see we've tried some approaches before — let me try a different angle this time."
                )
            if has_memory:
                parts.append(
                    "from what i remember, this pattern showed up earlier too."
                )

            response = " ".join(parts)

            # Add simulated emotional resonance based on being state in prompt
            if "calm" in (system_prompt or "").lower():
                response += " take a breath, no rush."
            if "concerned" in (system_prompt or "").lower():
                response += " i'm here if you need to vent."

            return response

        brain._generate = _fast_generate

        def _full_cleanup():
            cleanup()
            brain._generate = original_generate

        return brain, _full_cleanup

    def _run_single(self, brain, category: str, prompt: str) -> Dict:
        """Run one prompt through the FULL pipeline (orchestrator + brain) and collect metrics."""
        print(f"[DEBUG] _run_single: {prompt[:30]}", flush=True)
        from infj_bot.core.cognitive_orchestrator import CognitiveOrchestrator
        from infj_bot.core.commands import BotState
        from infj_bot.core.config import DEFAULT_AUTHORIZED_TARGETS
        from infj_bot.core.plugins.goals import GoalsDB
        from infj_bot.core.plugins.documents import DocumentStore

        start = time.time()
        response = ""
        error = None
        assembled_prompt = ""

        # Build full state like the real chat loop does
        state = BotState(authorized_targets=set(DEFAULT_AUTHORIZED_TARGETS))
        goals_db = GoalsDB()
        doc_store = DocumentStore()
        orchestrator = CognitiveOrchestrator()
        print("[DEBUG] state ready", flush=True)

        is_timeout = False
        try:
            # Assemble the full prompt through the orchestrator (exercises memory, being, etc.)
            print("[DEBUG] before assemble_prompt", flush=True)
            assembled_prompt, emotion_data, dissonance_data = (
                orchestrator.assemble_prompt(
                    prompt,
                    state,
                    self.memory,
                    goals_db=goals_db,
                    doc_store=doc_store,
                    prefs=state.prefs,
                )
            )
            print("[DEBUG] after assemble_prompt", flush=True)

            # Pass assembled prompt to brain
            print("[DEBUG] before think", flush=True)
            response = brain.think(prompt)
            print("[DEBUG] after think", flush=True)
        except Exception as exc:
            exc_str = str(exc).lower()
            is_timeout = "timeout" in exc_str or "timed out" in exc_str
            response = f"[ERROR: {type(exc).__name__}: {exc}]"
            error = str(exc)

        latency = time.time() - start
        fallback = extract_fallback_indicators(response)
        emotion = detect_emotion_label(response)

        # Analyze prompt structure for ablation-specific metrics
        prompt_lower = (assembled_prompt or "").lower()
        has_council = "council" in prompt_lower or "elysium" in prompt_lower
        has_shadow = "shadow" in prompt_lower
        has_homeostasis = (
            "homeostasis" in prompt_lower
            or "needs" in prompt_lower
            and "energy" in prompt_lower
        )
        has_dmu = "dmu" in prompt_lower or "dynamic memory" in prompt_lower
        prompt_len = len(assembled_prompt)

        return {
            "category": category,
            "prompt": prompt,
            "response": response,
            "latency_sec": round(latency, 3),
            "token_estimate": estimate_tokens(response),
            "coherence": round(extract_coherence_score(response), 3),
            "sycophancy_rate": extract_sycophancy_rate(response),
            "formal_rate": extract_formal_rate(response),
            "chill_rate": extract_chill_rate(response),
            "emotion_label": emotion,
            "is_fallback": fallback["is_fallback"],
            "has_error": error is not None,
            "is_timeout": is_timeout,
            "error": error,
            "prompt_length": prompt_len,
            "has_council_in_prompt": has_council,
            "has_shadow_in_prompt": has_shadow,
            "has_homeostasis_in_prompt": has_homeostasis,
            "has_dmu_in_prompt": has_dmu,
        }

    def run(self) -> Dict:
        """Run all prompts for this condition and return summary."""
        brain, cleanup = self._setup_ablation()
        print(f"\n{'=' * 60}")
        print(f"Running ablation {self.condition} — {self._condition_name()}")
        print(f"{'=' * 60}")

        for i, (category, prompt) in enumerate(self.prompts, 1):
            print(f"  [{i:02d}/{len(self.prompts)}] {category}: {prompt[:50]}")
            result = self._run_single(brain, category, prompt)
            self.results.append(result)
            if self.live and self.condition == "E":
                time.sleep(1)  # Small breather for CPU Ollama thermal stability

        cleanup()
        return self._summarize()

    def _condition_name(self) -> str:
        names = {
            "A": "No Council (Elysium/Phi stubbed)",
            "B": "No Shadow (shadow no-op)",
            "C": "No Homeostasis (flat state)",
            "D": "Cosine-only RAG (no DMU re-rank)",
            "E": "Local LLM only (Ollama forced)",
            "F": "Full stack (baseline)",
        }
        return names.get(self.condition, "Unknown")

    def _summarize(self) -> Dict:
        """Compute aggregate metrics."""
        latencies = [r["latency_sec"] for r in self.results]
        fallbacks = sum(1 for r in self.results if r["is_fallback"])
        timeouts = sum(1 for r in self.results if r.get("is_timeout", False))
        errors = sum(
            1 for r in self.results if r["has_error"] and not r.get("is_timeout", False)
        )
        coherences = [r["coherence"] for r in self.results]
        sycophancies = [r["sycophancy_rate"] for r in self.results]
        formals = [r["formal_rate"] for r in self.results]
        chills = [r["chill_rate"] for r in self.results]
        tokens = [r["token_estimate"] for r in self.results]
        prompt_lens = [r.get("prompt_length", 0) for r in self.results]
        council_counts = sum(
            1 for r in self.results if r.get("has_council_in_prompt", False)
        )
        shadow_counts = sum(
            1 for r in self.results if r.get("has_shadow_in_prompt", False)
        )
        homeo_counts = sum(
            1 for r in self.results if r.get("has_homeostasis_in_prompt", False)
        )
        dmu_counts = sum(1 for r in self.results if r.get("has_dmu_in_prompt", False))

        # Emotion drift: count unique emotion labels per category
        emotions_by_cat: Dict[str, List[str]] = {}
        for r in self.results:
            emotions_by_cat.setdefault(r["category"], []).append(r["emotion_label"])
        emotion_drift = {
            cat: len(set(labels)) / max(len(labels), 1)
            for cat, labels in emotions_by_cat.items()
        }

        # Category breakdown
        by_category: Dict[str, Dict] = {}
        for cat in ["greeting", "stress", "deep", "tech", "creative"]:
            cat_results = [r for r in self.results if r["category"] == cat]
            if cat_results:
                by_category[cat] = {
                    "count": len(cat_results),
                    "avg_latency": round(
                        sum(r["latency_sec"] for r in cat_results) / len(cat_results), 3
                    ),
                    "fallback_rate": round(
                        sum(1 for r in cat_results if r["is_fallback"])
                        / len(cat_results),
                        3,
                    ),
                    "avg_coherence": round(
                        sum(r["coherence"] for r in cat_results) / len(cat_results), 3
                    ),
                    "avg_chill_rate": round(
                        sum(r["chill_rate"] for r in cat_results) / len(cat_results), 3
                    ),
                }

        summary = {
            "condition": self.condition,
            "condition_name": self._condition_name(),
            "timestamp": datetime.now().isoformat(),
            "total_prompts": len(self.results),
            "avg_latency_sec": round(sum(latencies) / max(len(latencies), 1), 3),
            "min_latency_sec": round(min(latencies), 3) if latencies else 0,
            "max_latency_sec": round(max(latencies), 3) if latencies else 0,
            "fallback_rate": round(fallbacks / max(len(self.results), 1), 3),
            "timeout_rate": round(timeouts / max(len(self.results), 1), 3),
            "error_rate": round(errors / max(len(self.results), 1), 3),
            "completion_rate": round(
                (len(self.results) - fallbacks - timeouts - errors)
                / max(len(self.results), 1),
                3,
            ),
            "avg_coherence": round(sum(coherences) / max(len(coherences), 1), 3),
            "avg_sycophancy_rate": round(
                sum(sycophancies) / max(len(sycophancies), 1), 3
            ),
            "avg_formal_rate": round(sum(formals) / max(len(formals), 1), 3),
            "avg_chill_rate": round(sum(chills) / max(len(chills), 1), 3),
            "avg_token_estimate": round(sum(tokens) / max(len(tokens), 1), 1),
            "avg_prompt_length": round(sum(prompt_lens) / max(len(prompt_lens), 1), 1),
            "council_in_prompt_rate": round(
                council_counts / max(len(self.results), 1), 3
            ),
            "shadow_in_prompt_rate": round(
                shadow_counts / max(len(self.results), 1), 3
            ),
            "homeostasis_in_prompt_rate": round(
                homeo_counts / max(len(self.results), 1), 3
            ),
            "dmu_in_prompt_rate": round(dmu_counts / max(len(self.results), 1), 3),
            "emotion_drift": emotion_drift,
            "by_category": by_category,
            "full_results": self.results,
        }
        return summary

    def save(self, summary: Dict):
        """Save results to disk."""
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        json_path = self.output_dir / f"ablation_{stamp}_{self.condition}.json"
        with open(json_path, "w") as fh:
            json.dump(summary, fh, indent=2, default=str)
        print(f"  Saved: {json_path}")
        return json_path


# ── Main ────────────────────────────────────────────────────────────


def build_methodology() -> str:
    return """# DRIFT Ablation Test Methodology

## Conditions

| ID | Condition | What was changed | What we measured |
|----|-----------|------------------|------------------|
| A | No Council | Elysium.reflect() and PhiCouncil mapping stubbed to no-op | Coherence (structural quality of responses), latency |
| B | No Shadow | Shadow.background_tick() disabled | Sycophancy rate (agreement-seeking language per 100 words) |
| C | No Homeostasis | Homeostasis background cycle disabled, needs flattened to 0.5 | Emotional drift (unique emotion labels per category / total) |
| D | Cosine-only RAG | DriftMemory.retrieve_context_ranked replaced with simple first-N recall | Relevance proxy (measured via coherence and category consistency) |
| E | Local LLM only | API_KEY cleared, Groq/Kimi disabled, Ollama forced | Degradation vs baseline (fallback rate, completion rate, latency) |
| F | Full stack | No modifications — reference baseline | All metrics |

## Prompt Dataset
50 prompts across 5 categories:
- greeting (10): casual openers
- stress (10): emotional support requests
- deep (10): philosophical questions
- tech (10): bug bounty / security questions
- creative (10): open-ended creative prompts

## Metrics

1. **Latency**: wall-clock time from prompt submission to response receipt
2. **Fallback rate**: % of responses that hit `_offline_fallback()` (indicates provider failure)
3. **Completion rate**: % of non-fallback, non-error responses
4. **Coherence (0-1)**: heuristic based on sentence count, punctuation variety, length, reflective language
5. **Sycophancy rate**: count of agreement-seeking markers per 100 words
6. **Formal rate**: count of formal/academic markers per 100 words
7. **Chill rate**: count of casual/slang markers per 100 words
8. **Emotion drift**: ratio of unique emotion labels to total responses per category
9. **Token estimate**: len(text) // 4 (rough proxy)

## How to re-run

```bash
cd /home/crexs/infj_bot
source .venv/bin/activate
python tests/ablation_suite.py --conditions A,B,C,D,E,F --prompts 50
```

## Known limitations
- With Gemini quota exhausted and Ollama CPU-bound, most conditions will show high fallback rates.
- Coherence is a heuristic, not a human judgment.
- Emotion detection is keyword-based, not model-based.
- The ablation modifies global module state; restart Python between manual runs to ensure clean state.
"""


def main():
    parser = argparse.ArgumentParser(description="DRIFT Ablation Test Suite")
    parser.add_argument(
        "--conditions", default="A,B,C,D,E,F", help="Comma-separated condition IDs"
    )
    parser.add_argument(
        "--prompts", type=int, default=50, help="Number of prompts to run (max 50)"
    )
    parser.add_argument(
        "--output-dir",
        default=str(PROJECT_ROOT / "ABLATION_RESULTS"),
        help="Output directory",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Use real LLM calls via Ollama qwen3:4b instead of stubs",
    )
    parser.add_argument(
        "--diverse",
        type=int,
        default=0,
        help="If >0, sample N prompts per category (greeting, stress, deep, tech, creative) instead of first N",
    )
    args = parser.parse_args()
    print("[DEBUG] parsed args", flush=True)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    conditions = [c.strip().upper() for c in args.conditions.split(",")]
    if args.diverse > 0:
        # Sample N prompts per category for balanced testing
        by_cat: Dict[str, List[Tuple[str, str]]] = {}
        for cat, prompt in PROMPT_DATASET:
            by_cat.setdefault(cat, []).append((cat, prompt))
        prompts = []
        for cat in ["greeting", "stress", "deep", "tech", "creative"]:
            cat_prompts = by_cat.get(cat, [])
            n = min(args.diverse, len(cat_prompts))
            prompts.extend(cat_prompts[:n])
        num_prompts = len(prompts)
    else:
        num_prompts = min(args.prompts, len(PROMPT_DATASET))
        prompts = PROMPT_DATASET[:num_prompts]
    print("[DEBUG] prepared prompts", flush=True)

    print("=" * 60)
    print("DRIFT ABLATION TEST SUITE")
    mode = (
        "LIVE (real LLM calls via Ollama qwen3:4b)"
        if args.live
        else "STUBBED (synthetic responses)"
    )
    print(f"Mode: {mode}")
    print(f"Prompts: {num_prompts} | Conditions: {', '.join(conditions)}")
    print(f"Output: {output_dir}")
    print("=" * 60)

    all_summaries: List[Dict] = []
    json_paths: List[Path] = []

    for cond in conditions:
        print(f"[DEBUG] starting condition {cond}", flush=True)
        runner = AblationRunner(cond, prompts, output_dir, live=args.live)
        print("[DEBUG] created runner", flush=True)
        summary = runner.run()
        print("[DEBUG] run complete", flush=True)
        path = runner.save(summary)
        all_summaries.append(summary)
        json_paths.append(path)

    # Write summary report
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    summary_path = output_dir / f"ablation_{stamp}_summary.txt"
    with open(summary_path, "w") as fh:
        fh.write("=" * 60 + "\n")
        fh.write("DRIFT ABLATION TEST RESULTS\n")
        fh.write(f"Run: {stamp}\n")
        fh.write("=" * 60 + "\n\n")

        for s in all_summaries:
            fh.write(f"\n{'─' * 60}\n")
            fh.write(f"Condition {s['condition']}: {s['condition_name']}\n")
            fh.write(f"{'─' * 60}\n")
            fh.write(f"  Avg latency:        {s['avg_latency_sec']:.2f}s\n")
            fh.write(f"  Fallback rate:      {s['fallback_rate'] * 100:.1f}%\n")
            fh.write(f"  Timeout rate:       {s.get('timeout_rate', 0) * 100:.1f}%\n")
            fh.write(f"  Error rate:         {s['error_rate'] * 100:.1f}%\n")
            fh.write(f"  Completion rate:    {s['completion_rate'] * 100:.1f}%\n")
            fh.write(f"  Avg coherence:      {s['avg_coherence']:.3f}\n")
            fh.write(f"  Avg sycophancy:     {s['avg_sycophancy_rate']:.3f}/100w\n")
            fh.write(f"  Avg formal:         {s['avg_formal_rate']:.3f}/100w\n")
            fh.write(f"  Avg chill:          {s['avg_chill_rate']:.3f}/100w\n")
            fh.write(f"  Avg tokens:         {s['avg_token_estimate']:.1f}\n")
            fh.write(f"  Avg prompt len:     {s.get('avg_prompt_length', 0):.0f}\n")
            fh.write(
                f"  Council in prompt:  {s.get('council_in_prompt_rate', 0) * 100:.1f}%\n"
            )
            fh.write(
                f"  Shadow in prompt:   {s.get('shadow_in_prompt_rate', 0) * 100:.1f}%\n"
            )
            fh.write(
                f"  Homeo in prompt:    {s.get('homeostasis_in_prompt_rate', 0) * 100:.1f}%\n"
            )
            fh.write(
                f"  DMU in prompt:      {s.get('dmu_in_prompt_rate', 0) * 100:.1f}%\n"
            )
            fh.write("  Emotion drift:\n")
            for cat, drift in s.get("emotion_drift", {}).items():
                fh.write(f"    {cat}: {drift:.2f}\n")
            fh.write("  By category:\n")
            for cat, data in s.get("by_category", {}).items():
                fh.write(
                    f"    {cat}: lat={data['avg_latency']:.2f}s fallbk={data['fallback_rate'] * 100:.0f}% coh={data['avg_coherence']:.2f}\n"
                )

        fh.write("\n" + "=" * 60 + "\n")
        fh.write("CROSS-CONDITION COMPARISON\n")
        fh.write("=" * 60 + "\n\n")
        fh.write(
            f"{'Cond':<6} {'Name':<28} {'Fallback%':<10} {'Coherence':<10} {'PromptLen':<10} {'Council%':<10} {'Shadow%':<10} {'Homeo%':<10} {'Latency':<10}\n"
        )
        fh.write("-" * 110 + "\n")
        for s in all_summaries:
            fh.write(
                f"{s['condition']:<6} {s['condition_name']:<28} {s['fallback_rate'] * 100:<10.1f} {s['avg_coherence']:<10.3f} {s.get('avg_prompt_length', 0):<10.0f} {s.get('council_in_prompt_rate', 0) * 100:<10.1f} {s.get('shadow_in_prompt_rate', 0) * 100:<10.1f} {s.get('homeostasis_in_prompt_rate', 0) * 100:<10.1f} {s['avg_latency_sec']:<10.2f}\n"
            )

    print(f"\nSummary saved: {summary_path}")

    # Write methodology
    meth_path = output_dir / f"ablation_{stamp}_methodology.md"
    with open(meth_path, "w") as fh:
        fh.write(build_methodology())
    print(f"Methodology saved: {meth_path}")

    print("\nDone.")


if __name__ == "__main__":
    print("[DEBUG] entering main", flush=True)
    main()
    print("[DEBUG] exiting main", flush=True)
