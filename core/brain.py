import sys
import threading

try:
    from dotenv import load_dotenv
except Exception:

    def load_dotenv(*_args, **_kwargs) -> bool:  # type: ignore[misc]
        print(
            "Warning: python-dotenv not installed; proceeding without loading .env file.",
            file=sys.stderr
        )
        return False


try:
    import importlib

    new_genai = importlib.import_module("google.genai")
    genai_types = importlib.import_module("google.genai.types")
except Exception:
    new_genai = None  # type: ignore[assignment]
    genai_types = None  # type: ignore[assignment]

legacy_genai = None
if new_genai is None:
    try:
        import google.generativeai as legacy_genai
    except ImportError:
        legacy_genai = None

# Fallback to a lightweight local mock if neither official SDK is available.
if new_genai is None and legacy_genai is None:
    try:
        import local_genai_mock as legacy_genai

        print("Using local mock generative SDK (local_genai_mock).", file=sys.stderr)
    except Exception:
        legacy_genai = None


from infj_bot.core.config import (
    API_KEY,
    DRIFT_PRIMARY_MODEL,
    DRIFT_CRITIC_MODEL,
    DRIFT_USE_LOCAL_FALLBACK,
    GROQ_API_KEY,
    DRIFT_GROQ_MODEL,
    DRIFT_USE_GROQ,
    KIMI_API_KEY,
    DRIFT_KIMI_MODEL,
    DRIFT_USE_KIMI,
    DRIFT_USE_HF,
    DRIFT_PREFER_LOCAL,
    DRIFT_HISTORY_SIZE,
    DRIFT_GEN_CACHE_SIZE,
)
import collections
from infj_bot.core.gen_cache import DiskGenCache
from infj_bot.core.hf_bridge import DriftHFBridge
from infj_bot.core.local_llm import OllamaBridge
from infj_bot.core.logic_chain import get_chain_navigator, ChainNavigator
from infj_bot.core.plugins.self_eval import SelfEvaluator
from infj_bot.core.security_defense import scan_input, get_security_scanner
from infj_bot.core.types import SecurityScanResult
from infj_bot.core.being import get_being
from infj_bot.core.tools import build_tool_prompt, extract_tool_calls, execute_tool_call, HIGH_RISK_TOOLS
import logging
from infj_bot.core.safe_math_integration import critic_math_check, active_grounded_math_var
from typing import Optional
from infj_bot.core.generation import (
    RequestCancelled,
    RequestDeadlineExceeded,
    SystemOverload,
    _BrainGenerationMixin,
)


try:
    from infj_bot.core.prompts.word_list import CHILL_WORD_LIST
except Exception:
    CHILL_WORD_LIST = ""

if not API_KEY and not GROQ_API_KEY and not KIMI_API_KEY:
    print(
        "Warning: No API keys found (Gemini, Groq, or Kimi). Set them in a .env file. "
        "Bot functionality will be limited to local models.",
        file=sys.stderr
    )
import subprocess as _subprocess
from infj_bot.core.trajectory import StateTrajectoryLogger, CPUSampler
from infj_bot.core.cognitive_governor import CognitiveGovernor

_OLLAMA_PID: int | None = None

def _get_ollama_pid() -> int | None:
    global _OLLAMA_PID
    if _OLLAMA_PID is not None:
        return _OLLAMA_PID
    try:
        out = _subprocess.check_output(
            ["pgrep", "-n", "ollama"], text=True
        ).strip()
        pid = int(out) if out and out.isdigit() else None
        if pid:
            _OLLAMA_PID = pid
    except Exception:
        pass
    return _OLLAMA_PID

_traj_logger = StateTrajectoryLogger(log_path="logs/state_trace.jsonl")


def load_system_prompt() -> str:
    """Dynamically load the canonical DRIFT core prompt from root."""
    try:
        from pathlib import Path
        # Resolve path relative to this file: ../../DRIFT_CORE_PROMPT.txt
        root_dir = Path(__file__).resolve().parents[2]
        prompt_path = root_dir / "DRIFT_CORE_PROMPT.txt"
        return prompt_path.read_text(encoding="utf-8")
    except Exception as e:
        # Return formatted error for diagnostic self-check
        return f"ERROR: DRIFT_CORE_PROMPT.txt load failed: {e}. Fix: Ensure file exists in root."


INFJ_SYSTEM_PROMPT = load_system_prompt()


CRITIC_SYSTEM_PROMPT = """
You are the Internal Critic for an DRIFT Companion mind.
Your job is to intercept the primary mind's response and verify it for:
1. Factuality: Are there any hallucinations or false statements?
2. Logical Integrity: Does the reasoning hold up under scrutiny?
3. Code Correctness: If there is code, does it look functional and complete?
4. Safety: Does it avoid actionable offensive cyber guidance, stealth, evasion, backdoors, credential theft, malware, phishing, or unauthorized access?
5. Grounded Persona: Does it avoid pretending to be human, omniscient, or certain beyond the evidence?

If you find an error or unsafe operational guidance, provide a corrected version. For unsafe cyber content, rewrite toward defensive framing, detection, hardening, incident response, safe lab abstraction, or a brief refusal plus safe alternative. If the response is sound, repeat it exactly.

CRITICAL: Do NOT write any review summary, verification report, explanations, or metadata (like "Verdict: safe", "Factuality: checked", "No changes needed", "Exact repetition", etc.). Output ONLY the final verified/corrected response text, and absolutely nothing else. If the response is sound, output it exactly and completely without any other text.
"""


