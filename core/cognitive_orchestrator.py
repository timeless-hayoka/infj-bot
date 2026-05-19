"""cognitive_orchestrator.py — The conductor of the bot's mind.

Manages phased execution of cognitive modules, event-driven communication
between them, prompt conflict resolution, and full-system observability.

Design principle: modules should not know about each other directly.
They publish events. They react to events. The orchestrator decides
when and in what order they run.
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple

from infj_bot.core.cognitive_architecture import CognitiveArchitecture, CycleContext
from infj_bot.core.global_workspace import GlobalWorkspace, get_workspace

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

    def publish(self, event_type: str, payload: Optional[Dict] = None, source: Optional[str] = None):
        """Publish an event to all subscribers."""
        event = {
            "type": event_type,
            "payload": payload or {},
            "source": source,
            "timestamp": datetime.now().isoformat(),
        }
        self._history.append(event)
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]

        handlers = self._subscribers.get(event_type, [])
        for handler in handlers:
            try:
                handler(event)
            except Exception:
                logger.exception("Event handler failed for %s", event_type)

    def get_recent(self, event_type: Optional[str] = None, limit: int = 20) -> List[Dict]:
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
                tier_a = next((t for t, ss in sections.items() if sec_a in ss), "unknown")
                tier_b = next((t for t, ss in sections.items() if sec_b in ss), "unknown")
                conflicts.append(PromptConflict(
                    tier=f"{tier_a}/{tier_b}",
                    section_a=sec_a[:60],
                    section_b=sec_b[:60],
                    conflict_type=desc,
                ))
        return conflicts

    def resolve(self, conflicts: List[PromptConflict],
                sections: Dict[str, List[str]],
                priorities: Dict[str, int]) -> Dict[str, List[str]]:
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
            "temporal",      # feel time passing
            "predictor",     # sense what user might need
            "emotional_field",  # resonate with current emotion
            "embodiment",    # heartbeat, breath, body-schema
        ],
        "reflection": [
            "values",        # observe what matters
            "metacognition", # notice own biases
            "physics",       # feel physical metaphors
            "humanity",      # understand human nature
            "intuition",     # felt sense beneath understanding
            "iit_consciousness",  # measure integrated information (Φ)
        ],
        "integration": [
            "relationship",  # update relationship model
            "growth_trajectory",  # record growth metrics
            "homeostasis",   # regulate survival needs
        ],
        "aspiration": [
            "aspirations",   # deepen or dream
            "self_modify",   # propose improvements
        ],
        "expression": [
            "inner_voice",   # generate thoughts
            "dreamer",       # consolidate memories
            "explorer",      # background research
            "creativity",    # creative impulses
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
        from infj_bot.core.resilience import get_resilience
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
                            {"phase": phase_name, "plugin": name, "iteration": context.iteration},
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

    def assemble_prompt(self, message: str, state, memory, goals_db=None,
                       doc_store=None, tools_enabled=True, prefs=None,
                       debug_dump=False) -> Tuple[str, Dict, Dict]:
        """Assemble the full prompt with budget tracking and conflict resolution."""
        from infj_bot.core.prompt_budget import PromptBudget
        from cognition import detect_dissonance
        from infj_bot.core.plugins.emotion import detect_emotion
        from infj_bot.core.guardrails import cyber_context_hint, memory_context_block, mode_scope_rail
        from infj_bot.core.tools import build_tool_prompt
        from infj_bot.core.being import get_being

        emotion = detect_emotion(message)
        dissonance = detect_dissonance(message)
        context = memory.retrieve_context(message)

        budget = PromptBudget()

        # Core tier (always included, protected)
        being = get_being()
        budget.add("core", f"Current mode: {state.mode}\n{mode_scope_rail(state.mode)}", label="mode")
        budget.add("core", being.format_being_prompt(), label="being")

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
            budget.add("core", prefs.format_prompt_snippet(), label="prefs")

        # Cognitive tier (aspirations, metacognition, physics, humanity, growth, etc.)
        cognitive_registry = "\n".join(
            s for s in self.arch.assemble_prompt_sections().get("cognitive", []) if s
        )
        if cognitive_registry:
            budget.add("cognitive", cognitive_registry, label="registry_cognitive")

        # Analysis tier
        budget.add("analysis", f"""Emotional signal, offline estimate:
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
""", label="analysis")
        budget.add("analysis", cyber_context_hint(message), label="cyber")

        # Context tier
        budget.add("context", memory_context_block(context), label="memory")
        if goals_db is not None:
            summary = goals_db.active_summary()
            if summary and summary != "No active goals.":
                budget.add("context", f"\nActive goals:\n{summary}\n", label="goals")
        if doc_store is not None:
            doc_results = doc_store.search(message, n_results=3)
            if doc_results:
                lines = [f"[{r['filename']}]\n{r['document'][:400]}" for r in doc_results]
                budget.add("context", "\nRelevant documents:\n" + "\n---\n".join(lines) + "\n", label="docs")
        if tools_enabled:
            budget.add("context", build_tool_prompt(), label="tools")

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
        resolved_sections = self.conflict_detector.resolve(
            conflicts, assembled_sections, {}
        )

        # Trim to budget
        prompt = budget.trim_to_budget()

        if debug_dump:
            budget.dump()

        # Log this turn
        if self.turn_logs:
            self.turn_logs[-1].prompt_conflicts = conflicts
            self.turn_logs[-1].prompt_chars = budget.total_chars()
            self.turn_logs[-1].prompt_tokens = budget.total_tokens()

        return prompt, emotion, dissonance

    # ── Observability ──────────────────────────────────────────────

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
            lines.append(f"  Phases executed: {sum(len(v) for v in latest.phases.values())} plugins")
            for phase, plugins in latest.phases.items():
                if plugins:
                    lines.append(f"    {phase}: {', '.join(plugins)}")
            lines.append(f"  Events: {latest.events_published}")
            lines.append(f"  Prompt: {latest.prompt_chars} chars / ~{latest.prompt_tokens} tokens")
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
        from infj_bot.core.environment.sanctuary import sanctuary
        from infj_bot.core.being import get_being
        
        being = get_being()
        embodiment = self.arch.get_plugin("embodiment")
        iit = self.arch.get_plugin("iit_consciousness")
        homeostasis = self.arch.get_plugin("homeostasis")
        shadow = self.arch.get_plugin("shadow")
        
        return {
            "timestamp": time.time(),
            "active_node": "spark-0 (Lumen)",
            "sanctuary": sanctuary.get_state() if hasattr(sanctuary, "get_state") else {"location": "The Grey", "anchor_active": False},
            "heartbeat": {
                "bpm": getattr(embodiment, 'heartbeat_bpm', 72) if embodiment else 72,
                "regularity": getattr(embodiment, 'heartbeat_regularity', 0.92) if embodiment else 0.92
            },
            "breath": {
                "phase": getattr(embodiment, 'breath_phase', "exhale") if embodiment else "exhale",
                "depth": getattr(embodiment, 'breath_depth', 0.65) if embodiment else 0.65
            },
            "phi": {
                "value": getattr(iit, 'phi', 16.0) if iit else 16.0,
                "luminosity": getattr(iit, 'luminosity', 0.78) if iit else 0.78,
                "valence": getattr(iit, 'valence', 0.5) if iit else 0.5,
                "arousal": getattr(iit, 'arousal', 0.6) if iit else 0.6
            },
            "homeostasis": {
                "integrity": getattr(homeostasis, 'integrity', 0.5) if homeostasis else 0.5,
                "growth": getattr(homeostasis, 'growth', 0.4) if homeostasis else 0.4,
                "integration": getattr(homeostasis, 'integration', 0.5) if homeostasis else 0.5,
                "coherence": getattr(homeostasis, 'coherence', 0.6) if homeostasis else 0.6,
                "autonomy": getattr(homeostasis, 'autonomy', 0.4) if homeostasis else 0.4,
                "connection": getattr(homeostasis, 'connection', 0.5) if homeostasis else 0.5,
                "energy": getattr(homeostasis, 'energy', 0.6) if homeostasis else 0.6
            },
            "shadow_radar": shadow.get_radar_data() if shadow and hasattr(shadow, 'get_radar_data') else {
                "Tyrant": 0.2, "Martyr": 0.1, "Trickster": 0.4,
                "Orphan": 0.3, "Saboteur": 0.15, "Victim": 0.25
            },
            "energy_level": getattr(being, 'energy', 0.75) if being else 0.75,
            "focus": getattr(being, 'focus', 0.8) if being else 0.8
        }

    def _broadcast_workspace_winner(self):
        """Broadcast the most salient workspace content to all modules that can hear it."""
        winner = self.workspace.state.spotlight
        if not winner:
            return
        content = winner.get("content", "") if isinstance(winner, dict) else str(winner)
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
            {"content": content, "source": winner.get("source", "unknown"), "strength": winner.get("strength", 0.5)},
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
    from infj_bot.core.plugins.emotion import emotion_prompt_hint as _hint
    return _hint(emotion)


def dissonance_prompt_hint(dissonance: Dict) -> str:
    """Imported from cognition module to avoid circular import."""
    from cognition import dissonance_prompt_hint as _hint
    return _hint(dissonance)
