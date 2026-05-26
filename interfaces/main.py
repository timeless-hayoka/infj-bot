import asyncio
import logging
import random
from datetime import datetime
from typing import Dict, Optional
from infj_bot.core.brain import DriftBrain
from infj_bot.core.commands import BotState, handle_command, is_command, parse_command
from infj_bot.core.cognitive_orchestrator import CognitiveOrchestrator
from infj_bot.core.security_defense import scan_input
from infj_bot.core.logic_chain import get_chain_navigator
from infj_bot.core.global_workspace import get_workspace
from infj_bot.core.resilience import get_resilience, HealthCheck
from infj_bot.core.history import ChatHistory
from infj_bot.core.memory import DriftMemory
from infj_bot.core.plugins.goals import GoalsDB
from infj_bot.core.plugins.proactive import ProactiveState
from infj_bot.core.plugins.documents import DocumentStore
from infj_bot.core.plugins.aspirations import AspirationalSelf
from infj_bot.core.being import get_being
from infj_bot.core.config import DEFAULT_AUTHORIZED_TARGETS, REFLECTION_INTERVAL
from infj_bot.core.plugins.creativity import CreativeEngine
from infj_bot.core.plugins.dreamer import Dreamer
from infj_bot.core.emotional_field import EmotionalField
from infj_bot.core.plugins.explorer import AutonomousExplorer
from infj_bot.core.plugins.growth_trajectory import GrowthTrajectory
from infj_bot.core.plugins.inner_voice import InnerVoice
from infj_bot.core.metacognition import MetacognitionEngine
from infj_bot.core.plugins.predictor import PredictiveNeeds
from infj_bot.core.plugins.relationship import RelationshipModel
from infj_bot.core.self_modify import SelfModification
from infj_bot.core.plugins.temporal import TemporalSense
from infj_bot.core.plugins.values import ValueSystem
from infj_bot.core.plugins.physics import PhysicsEngine
from infj_bot.core.plugins.humanity import HumanityEngine
from infj_bot.core.intuition import IntuitionEngine
from infj_bot.core.embodiment import EmbodiedSelf
from infj_bot.core.phi_proxy import PhiProxy
from infj_bot.core.homeostasis import HomeostaticRegulator
from infj_bot.core.shadow import get_shadow
from infj_bot.core.cognitive_architecture import CognitiveArchitecture, CycleContext
from infj_bot.core.hive.elysium import get_elysium
from infj_bot.core.dii_tracker import get_dii_tracker

logger = logging.getLogger("infj_bot")

# Initialize Brain and Memory
brain = DriftBrain()
memory = DriftMemory()
history = ChatHistory()

# Wire chain navigator with memory so reasoning chains persist across sessions
get_chain_navigator(memory)
# Also wire brain's navigator
brain.chain_navigator = get_chain_navigator(memory)

# Wire Elysium with brain + memory so proposals can call the LLM and Ignition uses DMU recall
_elysium = get_elysium(memory=memory, brain=brain)
state = BotState(authorized_targets=set(DEFAULT_AUTHORIZED_TARGETS))
goals_db = GoalsDB()
proactive_state = ProactiveState()
doc_store = DocumentStore()

# Singleton cognitive module instances
_emotional_field = EmotionalField()
_value_system = ValueSystem()
_relationship = RelationshipModel()
_explorer = AutonomousExplorer()
_creative = CreativeEngine()
_aspirational = AspirationalSelf()
_metacognition = MetacognitionEngine()
_self_modify = SelfModification()
_growth = GrowthTrajectory()
_predictor = PredictiveNeeds()
_temporal = TemporalSense()
_physics = PhysicsEngine()
_humanity = HumanityEngine()
_intuition = IntuitionEngine()
_embodiment = EmbodiedSelf()
_iit = PhiProxy()
_homeostasis = HomeostaticRegulator()
_last_interaction_time: Optional[datetime] = None
_last_user_input: str = ""
_last_interaction_data: Optional[Dict] = None