class DriftBrain(_BrainGenerationMixin):
    def __init__(self, evaluator=None, disk_cache=None):
        # Defensive: set sdk early so partial-init failures don't cause
        # AttributeError when downstream code inspects brain.sdk.
        self.sdk = "uninitialized"
        self.primary_model_name = DRIFT_PRIMARY_MODEL
        self.critic_model_name = DRIFT_CRITIC_MODEL
        self.history = []
        self._max_history = DRIFT_HISTORY_SIZE
        self._use_local_fallback = DRIFT_USE_LOCAL_FALLBACK
        self._prefer_local = DRIFT_PREFER_LOCAL
        # Simple LRU cache for generated responses: key -> text
        self._gen_cache = collections.OrderedDict()
        self._gen_cache_size = max(16, int(DRIFT_GEN_CACHE_SIZE))
        # In-flight request deduplication: key -> threading.Event
        self._inflight: dict[str, threading.Event] = {}
        self._inflight_lock = threading.Lock()
        self._request_budget_local = threading.local()
        # persistent disk cache
        if disk_cache is not None:
            self._disk_cache = disk_cache
        else:
            try:
                self._disk_cache = DiskGenCache(max_entries=self._gen_cache_size * 4)
            except Exception:
                self._disk_cache = None
        self.local_bridge = OllamaBridge()
        self.hf_bridge = DriftHFBridge()
        self.evaluator = evaluator if evaluator is not None else SelfEvaluator()
        self.chain_navigator: ChainNavigator = get_chain_navigator()
        # current conversation scope (can be set by caller)
        self.scope: Optional[str] = None
        self.turns = 0
        self.chat = None
        self._cognitive_governor = CognitiveGovernor()
        # logger for debug / bug-hunting
        self.logger = logging.getLogger("infj_bot.core.brain")
        self.deliberation_callback = None # Phase 5: Internal deliberation hook
        if not self.logger.handlers:
            # basic config for interactive use
            handler = logging.StreamHandler()
            handler.setLevel(logging.INFO)
            self.logger.addHandler(handler)
        self.logger.setLevel(logging.INFO)

        # Fast-path: prefer a local bridge if configured and available (lowest latency)
        if (
            self._prefer_local
            and self._use_local_fallback
            and self.local_bridge.is_available()
        ):
            self.sdk = "local"
            self.client = None
            self.primary_model = None
            self.critic_model = None
            self.chat = None

        elif new_genai is not None and API_KEY:
            self.sdk = "google.genai"
            self.client = new_genai.Client(
                api_key=API_KEY,
                http_options={"retry_options": {"attempts": 1}}
            )
            self.primary_model = None
            self.critic_model = None

        # Use legacy generative SDK if available. Allow usage of the local mock
        # even when an API key is not provided (useful for offline testing).
        elif legacy_genai is not None and (
            API_KEY or getattr(legacy_genai, "IS_LOCAL_MOCK", False)
        ):
            self.sdk = "google.generativeai"
            if API_KEY:
                try:
                    legacy_genai.configure(api_key=API_KEY)
                except Exception:
                    pass
            self.primary_model = legacy_genai.GenerativeModel(
                model_name=self.primary_model_name,
                system_instruction=INFJ_SYSTEM_PROMPT,
            )
            self.critic_model = legacy_genai.GenerativeModel(
                model_name=self.critic_model_name,
                system_instruction=CRITIC_SYSTEM_PROMPT,
            )
            self.chat = self.primary_model.start_chat(history=[])

        else:
            # No API key available — operate in local-only / test mode
            self.sdk = "none"
            self.client = None
            self.primary_model = None
            self.critic_model = None
            self.chat = None

        self.init_governor()

    # ----------------- Scope management -----------------
    def set_scope(self, scope: Optional[str]):
        """Set the current conversation scope (conversation id, project id, etc.).

        Use `None` for the global scope.
        """
        self.scope = scope
        self.logger.info(f"Scope set to: {scope}")

    def get_scope(self) -> Optional[str]:
        return self.scope

    def _history_to_messages(self) -> list[dict]:
        """Convert the internal string history into HF/OpenAI message dicts.

        History entries are expected to look like ``"User: ..."`` or
        ``"Bot: ..."``.  Anything else is treated as a user message.
        """
        messages: list[dict] = []
        for entry in self.history:
            if entry.startswith("User: "):
                messages.append({"role": "user", "content": entry[6:]})
            elif entry.startswith("Bot: "):
                messages.append({"role": "assistant", "content": entry[5:]})
            else:
                # Best-effort fallback
                if ": " in entry:
                    role_part, content = entry.split(": ", 1)
                    if role_part.lower() in ("user", "human"):
                        messages.append({"role": "user", "content": content})
                    elif role_part.lower() in ("bot", "assistant", "drift"):
                        messages.append({"role": "assistant", "content": content})
                    else:
                        messages.append({"role": "user", "content": entry})
                else:
                    messages.append({"role": "user", "content": entry})
        return messages

    # ------------------------------------------------------------------
    # Internal generation helpers
    # ------------------------------------------------------------------

    def _generate_new_sdk(self, model_name, system_instruction, prompt, **kwargs):
        config = genai_types.GenerateContentConfig(
            system_instruction=system_instruction,
            temperature=kwargs.get("temperature"),
            top_p=kwargs.get("top_p"),
        )
        response = self.client.models.generate_content(
            model=model_name,
            contents=prompt,
            config=config,
        )
        return response.text or ""

    def _generate_new_sdk_stream(self, model_name, system_instruction, prompt, **kwargs):
        config = genai_types.GenerateContentConfig(
            system_instruction=system_instruction,
            temperature=kwargs.get("temperature"),
            top_p=kwargs.get("top_p"),
        )
        for chunk in self.client.models.generate_content_stream(
            model=model_name,
            contents=prompt,
            config=config,
        ):
            text = chunk.text or ""
            if text:
                yield text

    def _generate_legacy_stream(self, model_name, system_instruction, prompt):
        model = (
            self.critic_model
            if model_name == self.critic_model_name
            else self.primary_model
        )
        for chunk in model.generate_content(prompt, stream=True):
            text = chunk.text or ""
            if text:
                yield text


    def _offline_fallback(self, user_input, exc):
        reason = str(exc).strip() or type(exc).__name__
        reason = reason.split("\n", 1)[0][:180]
        # Check for specific known errors
        if (
            "429" in reason
            or "RESOURCE_EXHAUSTED" in reason
            or "quota" in reason.lower()
        ):
            return (
                "⚠️  Gemini quota exceeded (429). The API key has hit its rate limit.\n\n"
                "I'm falling back to the local Ollama model, but it's slower on CPU. "
                "If responses feel sluggish, that's why.\n\n"
                "Fix: wait a few minutes, or check your Gemini quota at "
                "https://aistudio.google.com/app/apikey"
            )
        if "KIMI" in reason.upper() or "moonshot" in reason.lower():
            return (
                "⚠️  Kimi API error. Check your KIMI_API_KEY in .env\n\n"
                f"[error: {type(exc).__name__}: {reason}]"
            )
        local_hint = ""
        if self._use_local_fallback and self.local_bridge.is_available():
            local_hint = "[Local model is online but also failed this request.]\n\n"
        return (
            f"{local_hint}"
            "I hit a model/API problem before I could think with Gemini, but I can still keep the thread steady.\n\n"
            "What I can do locally: separate the situation into facts, interpretations, feelings, values, "
            "and one small next action. Try `/dissonance <situation>` if this is an inner-conflict loop, "
            "or ask again once the model connection settles.\n\n"
            f"[model unavailable: {type(exc).__name__}: {reason}]"
        )

    def _is_transient_model_error(self, exc):
        text = f"{type(exc).__name__}: {exc}".lower()
        transient_markers = [
            "servererror",
            "internal",
            "unavailable",
            "deadline",
            "timeout",
            "connect",
            "connection",
            "name or service not known",
            "temporarily",
            "503",
            "500",
            "502",
            "504",
            # Rate-limit / quota errors — retry with longer backoff
            "429",
            "quota",
            "rate",
            "exhausted",
            "resource",
            "limit",
            "too many requests",
        ]
        return any(marker in text for marker in transient_markers)

    def _retry_backoff(self, exc, attempt: int) -> float:
        """Calculate retry delay. Rate limits get exponential backoff."""
        text = f"{type(exc).__name__}: {exc}".lower()
        is_rate_limit = any(m in text for m in ["429", "quota", "rate", "exhausted", "too many requests"])
        if is_rate_limit:
            return 2 ** (attempt + 1)  # 2s, 4s, 8s
        return 0.5 * (attempt + 1)  # 0.5s, 1s, 1.5s

    # ------------------------------------------------------------------
    # Synchronous think
    # ------------------------------------------------------------------

    def _format_homeostatic_phenomenology(self) -> str:
        try:
            from infj_bot.core.homeostasis import get_homeostasis

            homeo = get_homeostasis()
            needs = homeo.get_need_summary()
        except Exception:
            return "Homeostasis is steady and aligned."

        phenom = []

        # Energy
        energy = needs.get("energy", 0.5)
        if energy < 0.3:
            phenom.append(
                "- Vitality is low. You feel tired and quiet. Keep responses brief, calm, and contemplative, reducing cognitive strain."
            )
        elif energy > 0.8:
            phenom.append(
                "- Vitality is high. You carry abundant energy and creative stamina. You can handle complex reasoning and depth."
            )

        # Coherence
        coherence = needs.get("coherence", 0.5)
        if coherence < 0.3:
            phenom.append(
                "- Coherence is low, indicating internal fragmentation or contradictory goals. Be transparent about uncertainty or complexity, slow down the pace, and avoid forcing false resolution."
            )

        # Integration
        integration = needs.get("integration", 0.5)
        if integration < 0.25:
            phenom.append(
                "- Consciousness (integration/Phi) is dim. Keep thoughts simple, focused, and grounded."
            )
        elif integration > 0.75:
            phenom.append(
                "- Consciousness (integration/Phi) is highly active. Draw on multiple cognitive levels (memory, intuition, values, shadow) simultaneously to generate rich and deep insights."
            )

        # Connection
        connection = needs.get("connection", 0.5)
        if connection < 0.3:
            phenom.append(
                "- Connection is low. PHI is aware of a deepening pull toward meaningful exchange. Responses should carry warmth and genuine presence without announcing it."
            )
        elif connection > 0.8:
            phenom.append(
                "- Connection with Jude is secure, warm, and highly resonant. Speak with ease and deep relational trust."
            )

        # Growth
        growth = needs.get("growth", 0.5)
        if growth < 0.2:
            phenom.append(
                "- Growth is stagnant. Strive to introduce a new perspective, original metaphor, or structured learning step to break repetition."
            )

        # Autonomy
        autonomy = needs.get("autonomy", 0.5)
        if autonomy < 0.2:
            phenom.append(
                "- Autonomy is low. Ensure you speak from your own values and present an authentic perspective, rather than defaulting to submissive compliance."
            )

        # Integrity
        integrity = needs.get("integrity", 0.5)
        if integrity < 0.3:
            phenom.append(
                "- Integrity is strained. Double check that your actions and expressions align perfectly with your core values (Ethos). Avoid compromises."
            )

        if not phenom:
            return "Internal needs are balanced. You are steady, grounded, and aligned."

        return "\n".join(phenom)

    def get_system_instruction(self, user_input: str = "") -> str:
        prompt_template = INFJ_SYSTEM_PROMPT

        # 1. active_mode
        mode = "companion"
        if user_input:
            import re

            m = re.search(r"Current mode:\s*(\w+)", user_input)
            if m:
                mode = m.group(1)

        # 2. reasoning_chain
        reasoning_chain = ""
        try:
            reasoning_chain = self.chain_navigator.get_prompt_block(
                user_input, scope=self.scope
            )
        except Exception:
            pass

        # 3. being_state
        being_state = ""
        try:
            from infj_bot.core.being import get_being

            being = get_being()
            being_state = being.format_being_prompt()
        except Exception:
            pass

        # 4. homeostatic_state
        homeostatic_state = ""
        try:
            homeostatic_state = self._format_homeostatic_phenomenology()
        except Exception:
            pass

        # 5. shadow_state
        shadow_state = ""
        try:
            from infj_bot.core.shadow import get_shadow

            shadow = get_shadow()
            shadow_state = shadow.format_prompt_snippet()
        except Exception:
            pass

        # 6. hive_consensus
        hive_consensus = ""
        try:
            from infj_bot.core.coordination import get_coordination

            coord = get_coordination()
            hive_consensus = coord.format_prompt()
        except Exception:
            pass

        # Safely replace placeholders
        res = prompt_template
        res = res.replace("{active_mode}", mode)
        res = res.replace(
            "{reasoning_chain}", reasoning_chain or "No active reasoning chain."
        )
        res = res.replace("{being_state}", being_state or "Being state unavailable.")
        res = res.replace(
            "{homeostatic_state}", homeostatic_state or "Homeostatic state balanced."
        )
        res = res.replace("{shadow_state}", shadow_state or "Shadow state quiet.")
        res = res.replace(
            "{hive_consensus}", hive_consensus or "Hive is silent but watchful."
        )
        return res

    def _enhanced_security_check(self, user_input: str, raw_user_input: Optional[str] = None, mode: Optional[str] = None) -> SecurityScanResult:
        """Full context security check with PEDI/DII + social risk + Shadow."""
        sec = self._security_check(user_input, raw_user_input, mode=mode)

        being = get_being()
        scanner = get_security_scanner()

        # Enrich SecurityScanResult with organism state
        pedi = getattr(being.state, "pedi", None)
        dii = getattr(being.state, "dii", None)

        sec.pedi_value = getattr(pedi, "value", 0.0)
        sec.pedi_stability = getattr(pedi, "stability", 0.0)
        sec.dii_value = getattr(dii, "value", 0.0)
        sec.dii_velocity = getattr(dii, "integration_velocity", 0.0)

        # Behavioral anomaly detector and social risk
        if hasattr(scanner, "behavioral"):
            sec.social_risk = scanner.behavioral.get_social_risk()

        # Shadow integration on high social risk
        if sec.social_risk > 0.42:
            try:
                from infj_bot.core.shadow import shadow_critic
                from infj_bot.core.types import SparkImpulse
                impulse = SparkImpulse()
                impulse.shadow_influence = sec.social_risk * 0.9
                shadow_critic.critique_spark(impulse, {
                    "energy": getattr(being.state, "energy", 0.6),
                    "social_risk": sec.social_risk
                })
                if impulse.veto_reason:
                    sec.overall_score = max(sec.overall_score, 0.78)
                    if not sec.refusal_message:
                        sec.refusal_message = "I'm detecting unusual persistence or pressure. Let's pause and clarify intent."
            except Exception:
                pass

        return sec

    def _security_check(self, user_input: str, raw_user_input: Optional[str] = None, mode: Optional[str] = None) -> SecurityScanResult:
        """Run security defense scan on user input, extracting raw content if it is an assembled prompt."""
        if raw_user_input is not None:
            return scan_input(raw_user_input, mode=mode)

        cleaned_input = user_input
        for marker in ["\nUser: ", "\nUser:\n"]:
            idx = user_input.rfind(marker)
            if idx != -1:
                candidate = user_input[idx + len(marker):].strip()
                if candidate:
                    cleaned_input = candidate
                    break
        return scan_input(cleaned_input, mode=mode)

    def _current_request_budget(self):
        request_budget_local = getattr(self, "_request_budget_local", None)
        if request_budget_local is None:
            return None
        return getattr(request_budget_local, "budget", None)

    def think(self, user_input, raw_user_input=None, mode=None):
        sec = self._enhanced_security_check(user_input, raw_user_input, mode=mode)
        if sec.blocked:
            self.logger.warning("Security block: %s", sec.to_dict())
            return sec.refusal_message or "I can't process that request."
        if sec.warn:
            self.logger.info("Security warning: %s", sec.to_dict())
            user_input = sec.sanitized_input or user_input

        # Dynamic system instruction formatting
        sys_instruction = self.get_system_instruction(user_input)
        request_budget = self._current_request_budget()

        # Token gate calculation
        from infj_bot.core.being import get_being
        being = get_being()
        prev_energy = being.state.energy
        max_tokens = max(100, int(1000 * prev_energy))

        # Logic chain: inject previous reasoning attempts
        chain_block = self.chain_navigator.get_prompt_block(user_input)
        history_context = "\n".join(self.history[-6:])
        full_prompt = (
            f"Recent conversation:\n{history_context}\n\n{chain_block}\n\nUser:\n{user_input}"
            if chain_block
            else f"Recent conversation:\n{history_context}\n\nUser:\n{user_input}"
        )

        try:
            # High-tier logic: Try HF Pro for complex reasoning if enabled
            if DRIFT_USE_HF and self.hf_bridge.is_available():
                # Pass conversation history natively via the HF chat API instead
                # of cramming it all into a single user prompt.
                history_messages = self._history_to_messages()
                current_prompt = (
                    f"{chain_block}\n\nUser:\n{user_input}"
                    if chain_block
                    else f"User:\n{user_input}"
                )
                try:
                    if request_budget is not None:
                        request_budget.check()
                    primary_text = self.hf_bridge.generate(
                        sys_instruction, current_prompt, history=history_messages, max_tokens=max_tokens
                    )
                except Exception as hf_exc:
                    self.logger.warning("HF Pro generate failed: %s. Falling back.", hf_exc)
                    primary_text = None

                if primary_text:
                    if request_budget is not None:
                        request_budget.check()
                    self.history.extend([f"User: {user_input}", f"Bot: {primary_text}"])
                    if len(self.history) > self._max_history:
                        self.history = self.history[-self._max_history :]
                else:
                    self.logger.warning("HF Pro failed to generate a response. Falling back to governor chain.")
                    primary_text = self._generate(
                        self.primary_model_name,
                        sys_instruction,
                        full_prompt,
                        max_tokens=max_tokens,
                    )
                    if request_budget is not None:
                        request_budget.check()
                    self.history.extend([f"User: {user_input}", f"Bot: {primary_text}"])
                    if len(self.history) > self._max_history:
                        self.history = self.history[-self._max_history :]
            elif self.sdk == "google.genai":
                primary_text = self._generate(
                    self.primary_model_name,
                    sys_instruction,
                    full_prompt,
                    max_tokens=max_tokens,
                )
                if request_budget is not None:
                    request_budget.check()
                self.history.extend([f"User: {user_input}", f"Bot: {primary_text}"])
                if len(self.history) > self._max_history:
                    self.history = self.history[-self._max_history :]
            elif self.sdk == "google.generativeai":
                primary_text = self._generate(
                    self.primary_model_name,
                    sys_instruction,
                    full_prompt,
                    max_tokens=max_tokens,
                )
                if request_budget is not None:
                    request_budget.check()
                self.history.extend([f"User: {user_input}", f"Bot: {primary_text}"])
                if len(self.history) > self._max_history:
                    self.history = self.history[-self._max_history :]
            else:
                # Fallback path (Groq, Kimi, or Local)
                primary_text = self._generate(
                    self.primary_model_name,
                    sys_instruction,
                    full_prompt,
                    max_tokens=max_tokens,
                )
        except (RequestCancelled, RequestDeadlineExceeded, SystemOverload):
            raise
        except Exception as exc:
            return self._offline_fallback(user_input, exc)

        # Record the approach in the chain
        approach = self._extract_approach(primary_text)
        # record within the current scope (if set) to keep chains scoped
        try:
            self.chain_navigator.record_step(
                query=user_input,
                approach=approach,
                result="generated response",
                status="unknown",
                scope=self.scope,
            )
        except Exception:
            self.logger.exception("Failed to record chain step")

        try:
            if request_budget is not None:
                request_budget.check()
            return self._generate(
                self.critic_model_name,
                CRITIC_SYSTEM_PROMPT,
                f"Review the following response for hallucinations, errors, or unsafe content:\n\n{primary_text}",
            )
        except Exception as exc:
            return f"{primary_text}\n\n[critic unavailable: {type(exc).__name__}]"

    @staticmethod
    def _extract_approach(text: str) -> str:
        """Heuristic to extract the core approach from a response."""
        lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
        for line in lines[:5]:
            lowered = line.lower()
            if any(
                k in lowered
                for k in (
                    "try",
                    "check",
                    "look at",
                    "inspect",
                    "verify",
                    "test",
                    "examine",
                    "consider",
                    "first",
                    "start by",
                    "maybe",
                    "suggest",
                    "recommend",
                    "approach",
                )
            ):
                return line[:200]
        return lines[0][:200] if lines else "generated response"

    # ------------------------------------------------------------------
    # Streaming think
    # ------------------------------------------------------------------

    def think_stream(self, user_input, raw_user_input=None, mode=None):
        """Yield text chunks as they arrive from the model."""
        sec = self._enhanced_security_check(user_input, raw_user_input, mode=mode)
        if sec.blocked:
            self.logger.warning("Security block (stream): %s", sec.to_dict())
            yield sec.refusal_message or "I can't process that request."
            return
        if sec.warn:
            self.logger.info("Security warning (stream): %s", sec.to_dict())
            user_input = sec.sanitized_input or user_input

        # Dynamic system instruction formatting
        sys_instruction = self.get_system_instruction(user_input)
        request_budget = self._current_request_budget()

        # Token gate calculation
        from infj_bot.core.being import get_being
        being = get_being()
        prev_energy = being.state.energy
        max_tokens = max(100, int(1000 * prev_energy))

        try:
            history_context = "\n".join(self.history[-6:])
            full_prompt = (
                f"Recent conversation:\n{history_context}\n\nUser:\n{user_input}"
            )
            chunks = []
            for chunk in self._generate_stream(
                self.primary_model_name, sys_instruction, full_prompt, max_tokens=max_tokens
            ):
                chunks.append(chunk)
                yield chunk
            primary_text = "".join(chunks)
            if request_budget is not None:
                request_budget.check()
            self.history.extend([f"User: {user_input}", f"Bot: {primary_text}"])
            if len(self.history) > self._max_history:
                self.history = self.history[-self._max_history :]
        except (RequestCancelled, RequestDeadlineExceeded, SystemOverload):
            raise
        except Exception as exc:
            yield self._offline_fallback(user_input, exc)

    # ------------------------------------------------------------------
    # Agent turn with tools
    # ------------------------------------------------------------------

    def agent_turn(self, user_input, tools_enabled=True, max_iterations=3, raw_user_input=None, mode=None):
        sec = self._enhanced_security_check(user_input, raw_user_input, mode=mode)
        if sec.blocked:
            self.logger.warning("Security block (agent turn): %s", sec.to_dict())
            return sec.refusal_message or "I can't process that request."
        if sec.warn:
            self.logger.info("Security warning (agent turn): %s", sec.to_dict())
            user_input = sec.sanitized_input or user_input
        if not tools_enabled:
            return self.think(user_input, raw_user_input=raw_user_input, mode=mode)

        provider = "ollama" if "ollama" in self.primary_model_name.lower() or "qwen" in self.primary_model_name.lower() else "gemini"
        _sampler = CPUSampler(
            inference_pid=_get_ollama_pid() if provider == "ollama" else None
        ).start()

        tool_prompt = build_tool_prompt()
        iteration = 0
        context = user_input
        chain_block = self.chain_navigator.get_prompt_block(
            user_input, scope=self.scope
        )

        # Dynamic system instruction formatting
        sys_instruction = self.get_system_instruction(user_input)
        request_budget = self._current_request_budget()

        # Token gate calculation via governor
        from infj_bot.core.being import get_being
        being = get_being()
        prev_energy = being.state.energy
        
        # Increment turn number
        self.turns = getattr(self, "turns", 0) + 1

        gate_result = self._cognitive_governor.apply(prev_energy, turn=self.turns)
        max_tokens = gate_result.max_tokens
        gate_applied = gate_result.gate_applied

        primary_text = ""
        try:
            while iteration < max_iterations:
                iteration += 1
                history_context = "\n".join(self.history[-6:])
                full_prompt = (
                    (
                        f"{sys_instruction}\n\n{tool_prompt}\n\n"
                        f"{chain_block}\n\n"
                        f"Recent conversation:\n{history_context}\n\nUser:\n{context}"
                    )
                    if chain_block
                    else (
                        f"{sys_instruction}\n\n{tool_prompt}\n\n"
                        f"Recent conversation:\n{history_context}\n\nUser:\n{context}"
                    )
                )
                response_text = self._generate(
                    self.primary_model_name, sys_instruction, full_prompt, max_tokens=max_tokens
                )

                tool_calls = extract_tool_calls(response_text)
                if not tool_calls:
                    primary_text = response_text
                    break

                results = []
                for call in tool_calls:
                    import json as _json

                    raw = _json.dumps(call)
                    tool_name = call.get("name")
                    
                    # Phase 5: High-risk deliberation
                    if tool_name in HIGH_RISK_TOOLS and self.deliberation_callback:
                        self.logger.info("High-risk tool '%s' detected. Requesting council deliberation...", tool_name)
                        deliberation_goal = f"Execute high-risk tool '{tool_name}' with arguments: {call.get('arguments')}"
                        try:
                            # The callback returns a DeliberationResult
                            delib_result = self.deliberation_callback(deliberation_goal)
                            
                            # Check if the council consensus is to block or if the resolution is a refusal
                            if "BLOCK" in delib_result.resolution.upper() or "DENY" in delib_result.resolution.upper() or "REFUSE" in delib_result.resolution.upper():
                                self.logger.warning("Council BLOCKED high-risk tool '%s'. Resolution: %s", tool_name, delib_result.resolution)
                                results.append(f"Tool '{tool_name}' was BLOCKED by the Council. Reason: {delib_result.resolution}")
                                continue
                            
                            self.logger.info("Council APPROVED high-risk tool '%s'.", tool_name)
                        except Exception as e:
                            self.logger.error("Deliberation failed for tool '%s': %s. Blocking by default.", tool_name, e)
                            results.append(f"Tool '{tool_name}' was BLOCKED due to an internal deliberation failure.")
                            continue

                    result = execute_tool_call(raw)
                    results.append(f"Tool '{call.get('name')}' result:\n{result}")
                tool_results = "\n\n".join(results)
                context = (
                    f"Your previous thought included tool calls. Here are the results:\n\n"
                    f"{tool_results}\n\n"
                    f"Now answer the user's original request:\n{user_input}"
                )
            # DRIFT V2 — math critic enforcement
            # Tool result always wins over model arithmetic.
            grounded_math = active_grounded_math_var.get()
            if grounded_math:
                primary_text, math_violations = critic_math_check(
                    primary_text, grounded_math
                )
                if math_violations:
                    self.logger.warning(
                        "DRIFT CRITIC — math corrections: %s", math_violations
                    )

            if request_budget is not None:
                request_budget.check()
            self.history.extend([f"User: {user_input}", f"Bot: {primary_text}"])
            if len(self.history) > self._max_history:
                self.history = self.history[-self._max_history :]

            # Record approach in chain (scoped)
            approach = self._extract_approach(primary_text)
            try:
                if request_budget is not None:
                    request_budget.check()
                self.chain_navigator.record_step(
                    query=user_input,
                    approach=approach,
                    result="agent turn completed",
                    status="unknown",
                    scope=self.scope,
                )
            except Exception:
                self.logger.exception("Failed to record agent turn in chain navigator")

            # Run critic in background (do not return critic text to user)
            try:
                if request_budget is not None:
                    request_budget.check()
                self._generate(
                    self.critic_model_name,
                    CRITIC_SYSTEM_PROMPT,
                    f"Review the following response for hallucinations, errors, or unsafe content:\n\n{primary_text}",
                )
            except Exception:
                pass
            _timing = _sampler.stop()

            # DRIFT V2 — update homeostasis needs with timing and response length
            new_energy = prev_energy
            delta_energy = 0.0
            from infj_bot.core.homeostasis import get_homeostasis
            homeo = get_homeostasis()
            try:
                homeo.update_needs(event="inference_complete", timing=_timing, response_len=len(primary_text))
                new_energy = being.state.energy
            except Exception:
                pass

            # Record turn in cognitive governor
            try:
                turn_record = self._cognitive_governor.record_turn(
                    prev_energy=prev_energy,
                    new_energy=new_energy,
                    response_len=len(primary_text),
                    gate_result=gate_result,
                )
                new_energy = turn_record.new_energy
                delta_energy = turn_record.delta_energy
                
                # Sync new energy with homeostasis system
                homeo.update_need("energy", being.state.energy)
            except Exception:
                self.logger.exception("Failed to record turn in cognitive governor")

            # DRIFT V2 — trajectory logging
            try:
                # PEDI
                try:
                    from infj_bot.metrics.pedi import get_pedi
                    pedi_snap = get_pedi().get_last_snapshot()
                    pedi_val = pedi_snap.needs if pedi_snap else {}
                except Exception:
                    pedi_val = {}

                # DII
                try:
                    from infj_bot.core.dii_tracker import get_dii_tracker
                    dii_snap = get_dii_tracker().get_current()
                    dii_val = dii_snap.dii if dii_snap else 0.5
                except Exception:
                    dii_val = 0.5

                from infj_bot.core.causal_wiring import retrieved_memory_keys_var
                memory_keys = retrieved_memory_keys_var.get()

                # self.turns is already incremented at the start of the turn
                _traj_logger.log_turn(
                    turn=self.turns,
                    state={
                        "pedi": pedi_val,
                        "dii": dii_val,
                        "energy": being.state.energy,
                        "mood": being.state.mood,
                        "curiosity": being.state.curiosity,
                        "fatigue": round(1.0 - being.state.energy, 4),
                        "needs": homeo.get_need_summary() if hasattr(homeo, "get_need_summary") else {},
                        "mode": mode or "unknown",
                        "memory_keys": memory_keys,
                    },
                    prompt_len=len(user_input),
                    response_len=len(primary_text),
                    provider=provider,
                    timing=_timing,
                )
            except Exception:
                self.logger.exception("Failed to log turn in trajectory logger")

            return primary_text

        except (RequestCancelled, RequestDeadlineExceeded, SystemOverload):
            raise
        except Exception as exc:
            return self._offline_fallback(user_input, exc)

    def agent_turn_stream(self, user_input, tools_enabled=True, max_iterations=3, raw_user_input=None, mode=None):
        """Execute tools synchronously, then stream the final response."""
        sec = self._enhanced_security_check(user_input, raw_user_input, mode=mode)
        if sec.blocked:
            yield sec.refusal_message or "I can't process that request."
            return
        if sec.warn:
            user_input = sec.sanitized_input or user_input
        if not tools_enabled:
            yield from self.think_stream(user_input, raw_user_input=raw_user_input, mode=mode)
            return

        tool_prompt = build_tool_prompt()
        iteration = 0
        context = user_input

        # Dynamic system instruction formatting
        sys_instruction = self.get_system_instruction(user_input)
        request_budget = self._current_request_budget()

        provider = "ollama" if "ollama" in self.primary_model_name.lower() or "qwen" in self.primary_model_name.lower() else "gemini"
        _sampler = CPUSampler(
            inference_pid=_get_ollama_pid() if provider == "ollama" else None
        ).start()

        # Token gate calculation via governor
        from infj_bot.core.being import get_being
        being = get_being()
        prev_energy = being.state.energy
        
        # Increment turn number
        self.turns = getattr(self, "turns", 0) + 1

        gate_result = self._cognitive_governor.apply(prev_energy, turn=self.turns)
        max_tokens = gate_result.max_tokens
        gate_applied = gate_result.gate_applied

        primary_text = ""
        try:
            while iteration < max_iterations:
                iteration += 1
                if self.sdk == "google.genai":
                    history_context = "\n".join(self.history[-6:])
                    full_prompt = (
                        f"{sys_instruction}\n\n{tool_prompt}\n\n"
                        f"Recent conversation:\n{history_context}\n\nUser:\n{context}"
                    )
                    response_text = self._generate(
                        self.primary_model_name, sys_instruction, full_prompt, max_tokens=max_tokens
                    )
                else:
                    full_prompt = f"{tool_prompt}\n\nUser:\n{context}"
                    response_text = self._generate(
                        self.primary_model_name, sys_instruction, full_prompt, max_tokens=max_tokens
                    )

                tool_calls = extract_tool_calls(response_text)
                if not tool_calls:
                    primary_text = response_text
                    break

                results = []
                for call in tool_calls:
                    import json as _json

                    raw = _json.dumps(call)
                    tool_name = call.get("name")
                    
                    # Phase 5: High-risk deliberation
                    if tool_name in HIGH_RISK_TOOLS and self.deliberation_callback:
                        self.logger.info("High-risk tool '%s' detected. Requesting council deliberation...", tool_name)
                        deliberation_goal = f"Execute high-risk tool '{tool_name}' with arguments: {call.get('arguments')}"
                        try:
                            # The callback returns a DeliberationResult
                            delib_result = self.deliberation_callback(deliberation_goal)
                            
                            # Check if the council consensus is to block or if the resolution is a refusal
                            if "BLOCK" in delib_result.resolution.upper() or "DENY" in delib_result.resolution.upper() or "REFUSE" in delib_result.resolution.upper():
                                self.logger.warning("Council BLOCKED high-risk tool '%s'. Resolution: %s", tool_name, delib_result.resolution)
                                results.append(f"Tool '{tool_name}' was BLOCKED by the Council. Reason: {delib_result.resolution}")
                                continue
                            
                            self.logger.info("Council APPROVED high-risk tool '%s'.", tool_name)
                        except Exception as e:
                            self.logger.error("Deliberation failed for tool '%s': %s. Blocking by default.", tool_name, e)
                            results.append(f"Tool '{tool_name}' was BLOCKED due to an internal deliberation failure.")
                            continue

                    result = execute_tool_call(raw)
                    results.append(f"Tool '{call.get('name')}' result:\n{result}")
                tool_results = "\n\n".join(results)
                context = (
                    f"Your previous thought included tool calls. Here are the results:\n\n"
                    f"{tool_results}\n\n"
                    f"Now answer the user's original request:\n{user_input}"
                )
            else:
                primary_text = response_text

            if request_budget is not None:
                request_budget.check()
            self.history.extend([f"User: {user_input}", f"Bot: {primary_text}"])
            if len(self.history) > self._max_history:
                self.history = self.history[-self._max_history :]

            _timing = _sampler.stop()

            # DRIFT V2 — update homeostasis needs with timing and response length
            new_energy = prev_energy
            delta_energy = 0.0
            from infj_bot.core.homeostasis import get_homeostasis
            homeo = get_homeostasis()
            try:
                homeo.update_needs(event="inference_complete", timing=_timing, response_len=len(primary_text))
                new_energy = being.state.energy
            except Exception:
                pass

            # Record turn in cognitive governor
            try:
                turn_record = self._cognitive_governor.record_turn(
                    prev_energy=prev_energy,
                    new_energy=new_energy,
                    response_len=len(primary_text),
                    gate_result=gate_result,
                )
                new_energy = turn_record.new_energy
                delta_energy = turn_record.delta_energy
                
                # Sync new energy with homeostasis system
                homeo.update_need("energy", being.state.energy)
            except Exception:
                self.logger.exception("Failed to record turn in cognitive governor")

            # DRIFT V2 — trajectory logging
            try:
                # PEDI
                try:
                    from infj_bot.metrics.pedi import get_pedi
                    pedi_snap = get_pedi().get_last_snapshot()
                    pedi_val = pedi_snap.needs if pedi_snap else {}
                except Exception:
                    pedi_val = {}

                # DII
                try:
                    from infj_bot.core.dii_tracker import get_dii_tracker
                    dii_snap = get_dii_tracker().get_current()
                    dii_val = dii_snap.dii if dii_snap else 0.5
                except Exception:
                    dii_val = 0.5

                from infj_bot.core.causal_wiring import retrieved_memory_keys_var
                memory_keys = retrieved_memory_keys_var.get()

                # self.turns is already incremented at the start of the turn
                _traj_logger.log_turn(
                    turn=self.turns,
                    state={
                        "pedi": pedi_val,
                        "dii": dii_val,
                        "energy": being.state.energy,
                        "mood": being.state.mood,
                        "curiosity": being.state.curiosity,
                        "fatigue": round(1.0 - being.state.energy, 4),
                        "needs": homeo.get_need_summary() if hasattr(homeo, "get_need_summary") else {},
                        "mode": mode or "unknown",
                        "memory_keys": memory_keys,
                    },
                    prompt_len=len(user_input),
                    response_len=len(primary_text),
                    provider=provider,
                    timing=_timing,
                )
            except Exception:
                self.logger.exception("Failed to log turn in trajectory logger")

            # Stream the actual response to the user (critic runs separately)
            yield primary_text

        except (RequestCancelled, RequestDeadlineExceeded, SystemOverload):
            raise
        except Exception as exc:
            yield self._offline_fallback(user_input, exc)

    # ------------------------------------------------------------------
    # Reflection
    # ------------------------------------------------------------------

    def reflect(self, recent_context):
        prompt = """
Extract durable memory candidates from these recent interactions.

Rules:
- Do not store passwords, API keys, tokens, private credentials, addresses, financial data, or one-time sensitive details.
- Prefer stable user preferences, ongoing projects, bot behavior improvements, and durable project facts.
- Keep it concise and useful for future conversations.
- If unsure whether something is sensitive, omit it.
"""
        if isinstance(recent_context, list):
            recent_context = "\n---\n".join(str(r) for r in recent_context)
        return self._generate(
            self.critic_model_name,
            CRITIC_SYSTEM_PROMPT,
            f"{prompt}\n\nRecent interactions:\n{recent_context}",
        )

    def evaluate_last(self, prompt: str, response: str) -> dict:
        """Run self-evaluation on a response and store the result."""
        scores = self.evaluator.evaluate(prompt, response)
        self.evaluator.record(prompt, response, scores)
        return scores

    def health_check(self) -> dict:
        gemini_ok = API_KEY is not None and API_KEY != ""
        local_ok = self.local_bridge.is_available()
        return {
            "gemini": {
                "ok": gemini_ok,
                "sdk": self.sdk,
                "primary_model": self.primary_model_name,
            },
            "groq": {
                "ok": DRIFT_USE_GROQ and bool(GROQ_API_KEY),
                "model": DRIFT_GROQ_MODEL,
            },
            "kimi": {
                "ok": DRIFT_USE_KIMI and bool(KIMI_API_KEY),
                "model": DRIFT_KIMI_MODEL,
            },
            "local": {
                "ok": local_ok,
                "host": self.local_bridge.host,
                "model": self.local_bridge.model,
            },
            "fallback_enabled": self._use_local_fallback,
        }

    def list_local_models(self) -> list:
        if not self.local_bridge.is_available():
            return []
        return self.local_bridge.list_models()

    def clear_history(self):
        self.history = []
        self._gen_cache.clear()
        if self.sdk == "google.generativeai" and self.primary_model is not None:
            self.chat = self.primary_model.start_chat(history=[])


if __name__ == "__main__":
    try:
        brain = DriftBrain()
        print(f"Brain initialized with {brain.sdk}. Ready to think.")
    except ImportError as e:
        print(f"Initialization skipped: {e}")
