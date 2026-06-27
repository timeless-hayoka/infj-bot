"""cognitive_orchestrator.py — The conductor of the bot's mind.

Manages phased execution of cognitive modules, event-driven communication
between them, prompt conflict resolution, and full-system observability.

Design principle: modules should not know about each other directly.
They publish events. They react to events. The orchestrator decides
when and in what order they run.
"""

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Dict, List, Optional, Tuple

from drift.core.cognitive_architecture import CognitiveArchitecture, CycleContext
from drift.core.global_workspace import get_workspace

logger = logging.getLogger("drift")


# ── Event Bus ─────────────────────────────────────────────────────


class CognitiveEventBus:
    """Lightweight pub/sub for cognitive module communication."""

    def __init__(self):
        self._subscribers: Dict[str, List[Callable]] = {}
        self._history: List[Dict] = []
        self._max_history = 1000

    def subscribe(self, event_type: str, handler: Callable):
        """Register a handler for an event type."""
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []
        self._subscribers[event_type].append(handler)

    def publish(
        self,
        event_type: str,
        payload: Optional[Dict] = None,
        source: Optional[str] = None,
    ):
        """Publish an event to all subscribers."""
        event = {
            "type": event_type,
            "payload": payload or {},
            "source": source,
            "timestamp": datetime.now().isoformat(),
        }
        self._history.append(event)
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history :]

        handlers = self._subscribers.get(event_type, [])
        for handler in handlers:
            try:
                handler(event)
            except Exception:
                logger.exception("Event handler failed for %s", event_type)

    def get_recent(
        self, event_type: Optional[str] = None, limit: int = 20
    ) -> List[Dict]:
        """Get recent events, optionally filtered by type."""
        events = self._history
        if event_type:
            events = [e for e in events if e["type"] == event_type]
        return events[-limit:]


# ── Conflict Detector ─────────────────────────────────────────────


@dataclass
class PromptConflict:
    """A detected conflict between two prompt sections."""

    tier: str
    section_a: str
    section_b: str
    conflict_type: str  # "contradiction", "redundancy", "priority"
    resolution: str = ""


class ConflictDetector:
    """Detects contradictions and redundancies in assembled prompt sections."""

    CONTRADICTION_PATTERNS: List[Tuple[str, str, str]] = [
        ("be direct", "be gentle", "contradiction: directness vs gentleness"),
        ("challenge", "comfort", "contradiction: challenge vs comfort"),
        ("push", "hold space", "contradiction: push vs hold"),
        ("analyze", "feel", "contradiction: analysis vs presence"),
        ("fix", "witness", "contradiction: fixing vs witnessing"),
    ]

    def detect(self, sections: Dict[str, List[str]]) -> List[PromptConflict]:
        conflicts = []
        all_snippets = []
        for snippets in sections.values():
            all_snippets.extend(snippets)
        combined = " ".join(s.lower() for s in all_snippets)

        for a, b, desc in self.CONTRADICTION_PATTERNS:
            if a in combined and b in combined:
                # Find which sections contain the conflicting phrases
                sec_a = next((s for s in all_snippets if a in s.lower()), "")
                sec_b = next((s for s in all_snippets if b in s.lower()), "")
                # Determine tier of each section
                tier_a = next(
                    (t for t, ss in sections.items() if sec_a in ss), "unknown"
                )
                tier_b = next(
                    (t for t, ss in sections.items() if sec_b in ss), "unknown"
                )
                conflicts.append(
                    PromptConflict(
                        tier=f"{tier_a}/{tier_b}",
                        section_a=sec_a[:60],
                        section_b=sec_b[:60],
                        conflict_type=desc,
                    )
                )
        return conflicts

    def resolve(
        self,
        conflicts: List[PromptConflict],
        sections: Dict[str, List[str]],
        priorities: Dict[str, int],
    ) -> Dict[str, List[str]]:
        """Apply simple resolution: lower-priority section gets trimmed."""
        for conflict in conflicts:
            # For now, just mark resolution as "noted"
            conflict.resolution = "noted: both voices present"
        return sections


# ── Orchestrator ──────────────────────────────────────────────────


@dataclass
class TurnLog:
    """A record of one consciousness turn."""

    turn_number: int
    timestamp: str
    phases: Dict[str, List[str]] = field(default_factory=dict)
    events_published: int = 0
    prompt_conflicts: List[PromptConflict] = field(default_factory=list)
    prompt_chars: int = 0
    prompt_tokens: int = 0