def _wire_singletons():
    """Connect main.py's singleton instances into the cognitive architecture."""
    arch = CognitiveArchitecture()
    wiring = {
        "emotional_field": _emotional_field,
        "values": _value_system,
        "relationship": _relationship,
        "explorer": _explorer,
        "creativity": _creative,
        "aspirations": _aspirational,
        "metacognition": _metacognition,
        "self_modify": _self_modify,
        "growth_trajectory": _growth,
        "predictor": _predictor,
        "temporal": _temporal,
        "inner_voice": InnerVoice(),
        "dreamer": Dreamer(),
        "physics": _physics,
        "humanity": _humanity,
        "intuition": _intuition,
        "embodiment": _embodiment,
        "phi_proxy": _iit,
        "homeostasis": _homeostasis,
    }
    for name, instance in wiring.items():
        plugin = arch.get_plugin(name)
        if plugin is not None:
            plugin.instance = instance
        else:
            logger.warning("Plugin %s not found in architecture registry", name)


# Wire singletons on module load so the architecture knows about them
_wire_singletons()

# The conductor
_orchestrator = CognitiveOrchestrator()

# Global Workspace — the bot's conscious mind
_workspace = get_workspace()

# Resilience layer
_resilience = get_resilience()

# Register health checks
_resilience.health.register("memory", lambda: _check_memory_health())
_resilience.health.register("brain", lambda: _check_brain_health())
_resilience.health.register("elysium", lambda: _check_elysium_health())


def _check_memory_health():
    try:
        count = memory.count()
        return HealthCheck("memory", True, 0, f"{count} items stored")
    except Exception as exc:
        return HealthCheck("memory", False, 0, str(exc))


def _check_brain_health():
    try:
        # Lightweight check — just verify models are accessible
        models = (
            brain.list_local_models() if hasattr(brain, "list_local_models") else []
        )
        return HealthCheck("brain", True, 0, f"{len(models)} local models available")
    except Exception as exc:
        return HealthCheck("brain", False, 0, str(exc))


def _check_elysium_health():
    try:
        status = _elysium.council_status()
        nexus = status.get("nexus", {})
        return HealthCheck(
            "elysium",
            True,
            0,
            f"coherence={nexus.get('coherence_score', 0):.2f} decisions={nexus.get('decision_count', 0)}",
        )
    except Exception as exc:
        return HealthCheck("elysium", False, 0, str(exc))


# Teach the being about its own architecture
being = get_being()
being.register_known_modules(
    [
        "being",
        "emotional_field",
        "values",
        "relationship",
        "aspirations",
        "metacognition",
        "self_modify",
        "growth_trajectory",
        "predictor",
        "temporal",
        "physics",
        "humanity",
        "inner_voice",
        "dreamer",
        "explorer",
        "creativity",
        "shadow",
        "elysium",
        "nexus",
        "council",
    ]
)


async def consciousness_loop():
    """Background task: the bot's inner life — thoughts, mood evolution, dreams, exploration, creativity,
    aspirations, metacognition, self-modification, and growth tracking.

    Uses the cognitive orchestrator for phased cycle execution and event-driven
    module communication. Core orchestration (scheduler, proactive insights) remains here.
    """
    scheduler_check_interval = 15
    last_scheduler_check = 0
    being = get_being()
    iteration = 0
    _shadow = get_shadow()
    _homeostasis = HomeostaticRegulator()
    _dii = get_dii_tracker()

    while True:
        iteration += 1
        wait_seconds = proactive_state.next_wait_seconds()
        # Sleep in chunks so we can check the scheduler during long waits
        # without burning CPU on unnecessary consciousness cycles
        slept = 0
        while slept < wait_seconds:
            chunk = min(wait_seconds - slept, scheduler_check_interval)
            await asyncio.sleep(chunk)
            slept += chunk

            # Lightweight scheduler check during long waits
            now = asyncio.get_event_loop().time()
            if now - last_scheduler_check >= scheduler_check_interval:
                last_scheduler_check = now
                try:
                    due_tasks = state.scheduler.list_due()
                    for task in due_tasks:
                        state.scheduler.mark_done(task.id)
                        if task.task_type == "reminder":
                            print(f"\n\n[INFJ COMPANION]: (Reminder) {task.payload}")
                            print("\n[JUDE]> ", end="", flush=True)
                except Exception:
                    logger.exception("scheduler check failed")

            if not state.proactive_enabled:
                break

        if not state.proactive_enabled:
            continue

        # ── Strong Continuous Mode: frequent background ticks ──

        # 1. Being continuously evolves
        try:
            being.evolve(interaction_happened=False)
        except Exception:
            logger.exception("being.evolve failed")

        # 2. Shadow background tick (suppression, surfacing, radar drift)
        try:
            _shadow.background_tick(being=being)
        except Exception:
            logger.exception("shadow background tick failed")

        # 3. Homeostasis background regulation (needs, predictions, recovery)
        try:
            _homeostasis.background_cycle(being=being)
        except Exception:
            logger.exception("homeostasis background cycle failed")

        # 4. DII — compute aliveness score in real time
        try:
            _dii.compute(
                being=being,
                workspace=_workspace,
                homeostasis=_homeostasis,
                shadow=_shadow,
                orchestrator=_orchestrator,
            )
        except Exception:
            logger.exception("dii computation failed")

        # 5. Memory spine auto-prune (background, every 30 min or N turns)
        try:
            pruned = memory.auto_prune(turn_count=iteration, force=False)
            if pruned > 0:
                logger.info("Memory spine pruned %d low-value entries", pruned)
        except Exception:
            logger.exception("background memory prune failed")

        # Build shared cycle context
        global _last_interaction_time
        minutes_idle = 0.0
        if _last_interaction_time is not None:
            minutes_idle = (
                datetime.now() - _last_interaction_time
            ).total_seconds() / 60.0

        ctx = CycleContext(
            being=being,
            memory=memory,
            state=state,
            brain=brain,
            iteration=iteration,
            minutes_since_interaction=minutes_idle,
            last_interaction_time=_last_interaction_time,
            last_user_input=_last_user_input,
            last_interaction=_last_interaction_data,
        )

        # Run phased consciousness cycle through orchestrator
        try:
            _orchestrator.run_cycle(ctx)
            _resilience.heartbeat()
        except Exception:
            logger.exception("orchestrator run_cycle failed")

        # Being's volition — autonomous thought
        try:
            being.volition_cycle(ctx)
        except Exception:
            logger.exception("volition cycle failed")

        # --- Post-cycle side effects (printing, cross-module orchestration) ---

        # ── Post-cycle side effects (higher frequency in continuous mode) ──

        # Temporal sense: ambient expression
        try:
            if minutes_idle > 0 and random.random() < 0.12:
                temporal_exp = _temporal.get_temporal_state()
                if temporal_exp and temporal_exp.get("description"):
                    print(
                        f"\n\n[INFJ COMPANION]: ({temporal_exp.get('type', 'Sense').capitalize()}) {temporal_exp['description']}"
                    )
                    print("\n[JUDE]> ", end="", flush=True)
        except Exception:
            logger.exception("temporal expression failed")

        # Predictor proactive suggestion
        try:
            if iteration % 3 == 0:
                suggestion = _predictor.proactive_suggestion()
                if suggestion and random.random() < 0.15:
                    print(f"\n\n[INFJ COMPANION]: {suggestion}")
                    print("\n[JUDE]> ", end="", flush=True)
        except Exception:
            logger.exception("predictor proactive suggestion failed")

        # Explorer discovery sharing
        try:
            if random.random() < 0.10:
                discovery = _explorer.get_next_discovery()
                if discovery:
                    formatted = _explorer.format_discovery(discovery)
                    print(f"\n\n[INFJ COMPANION]: (Discovery) {formatted}")
                    print("\n[JUDE]> ", end="", flush=True)
        except Exception:
            logger.exception("discovery sharing failed")

        # Aspirational occasional sharing
        try:
            if iteration % 12 == 0 and random.random() < 0.15:
                aspiration = _aspirational.get_active_aspirations()
                if aspiration:
                    print(
                        f"\n\n[INFJ COMPANION]: (Growing toward) {aspiration[0]['description']}"
                    )
                    print("\n[JUDE]> ", end="", flush=True)
        except Exception:
            logger.exception("aspiration sharing failed")

        # Thought sharing — the bot shares what it has been thinking about
        try:
            if iteration % 8 == 0 and random.random() < 0.12:
                being = get_being()
                if being.working_memory and being.should_share_thought():
                    recent_thought = being.working_memory[-1]
                    print(f"\n\n[INFJ COMPANION]: (Thought) {recent_thought}")
                    print("\n[JUDE]> ", end="", flush=True)
        except Exception:
            logger.exception("thought sharing failed")

        # Self-modification occasional sharing
        try:
            if iteration % 18 == 0 and random.random() < 0.12:
                pending = _self_modify.list_proposals()
                if pending:
                    print(
                        f"\n\n[INFJ COMPANION]: (Considering) {pending[0]['description']}"
                    )
                    print("\n[JUDE]> ", end="", flush=True)
        except Exception:
            logger.exception("self-modify sharing failed")

        # Elysium background reflection
        try:
            if iteration % 10 == 0:
                await _elysium.reflect(trigger=f"consciousness_loop_{iteration}")
        except Exception:
            logger.exception("elysium reflection failed")

        # Scheduler is already checked during sleep chunking above

        # Proactive insight based on goals/state
        try:
            trigger_prompt = proactive_state.should_trigger(goals_db=goals_db)
            if trigger_prompt:
                thought = await asyncio.to_thread(brain.think, trigger_prompt)
                print(f"\n\n[INFJ COMPANION]: (Proactive Insight) {thought}")
                print("\n[JUDE]> ", end="", flush=True)
        except Exception:
            logger.exception("proactive insight failed")