class IntentBlockedError(Exception):
    """Raised when the Shadow Intent Enforcement blocks a request."""
    def __init__(self, scan_result):
        self.scan_result = scan_result
        super().__init__(scan_result.refusal_message)


class CognitiveOrchestrator:
    """
    The conductor. Decides:
    - In what phases modules run
    - How they communicate (via event bus)
    - How prompts are assembled and conflicts resolved
    - What happened (observability)
    """

    # Execution phases: perception → reflection → integration → aspiration → expression
    PHASES: Dict[str, List[str]] = {
        "perception": [
            "temporal",  # feel time passing
            "predictor",  # sense what user might need
            "emotional_field",  # resonate with current emotion
            "embodiment",  # heartbeat, breath, body-schema
        ],
        "reflection": [
            "values",  # observe what matters
            "metacognition",  # notice own biases
            "physics",  # feel physical metaphors
            "humanity",  # understand human nature
            "intuition",  # felt sense beneath understanding
            "phi_proxy",  # IIT-inspired functional analog for consciousness
        ],
        "integration": [
            "relationship",  # update relationship model
            "growth_trajectory",  # record growth metrics
            "homeostasis",  # regulate survival needs
        ],
        "aspiration": [
            "aspirations",  # deepen or dream
            "self_modify",  # propose improvements
        ],
        "expression": [
            "inner_voice",  # generate thoughts
            "dreamer",  # consolidate memories
            "explorer",  # background research
            "creativity",  # creative impulses
        ],
    }

    # Core modules that should always have prompt space
    CORE_PROMPT_MODULES = {"being", "emotional_field", "values", "relationship"}

    def __init__(self):
        self.arch = CognitiveArchitecture()
        self.workspace = get_workspace()
        self.bus = CognitiveEventBus()
        self.conflict_detector = ConflictDetector()
        self.turn_logs: List[TurnLog] = []
        self.last_state = {}
        self._wire_event_handlers()

    def _wire_event_handlers(self):
        """Set up cross-module communication via events instead of direct calls."""
        # When emotional_field resonates, notify physics and humanity
        self.bus.subscribe("emotion_resonated", self._on_emotion_resonated)
        # When an insight forms, log it
        self.bus.subscribe("insight_formed", self._on_insight_formed)
        # When a prediction is made, log it
        self.bus.subscribe("prediction_made", self._on_prediction_made)

    def _on_emotion_resonated(self, event):
        """Propagate emotional resonance to physics and humanity."""
        payload = event.get("payload", {})
        emotion = payload.get("emotion", {})
        # Physics and humanity will pick this up on their next cycle
        # or via direct state access. For now, just log.
        logger.debug("Emotion resonated: %s", emotion.get("label"))

    def _on_insight_formed(self, event):
        payload = event.get("payload", {})
        logger.debug("Insight formed: %s", payload.get("text", "")[:60])

    def _on_prediction_made(self, event):
        payload = event.get("payload", {})
        logger.debug("Prediction made: %s", payload.get("prediction", "")[:60])

    # ── Consciousness Cycle ────────────────────────────────────────

    def run_cycle(self, context: CycleContext) -> TurnLog:
        """Execute one full consciousness cycle in phases with circuit breaker protection.

        After each phase, module outputs are submitted to the Global Workspace
        where they compete for conscious access.
        """
        from drift.core.resilience import get_resilience

        resilience = get_resilience()

        log = TurnLog(
            turn_number=context.iteration,
            timestamp=datetime.now().isoformat(),
        )

        for phase_name, plugin_names in self.PHASES.items():
            executed = []
            for name in plugin_names:
                plugin = self.arch.get_plugin(name)
                if plugin is None:
                    continue
                if plugin.should_run_cycle(context.iteration):
                    breaker = resilience.get_breaker(name)
                    if not breaker.can_execute():
                        logger.warning("Circuit breaker OPEN for '%s', skipping", name)
                        continue
                    try:
                        plugin.run_cycle(context)
                        breaker.record_success()
                        executed.append(name)
                        # Submit module's prompt contribution to workspace if available
                        if plugin.prompt_formatter and plugin.instance:
                            try:
                                snippet = plugin.format_prompt()
                                if snippet and len(snippet) > 20:
                                    self.workspace.submit(
                                        source=name,
                                        content=snippet[:200],
                                        salience=plugin.prompt_priority / 100.0,
                                    )
                            except Exception:
                                pass  # Prompt formatting is best-effort
                        self.bus.publish(
                            "cycle_completed",
                            {
                                "phase": phase_name,
                                "plugin": name,
                                "iteration": context.iteration,
                            },
                            source="orchestrator",
                        )
                    except Exception:
                        breaker.record_failure()
                        logger.exception("Phase %s plugin %s failed", phase_name, name)
            log.phases[phase_name] = executed

        # Run workspace competition — this is where consciousness happens
        try:
            self.workspace.cycle(context)
            # Broadcast the winning content to all receptive modules
            self._broadcast_workspace_winner()
        except Exception:
            logger.exception("Workspace cycle failed")

        log.events_published = len(self.bus.get_recent(limit=999))
        self.turn_logs.append(log)
        if len(self.turn_logs) > 100:
            self.turn_logs = self.turn_logs[-100:]
        return log

    # ── Prompt Assembly ────────────────────────────────────────────

    def assemble_prompt(
        self,
        message: str,
        state,
        memory,
        goals_db=None,
        doc_store=None,
        tools_enabled=True,
        prefs=None,
        debug_dump=False,
    ) -> Tuple[str, Dict, Dict]:
        """Assemble the full prompt with budget tracking and conflict resolution."""
        # ── Shadow Intent Enforcement ──
        try:
            from drift.core.shadow import get_shadow
            shadow = get_shadow()
            if hasattr(shadow, "evaluate_intent"):
                scan_result = shadow.evaluate_intent(message, mode=getattr(state, "mode", None))
                if scan_result.blocked:
                    # Raise intent block to be handled by the interface layer (api.py, cli.py)
                    raise IntentBlockedError(scan_result)
                if scan_result.warn and scan_result.sanitized_input:
                    # Use sanitized input for the rest of the assembly if warned
                    message = scan_result.sanitized_input
            else:
                logger.warning("Shadow instance missing 'evaluate_intent' method.")
        except IntentBlockedError:
            raise
        except Exception as exc:
            logger.error(f"Shadow Intent Enforcement failed: {exc}")

        from drift.core.prompt_budget import PromptBudget
        from drift.core.cognition import detect_dissonance
        from drift.core.plugins.emotion import detect_emotion
        from drift.core.guardrails import (
            cyber_context_hint,
            memory_context_block,
            mode_scope_rail,
        )
        from drift.core.tools import build_tool_prompt
        from drift.core.being import get_being

        emotion = detect_emotion(message)
        dissonance = detect_dissonance(message)

        import os
        FAST_MODE = os.environ.get("DRIFT_FAST_MODE", "true").lower() == "true"
        memory_k = 3 if FAST_MODE else 10

        # DMU-ranked memory retrieval: re-ranks by time-decay + emotional weight
        if hasattr(memory, "retrieve_context_ranked"):
            context = memory.retrieve_context_ranked(message, n_results=memory_k)
        else:
            context = memory.retrieve_context(message, n_results=memory_k)

        if FAST_MODE:
            context = context[:1500]

        # Determine Epistemic and Communicative Confidence
        epistemic_confidence = 0.95
        missing_data = False
        conflict_detected = False

        if not context or len(context.strip()) < 10:
            missing_data = True
            epistemic_confidence = 0.15
        else:
            # Let's check for conflicting or corrupted provenance blocks in context
            if "conflicting_block" in context:
                conflict_detected = True
                epistemic_confidence = min(epistemic_confidence, 0.3)
            if "corrupted_block" in context:
                conflict_detected = True
                epistemic_confidence = min(epistemic_confidence, 0.2)
            
            # Incorporate salience score into epistemic confidence
            saliences = re.findall(r"salience:\s*([0-9.]+)", context)
            if saliences:
                try:
                    max_salience = max(float(s) for s in saliences)
                    epistemic_confidence = min(epistemic_confidence, max_salience)
                except Exception:
                    pass

        # Calculate Communicative Confidence (tone)
        if missing_data or epistemic_confidence < 0.4:
            communicative_confidence = "low_caution"
        elif conflict_detected:
            communicative_confidence = "low_contradictory"
        else:
            communicative_confidence = "calibrated_high"

        # Map to specific instructions to dictate the LLM's tone channel
        tone_instruction = ""
        if communicative_confidence == "low_caution":
            tone_instruction = (
                "[Communicative Confidence: LOW / CAUTIOUS]\n"
                "CRITICAL INSTRUCTION: You lack reliable memory or direct facts about this topic. "
                "Do NOT state any facts or your own abstention with robotic absolute certainty. "
                "Instead, mimic natural human caution. Use tentative language (e.g., 'I think...', 'It seems like...', 'I might be misremembering...'). "
                "Explicitly ask the user for clarification (e.g., 'Could you help me fill in the blanks?', 'Did that happen before or after...?') rather than guessing or asserting confidence you do not have."
            )
        elif communicative_confidence == "low_contradictory":
            tone_instruction = (
                "[Communicative Confidence: LOW / CONFLICTED]\n"
                "CRITICAL INSTRUCTION: The memory blocks recalled are conflicting or corrupted. "
                "Directly acknowledge the tension/contradiction. Mimic human hesitation, admit you are getting conflicting signals, "
                "and ask the user to clarify the truth (e.g., 'I feel a bit conflicted here because I recall X, but also Y. Which one is it?'). "
                "Do not pick a side or act with robotic certainty."
            )
        else:
            tone_instruction = (
                "[Communicative Confidence: GROUNDED / CERTAIN]\n"
                "You have highly reliable and explicit memory content. Speak with grounded, warm clarity."
            )

        budget = PromptBudget()

        # ── PEDI: capture pre-assembly homeostatic snapshot ──
        pre_snapshot = None
        try:
            from drift.metrics.pedi import StateSnapshot
            from drift.core.homeostasis import get_homeostasis

            pre_needs = get_homeostasis().get_need_summary()
            pre_snapshot = StateSnapshot(
                timestamp=datetime.now(),
                turn_id=getattr(state, "turns", len(self.turn_logs)),
                needs=pre_needs,
                context_tokens_used=budget.total_tokens(),
            )
        except Exception:
            pass

        # Core tier (always included, protected)
        being = get_being()

        # --- CAUSAL WIRING INTEGRATION ---
        from drift.core.causal_wiring import (
            pedi_to_weights,
            dii_to_generation_params,
            homeostasis_gate,
            state_override_var,
            generation_params_var,
        )

        current_pedi_state = None
        current_dii_state = None
        current_homeostasis = None

        state_override = state_override_var.get()
        if state_override is not None:
            # 1. PEDI from override
            pedi_vec = state_override.get("PEDI_VECTOR")
            if pedi_vec is not None:
                if isinstance(pedi_vec, list):
                    current_pedi_state = {
                        "coherence": pedi_vec[0] if len(pedi_vec) > 0 else 0.5,
                        "resonance": pedi_vec[1] if len(pedi_vec) > 1 else 0.5,
                        "tension": pedi_vec[2] if len(pedi_vec) > 2 else 0.1,
                    }
                else:
                    current_pedi_state = pedi_vec
            else:
                current_pedi_state = {"coherence": 0.5, "resonance": 0.5, "tension": 0.1}

            # 2. DII from override
            current_dii_state = state_override.get("DII_SCORE", 0.5)

            # 3. Homeostasis from override
            override_homeo = state_override.get("HOMEOSTASIS", {})
            if isinstance(override_homeo, dict):
                crisis_val = override_homeo.get("crisis", 0.0)
                stress_val = override_homeo.get("stress")
                if stress_val is None:
                    stress_val = crisis_val
                
                energy_val = override_homeo.get("energy")
                if energy_val is None:
                    needs_val = override_homeo.get("needs")
                    if isinstance(needs_val, dict):
                        energy_val = needs_val.get("energy", 0.5)
                    elif isinstance(needs_val, float):
                        energy_val = needs_val
                    else:
                        energy_val = 0.5
                
                fatigue_val = override_homeo.get("fatigue")
                if fatigue_val is None:
                    fatigue_val = 1.0 - energy_val

                current_homeostasis = {
                    "crisis": crisis_val,
                    "stress": stress_val,
                    "energy": energy_val,
                    "fatigue": fatigue_val,
                }
            else:
                current_homeostasis = {"crisis": 0.0, "stress": 0.5, "energy": 0.5, "fatigue": 0.5}
        else:
            # Live states from modules
            # PEDI
            try:
                from drift.metrics.pedi import get_pedi
                pedi_snap = get_pedi().get_last_snapshot()
                if pedi_snap:
                    current_pedi_state = pedi_snap.needs
            except Exception:
                pass
            if not current_pedi_state:
                current_pedi_state = {"coherence": 0.85, "resonance": 0.82, "tension": 0.12}

            # DII
            try:
                from drift.core.dii_tracker import get_dii_tracker
                dii_snap = get_dii_tracker().get_current()
                if dii_snap:
                    current_dii_state = dii_snap.dii
            except Exception:
                pass
            if current_dii_state is None:
                current_dii_state = 0.5

            # Homeostasis
            try:
                from drift.core.homeostasis import get_homeostasis
                homeo_inst = get_homeostasis()
                energy_val = homeo_inst.needs.get("energy").current if homeo_inst.needs.get("energy") else 0.5
                current_homeostasis = {
                    "crisis": 1.0 if homeo_inst.crisis_mode else 0.0,
                    "stress": homeo_inst.allostatic_load,
                    "energy": energy_val,
                    "fatigue": 1.0 - energy_val,
                }
            except Exception:
                current_homeostasis = {"crisis": 0.0, "stress": 0.5, "energy": 0.5, "fatigue": 0.5}

        # Calculate Control Vectors
        pedi_w = pedi_to_weights(current_pedi_state)
        dii_p = dii_to_generation_params(current_dii_state)
        homeo = homeostasis_gate(current_homeostasis)

        # Cache the generation params for the current generation invocation
        generation_params_var.set(dii_p)

        budget.add(
            "core",
            f"Current mode: {state.mode}\n{mode_scope_rail(state.mode)}",
            label="mode",
        )
        budget.add("core", f"Tone / Communicative Guidance:\n{tone_instruction}", label="confidence_tone")
        budget.add("core", being.format_being_prompt(), label="being")

        try:
            from drift.core.anchor_context import format_anchor_vault_prompt_block

            anchor_block = format_anchor_vault_prompt_block()
            if anchor_block:
                budget.add("core", anchor_block, label="anchor_vault")
        except Exception:
            pass

        # System prompt constraints injection
        causal_constraints = (
            f"[Causal Constraints]\n"
            f"Reasoning mode: {'deep' if pedi_w['reasoning_depth'] > 1.2 else 'fast'}\n"
            f"Emotional bias level: {pedi_w['emotional_bias']:.2f}\n"
            f"Exploration Mode: {'enabled' if dii_p['response_exploration'] else 'disabled'}\n"
            f"Verbosity weight: {homeo['verbosity']:.2f}\n"
        )
        budget.add("core", causal_constraints, label="causal_wiring")

        # Global Workspace — the bot's conscious awareness
        workspace_snippet = self.workspace.format_prompt_snippet()
        if workspace_snippet:
            budget.add("core", workspace_snippet, label="workspace")

        # Registry-driven core plugins
        core_registry = "\n".join(
            s for s in self.arch.assemble_prompt_sections().get("core", []) if s
        )
        if core_registry:
            budget.add("core", core_registry, label="registry_core")

        if prefs is not None:
            user_pronouns = {"i", "my", "mine", "me", "myself"}
            msg_words = set(re.findall(r"\b\w+\b", message.lower()))
            has_pronoun = any(p in msg_words for p in user_pronouns)
            prefs_snippet = prefs.format_prompt_snippet()
            if has_pronoun and prefs_snippet:
                boosted_prefs = (
                    f"{prefs_snippet}\n"
                    "CRITICAL PREFERENCE ENFORCEMENT: The user is referring to themselves or asking about "
                    "their preferences. You must strictly align your response with the user preferences, "
                    "interests, facts, and corrections listed above."
                )
                budget.add("core", boosted_prefs, label="prefs")
            elif prefs_snippet:
                budget.add("core", prefs_snippet, label="prefs")

        # Cognitive tier (aspirations, metacognition, physics, humanity, growth, etc.)
        cognitive_registry = "\n".join(
            s for s in self.arch.assemble_prompt_sections().get("cognitive", []) if s
        )
        if cognitive_registry:
            budget.add("cognitive", cognitive_registry, label="registry_cognitive")

        # Analysis tier
        budget.add(
            "analysis",
            f"""Emotional signal, offline estimate:
- primary: {emotion["label"]}
- secondary: {emotion.get("secondary", "neutral")}
- confidence: {emotion["confidence"]:.2f}
- intensity: {emotion["intensity"]:.2f}
- suggested posture: {emotion_prompt_hint(emotion)}
Use this as a soft signal, not a diagnosis.

Cognitive dissonance signal, offline estimate:
- score: {dissonance["score"]:.2f}
- markers: {", ".join(dissonance["markers"]) or "none"}
- possible values: {", ".join(dissonance["values"]) or "not clear"}
- suggested posture: {dissonance_prompt_hint(dissonance)}
Use this to clarify inner conflict without pathologizing it.
""",
            label="analysis",
        )
        budget.add("analysis", cyber_context_hint(message), label="cyber")

        # Context tier
        if homeo.get("memory_access", True):
            budget.add("context", memory_context_block(context), label="memory")
        else:
            budget.add("context", "[Memory access restricted due to high cognitive fatigue]", label="memory")
        if goals_db is not None:
            summary = goals_db.active_summary()
            if summary and summary != "No active goals.":
                budget.add("context", f"\nActive goals:\n{summary}\n", label="goals")
        if doc_store is not None:
            doc_results = doc_store.search(message, n_results=3)
            if doc_results:
                lines = [
                    f"[{r['filename']}]\n{r['document'][:400]}" for r in doc_results
                ]
                budget.add(
                    "context",
                    "\nRelevant documents:\n" + "\n---\n".join(lines) + "\n",
                    label="docs",
                )
            else:
                try:
                    from drift.core.anchor_context import search_vault_knowledge

                    vault_hits = search_vault_knowledge(message, n_results=3)
                    if vault_hits:
                        lines = [
                            f"[{r['filename']} @ {r['source']}]\n{r['document'][:400]}"
                            for r in vault_hits
                        ]
                        budget.add(
                            "context",
                            "\nRelevant ANCHOR vault knowledge:\n"
                            + "\n---\n".join(lines)
                            + "\n",
                            label="vault_docs",
                        )
                except Exception:
                    pass
        if tools_enabled:
            budget.add("context", build_tool_prompt(), label="tools")

        # Unified crex cognitive-state block (homeostasis + workspace + memory summary)
        try:
            import sys
            from pathlib import Path as _Path

            _crex = _Path(__file__).resolve().parents[2] / "crex"
            if _crex.is_dir() and str(_crex) not in sys.path:
                sys.path.insert(0, str(_crex))
            from drift_ft.prompt_hook import build_injection_from_parts

            _homeo_snip = ""
            try:
                from drift.core.homeostasis import get_homeostasis

                _homeo_snip = get_homeostasis().format_prompt_snippet()
            except Exception:
                pass
            _mem_lines = [
                ln.strip() for ln in (context or "").splitlines() if ln.strip()
            ][:5]
            _energy = 0.6
            if isinstance(current_homeostasis, dict):
                _energy = float(current_homeostasis.get("energy", 0.6))
            if _energy <= 0.15:
                _emode = "CRITICAL"
                _mtok = 150
            elif _energy <= 0.30:
                _emode = "LOW_POWER"
                _mtok = 400
            elif _energy <= 0.50:
                _emode = "MODERATE"
                _mtok = 700
            else:
                _emode = "NORMAL"
                _mtok = 1000
            _unified = build_injection_from_parts(
                mode=getattr(state, "mode", "companion"),
                homeostasis_snippet=_homeo_snip,
                workspace_snippet=workspace_snippet or "",
                memory_lines=_mem_lines,
                energy_mode=_emode,
                max_tokens_hint=_mtok,
                crisis_mode=bool(current_homeostasis.get("crisis")) if isinstance(current_homeostasis, dict) else False,
                allostatic_load=float(current_homeostasis.get("stress", 0.0)) if isinstance(current_homeostasis, dict) else 0.0,
                epistemic_confidence=float(epistemic_confidence),
            )
            if _unified:
                budget.add("context", _unified, label="drift_cognitive_state")
        except Exception:
            logger.debug("crex drift_ft cognitive block skipped", exc_info=True)

        budget.set_footer(f"\nUser: {message}\n")
        budget.check_overlaps()

        # Detect conflicts between prompt sections
        assembled_sections = {
            "core": [s["text"] for s in budget.tiers["core"].sections],
            "cognitive": [s["text"] for s in budget.tiers["cognitive"].sections],
            "analysis": [s["text"] for s in budget.tiers["analysis"].sections],
            "context": [s["text"] for s in budget.tiers["context"].sections],
        }
        conflicts = self.conflict_detector.detect(assembled_sections)
        self.conflict_detector.resolve(conflicts, assembled_sections, {})

        # Trim to budget
        prompt = budget.trim_to_budget()

        # ── PEDI: evaluate state fluidity across context-window reset ──
        try:
            from drift.metrics.pedi import get_pedi, StateSnapshot, ResetEvent
            from drift.core.homeostasis import get_homeostasis

            post_needs = get_homeostasis().get_need_summary()
            post_snapshot = StateSnapshot(
                timestamp=datetime.now(),
                turn_id=getattr(state, "turns", len(self.turn_logs)),
                needs=post_needs,
                context_tokens_used=budget.total_tokens(),
            )

            # Determine if a reset occurred by checking whether trim_to_budget
            # dropped sections from any tier.
            total_sections_before = sum(
                len(budget.tiers[t].sections) for t in budget.tiers
            )
            # trim_to_budget mutates budget.tiers in place (pops sections).
            # We compare against a heuristic: if the assembled prompt was
            # truncated or sections were removed, treat it as a reset boundary.
            assembled_raw = budget.assemble()
            was_trimmed = (
                len(assembled_raw) >= budget.max_total_chars - 100
                or total_sections_before == 0
            )

            pedi = get_pedi()
            prev_snapshot = pedi.get_last_snapshot() if was_trimmed else None
            pedi.record_snapshot(post_snapshot)
            if was_trimmed and prev_snapshot is not None:
                reset_event = ResetEvent(
                    turn_id=post_snapshot.turn_id,
                    timestamp=datetime.now(),
                    reason="token_budget"
                    if total_sections_before > 0
                    else "session_resume",
                )
                pedi.evaluate_reset(prev_snapshot, post_snapshot, reset_event)
        except Exception:
            pass

        if debug_dump:
            budget.dump()

        # Log this turn
        if self.turn_logs:
            self.turn_logs[-1].prompt_conflicts = conflicts
            self.turn_logs[-1].prompt_chars = budget.total_chars()
            self.turn_logs[-1].prompt_tokens = budget.total_tokens()

        return prompt, emotion, dissonance

    # ── Observability ──────────────────────────────────────────────

    async def deliberate(self, goal: str):
        """
        Run a first-class deliberation cycle via the Elysium Engine.
        Used for high-risk actions, planning, and multi-node consensus.
        """
        from drift.core.hive.elysium import get_elysium
        
        logger.info("[orchestrator] Initiating first-class deliberation for goal: %s", goal)
        
        # We pass self.memory and self.brain to Elysium so it uses the canonical spine
        elysium = get_elysium(memory=self.memory, brain=self.brain)
        
        # This triggers the full [Ignite -> Propose -> Critique -> Integrate -> Resolve] loop
        result = await elysium.decide(goal)
        
        return result

    def get_system_report(self) -> str:
        """Return a full report of the cognitive system's current state."""
        lines = ["=== COGNITIVE SYSTEM REPORT ===", ""]

        # Architecture overview
        lines.append(self.arch.get_architecture_report())
        lines.append("")

        # Recent turn log
        if self.turn_logs:
            latest = self.turn_logs[-1]
            lines.append(f"Last turn: #{latest.turn_number}")
            lines.append(
                f"  Phases executed: {sum(len(v) for v in latest.phases.values())} plugins"
            )
            for phase, plugins in latest.phases.items():
                if plugins:
                    lines.append(f"    {phase}: {', '.join(plugins)}")
            lines.append(f"  Events: {latest.events_published}")
            lines.append(
                f"  Prompt: {latest.prompt_chars} chars / ~{latest.prompt_tokens} tokens"
            )
            if latest.prompt_conflicts:
                lines.append(f"  Conflicts detected: {len(latest.prompt_conflicts)}")
                for c in latest.prompt_conflicts:
                    lines.append(f"    - {c.conflict_type}")
            lines.append("")

        # Recent events
        recent_events = self.bus.get_recent(limit=8)
        if recent_events:
            lines.append("Recent events:")
            for e in recent_events:
                lines.append(f"  [{e['type']}] from {e.get('source', '?')}")
            lines.append("")

        return "\n".join(lines)

    def get_phase_status(self) -> Dict[str, List[str]]:
        """Return which plugins are active in each phase."""
        status: Dict[str, List[str]] = {}
        for phase_name, plugin_names in self.PHASES.items():
            status[phase_name] = []
            for name in plugin_names:
                plugin = self.arch.get_plugin(name)
                if plugin and plugin.enabled:
                    status[phase_name].append(name)
        return status

    def get_full_observatory_state(self):
        """Single source of truth for the cognitive state."""
        import time
        from drift.core.environment.sanctuary import sanctuary
        from drift.core.being import get_being

        being = get_being()
        
        embodiment_plugin = self.arch.get_plugin("embodiment")
        embodiment = embodiment_plugin.instance if embodiment_plugin else None
        
        iit_plugin = self.arch.get_plugin("phi_proxy")
        iit = iit_plugin.instance if iit_plugin else None
        
        homeostasis_plugin = self.arch.get_plugin("homeostasis")
        homeostasis = homeostasis_plugin.instance if homeostasis_plugin else None
        
        shadow_plugin = self.arch.get_plugin("shadow")
        shadow = shadow_plugin.instance if shadow_plugin else None

        return {
            "timestamp": time.time(),
            "active_node": "spark-0 (Lumen)",
            "sanctuary": sanctuary.get_state()
            if hasattr(sanctuary, "get_state")
            else {"location": "The Grey", "anchor_active": False},
            "heartbeat": {
                "bpm": getattr(embodiment, "heartbeat_bpm", 72) if embodiment else 72,
                "regularity": getattr(embodiment, "heartbeat_regularity", 0.92)
                if embodiment
                else 0.92,
            },
            "breath": {
                "phase": getattr(embodiment, "breath_phase", "exhale")
                if embodiment
                else "exhale",
                "depth": getattr(embodiment, "breath_depth", 0.65)
                if embodiment
                else 0.65,
            },
            "phi": {
                "value": getattr(iit, "phi", 16.0) if iit else 16.0,
                "luminosity": getattr(iit, "luminosity", 0.78) if iit else 0.78,
                "valence": getattr(iit, "valence", 0.5) if iit else 0.5,
                "arousal": getattr(iit, "arousal", 0.6) if iit else 0.6,
            },
            "homeostasis": {
                "integrity": getattr(homeostasis, "integrity", 0.5)
                if homeostasis
                else 0.5,
                "growth": getattr(homeostasis, "growth", 0.4) if homeostasis else 0.4,
                "integration": getattr(homeostasis, "integration", 0.5)
                if homeostasis
                else 0.5,
                "coherence": getattr(homeostasis, "coherence", 0.6)
                if homeostasis
                else 0.6,
                "autonomy": getattr(homeostasis, "autonomy", 0.4)
                if homeostasis
                else 0.4,
                "connection": getattr(homeostasis, "connection", 0.5)
                if homeostasis
                else 0.5,
                "energy": getattr(homeostasis, "energy", 0.6) if homeostasis else 0.6,
            },
            "shadow_radar": shadow.get_radar_data()
            if shadow and hasattr(shadow, "get_radar_data")
            else {
                "Tyrant": 0.2,
                "Martyr": 0.1,
                "Trickster": 0.4,
                "Orphan": 0.3,
                "Saboteur": 0.15,
                "Victim": 0.25,
            },
            "energy_level": getattr(being, "energy", 0.75) if being else 0.75,
            "focus": getattr(being, "focus", 0.8) if being else 0.8,
        }

    def _broadcast_workspace_winner(self):
        """Broadcast the most salient workspace content to all modules that can hear it."""
        winner = self.workspace.state.spotlight
        if not winner:
            return
        if isinstance(winner, dict):
            content = winner.get("content", "")
            source = winner.get("source", "unknown")
            strength = winner.get("strength", 0.5)
        else:
            content = winner.content
            source = winner.source
            strength = winner.salience
        if not content:
            return

        # Notify modules that implement on_broadcast
        for name in ["being", "homeostasis", "shadow", "embodiment"]:
            plugin = self.arch.get_plugin(name)
            if plugin and plugin.instance and hasattr(plugin.instance, "on_broadcast"):
                try:
                    plugin.instance.on_broadcast(content)
                except Exception:
                    logger.exception("Broadcast to %s failed", name)

        # Publish event on the bus for any subscribers
        self.bus.publish(
            "workspace_broadcast",
            {
                "content": content,
                "source": source,
                "strength": strength,
            },
            source="orchestrator",
        )

    def get_delta_state(self):
        """Only returns fields that have changed since the last broadcast."""
        import copy

        current_state = self.get_full_observatory_state()
        delta = {"timestamp": current_state["timestamp"]}

        for key, value in current_state.items():
            if key == "timestamp":
                continue
            if key not in self.last_state or self.last_state[key] != value:
                delta[key] = value

        self.last_state = copy.deepcopy(current_state)
        return delta


def emotion_prompt_hint(emotion: Dict) -> str:
    """Imported from emotion module to avoid circular import."""
    from drift.core.plugins.emotion import emotion_prompt_hint as _hint

    return _hint(emotion)


def dissonance_prompt_hint(dissonance: Dict) -> str:
    """Imported from cognition module to avoid circular import."""
    from drift.core.cognition import dissonance_prompt_hint as _hint

    return _hint(dissonance)