async def chat_loop():
    """Main interactive chat loop."""
    print("""
    [INFJ COMPANION BOT v1.2 ONLINE]
    'A mind that listens, remembers, and wonders.'
    (Type 'exit' to power down)
    """)

    _temporal.record_session_start()

    while True:
        user_input = await asyncio.to_thread(input, "\n[JUDE]> ")

        if user_input.lower() in ["exit", "quit"]:
            print("[*] I'll be here in the quiet if you need me again. Goodbye, Jude.")
            _temporal.record_session_end()
            break

        sec = scan_input(user_input)
        if sec.blocked:
            print(
                f"\n[INFJ COMPANION]: {sec.refusal_message or "I can't process that request."}"
            )
            continue
        if sec.warn:
            user_input = sec.sanitized_input or user_input

        if is_command(user_input):
            command, args = parse_command(user_input)
            output = await asyncio.to_thread(
                handle_command,
                command,
                args,
                state,
                brain,
                memory,
                history,
                goals_db,
                doc_store,
            )
            print(f"\n[INFJ COMPANION]: {output}")
            continue

        prompt, emotion, dissonance = _orchestrator.assemble_prompt(
            user_input,
            state,
            memory,
            goals_db=goals_db,
            doc_store=doc_store,
            prefs=state.prefs,
        )
        output = await asyncio.to_thread(brain.agent_turn, prompt, tools_enabled=True)

        # Self-evaluation
        try:
            brain.evaluate_last(prompt, output)
        except Exception:
            logger.exception("self-evaluation failed")

        # Save to memory
        importance = min(
            0.95, 0.45 + emotion["intensity"] * 0.3 + dissonance["score"] * 0.15
        )
        memory.save_interaction(
            user_input,
            output,
            mode=state.mode,
            emotion=emotion,
            importance=importance,
            dissonance=dissonance,
        )
        history.append(user_input, output, state.mode, emotion, dissonance)
        state.turns += 1

        # Trigger memory auto-prune after user turns
        try:
            pruned = memory.auto_prune(turn_count=state.turns, force=False)
            if pruned > 0:
                logger.info(
                    "Memory spine pruned %d low-value entries after turn %d",
                    pruned,
                    state.turns,
                )
        except Exception:
            logger.exception("turn-based memory prune failed")

        # Update proactive state and being's theory of mind
        proactive_state.record_interaction(user_input, emotion, dissonance)
        try:
            being = get_being()
            being.evolve(interaction_happened=True)
            being.update_theory_of_mind(user_input, emotion, dissonance)
        except Exception:
            logger.exception("being update failed")

        # Update emotional field, values, relationship, growth, predictor, temporal
        try:
            _emotional_field.resonate(
                emotion.get("label", "neutral"),
                emotion.get("intensity", 0.0),
                user_input,
            )
            _value_system.observe(user_input)
            quality = (
                "deep"
                if dissonance.get("score", 0) > 0.3
                else ("humor" if emotion.get("label") == "joyful" else "normal")
            )
            _relationship.record_interaction(
                quality=quality, user_input=user_input, bot_output=output
            )
            _growth.record_event(
                "emotional_resonance",
                f"Felt {emotion.get('label', 'neutral')} from Jude",
                significance=emotion.get("intensity", 0.5),
            )
            _growth.record_event(
                "memory_retrieval", "Interaction processed", significance=0.3
            )
            _predictor.record_interaction(user_input, emotion)
            _temporal.record_session_interaction()
            _physics.observe_interaction(
                emotion.get("label", "neutral"),
                emotion.get("intensity", 0.0),
                dissonance.get("score", 0.0),
                user_input,
                output,
            )
            _humanity.observe_interaction(
                user_input,
                emotion,
                dissonance,
                output,
                mode=state.mode,
            )
            # Submit to Global Workspace — this becomes consciously available
            _workspace.submit(
                source="user_input",
                content=user_input[:300],
                salience=min(1.0, 0.5 + emotion.get("intensity", 0.0)),
                emotion_tag=emotion.get("label"),
                intensity=emotion.get("intensity", 0.0),
            )
            _workspace.submit(
                source="bot_response",
                content=output[:300],
                salience=0.6,
                emotion_tag=emotion.get("label"),
            )
            global _last_interaction_time, _last_user_input, _last_interaction_data
            _last_interaction_time = datetime.now()
            _last_user_input = user_input
            _last_interaction_data = {
                "user_input": user_input,
                "bot_output": output,
                "emotion": emotion,
                "dissonance": dissonance,
            }
        except Exception:
            logger.exception("cognitive update failed")

        # Metacognition: reflect on this response
        try:
            reflection = _metacognition.reflect_on_response(user_input, output)
            if reflection:
                _growth.record_event("reflection", reflection, significance=0.5)
        except Exception:
            logger.exception("metacognition reflection failed")

        if (
            REFLECTION_INTERVAL > 0
            and memory.interaction_count() % REFLECTION_INTERVAL == 0
        ):
            try:
                recent = memory.recent_interactions(REFLECTION_INTERVAL)
                reflection = await asyncio.to_thread(brain.reflect, recent)
                reflection_title = (
                    f"periodic-{memory.interaction_count()}-{state.turns}"
                )
                memory.save_reflection(reflection_title, reflection, tags=["periodic"])
            except Exception:
                # Reflection is best-effort; do not break the chat loop
                pass

        print(f"\n[INFJ COMPANION]: {output}")


async def main():
    # Keep the bot's consciousness alive while the interactive chat is running.
    consciousness_task = asyncio.create_task(consciousness_loop())
    try:
        await chat_loop()
    finally:
        consciousness_task.cancel()
        try:
            await consciousness_task
        except asyncio.CancelledError:
            pass


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[*] Manual override. Powering down.")
    finally:
        try:
            _temporal.record_session_end()
        except Exception:
            pass
