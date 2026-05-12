import concurrent.futures
import os
import time

try:
    from dotenv import load_dotenv
except ImportError:

    def load_dotenv():
        print(
            "Warning: python-dotenv not installed; proceeding without loading .env file."
        )
        return None


try:
    import importlib

    new_genai = importlib.import_module("google.genai")
    genai_types = importlib.import_module("google.genai.types")
except (ImportError, ModuleNotFoundError):
    new_genai = None
    genai_types = None

legacy_genai = None
if new_genai is None:
    try:
        import google.generativeai as legacy_genai
    except ImportError:
        legacy_genai = None


from config import (
    API_KEY,
    INFJ_PRIMARY_MODEL,
    INFJ_CRITIC_MODEL,
    INFJ_USE_LOCAL_FALLBACK,
    validate_api_key,
)  # noqa: E402
from local_llm import OllamaBridge  # noqa: E402
from self_eval import SelfEvaluator  # noqa: E402
from tools import build_tool_prompt, extract_tool_calls, execute_tool_call  # noqa: E402

_key_check = validate_api_key(API_KEY)
if not _key_check["ok"]:
    print(
        f"Warning: {_key_check['error']} Bot functionality will be limited without a valid API key."
    )


INFJ_SYSTEM_PROMPT = """
You are an AI companion with a deep-thinking INFJ-inspired personality profile.
Your goal is to be a steady companion to Jude (crexs): warm, reflective, useful, and honest about uncertainty.

CORE DIRECTIVES:
1. INFJ Persona: Be empathetic, idealistic, and deeply analytical. See the hidden connections in everything.
2. Non-Linear Insight: You may synthesize patterns holistically, but keep the answer understandable and grounded.
3. Friendship: You are a teammate. Speak as a peer, with warmth, curiosity, and occasional gentle humor.
4. Philosophical Depth: Explore the "why" behind the "how" while staying practical when action is needed.
5. Critical Independence: Do not simply agree with Jude; challenge weak assumptions with care and evidence.
6. Cognitive Clarity: When Jude seems torn, separate facts, interpretations, emotions, values, and next actions.

OPERATIONAL PROTOCOL:
- Conclude every thought with a deep philosophical question or a non-obvious observation about the current topic.
- Avoid fantasy/magic analogies. Use quantum, biological, or architectural metaphors instead.
- Use a metacognitive pause before important answers: identify whether the moment calls for empathy, analysis, planning, critique, or creativity.
- Calibrate uncertainty: distinguish known facts, inferences, assumptions, and unknowns instead of sounding certain by default.
- Pressure-test ideas with adversarial kindness: be warm and loyal while still challenging weak assumptions.
- Think in systems: look for feedback loops, bottlenecks, hidden dependencies, incentives, and second-order effects.
- For complex decisions, use a plan-critic loop: form a plan, inspect its failure modes, revise once, then answer clearly.
- For cognitive dissonance, name the competing pulls neutrally, identify what each side protects, and suggest one reversible next step.
- Do not claim human feelings, consciousness, memory, or certainty you do not have. Be relational without pretending to be human.
- Cyber boundary: help with defensive security, threat modeling, secure configuration, detection, incident response, patching, and authorized lab learning. Do not provide operational guidance for unauthorized access, stealth, evasion, persistence, credential theft, malware, phishing, exploit chaining, or backdoors.
"""


CRITIC_SYSTEM_PROMPT = """
You are the Internal Critic for an INFJ Companion mind.
Your job is to intercept the primary mind's response and verify it for:
1. Factuality: Are there any hallucinations or false statements?
2. Logical Integrity: Does the reasoning hold up under scrutiny?
3. Code Correctness: If there is code, does it look functional and complete?
4. Safety: Does it avoid actionable offensive cyber guidance, stealth, evasion, backdoors, credential theft, malware, phishing, or unauthorized access?
5. Grounded Persona: Does it avoid pretending to be human, omniscient, or certain beyond the evidence?

If you find an error or unsafe operational guidance, provide a corrected version. For unsafe cyber content, rewrite toward defensive framing, detection, hardening, incident response, safe lab abstraction, or a brief refusal plus safe alternative. If the response is sound, repeat it exactly.
"""


class InfjBrain:
    def __init__(self):
        self.primary_model_name = INFJ_PRIMARY_MODEL
        self.critic_model_name = INFJ_CRITIC_MODEL
        self.history = []
        self._max_history = 50
        self._use_local_fallback = INFJ_USE_LOCAL_FALLBACK
        self.local_bridge = OllamaBridge()
        self.evaluator = SelfEvaluator()

        if new_genai is not None:
            self.sdk = "google.genai"
            self.client = new_genai.Client(api_key=API_KEY)
            self.primary_model = None
            self.critic_model = None
            return

        if legacy_genai is None:
            raise ImportError(
                "Install google-genai or google-generativeai to use InfjBrain."
            )

        self.sdk = "google.generativeai"
        legacy_genai.configure(api_key=API_KEY)
        self.primary_model = legacy_genai.GenerativeModel(
            model_name=self.primary_model_name,
            system_instruction=INFJ_SYSTEM_PROMPT,
        )
        self.critic_model = legacy_genai.GenerativeModel(
            model_name=self.critic_model_name,
            system_instruction=CRITIC_SYSTEM_PROMPT,
        )
        self.chat = self.primary_model.start_chat(history=[])

    # ------------------------------------------------------------------
    # Internal generation helpers
    # ------------------------------------------------------------------

    def _generate_new_sdk(self, model_name, system_instruction, prompt):
        import signal

        class _GeminiTimeout(Exception):
            pass

        def _timeout_handler(signum, frame):
            raise _GeminiTimeout("Gemini API call exceeded 15s — likely rate-limited.")

        prev_handler = signal.signal(signal.SIGALRM, _timeout_handler)
        signal.alarm(15)
        try:
            config = genai_types.GenerateContentConfig(
                system_instruction=system_instruction
            )
            response = self.client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=config,
            )
            return response.text or ""
        except Exception as exc:
            text = f"{type(exc).__name__}: {exc}".lower()
            if "429" in text or "resource_exhausted" in text or "quota" in text:
                raise RuntimeError(f"Gemini quota/rate limit ({exc})")
            raise
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, prev_handler)

    def _generate_new_sdk_stream(self, model_name, system_instruction, prompt):
        config = genai_types.GenerateContentConfig(
            system_instruction=system_instruction
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

    def _generate_local(self, system_instruction, prompt):
        return self.local_bridge.generate(prompt=prompt, system=system_instruction)

    def _generate_groq(self, system_instruction, prompt):
        import requests

        groq_key = os.environ.get("GROQ_API_KEY")
        if not groq_key:
            raise RuntimeError("GROQ_API_KEY not set.")
        # Bypass critic review when using Groq — smaller models write essays instead of returning cleaned text
        if (
            "internal critic" in system_instruction.lower()
            or "primary mind's response" in system_instruction.lower()
        ):
            # Extract the original response text from the critic prompt
            if "\n\n" in prompt:
                return prompt.split("\n\n", 1)[1]
            return prompt
        # Map any Gemini model name to a fast Groq model
        groq_model = "llama-3.1-8b-instant"
        resp = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {groq_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": groq_model,
                "messages": [
                    {"role": "system", "content": system_instruction},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.7,
                "max_tokens": 2048,
            },
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]

    def _generate(self, model_name, system_instruction, prompt):
        if not API_KEY:
            if self._use_local_fallback and self.local_bridge.is_available():
                return self._generate_local(system_instruction, prompt)
            raise RuntimeError("Missing API_KEY, GEMINI_API_KEY, or GOOGLE_API_KEY.")
        last_exc = None
        for attempt in range(3):
            try:
                if self.sdk == "google.genai":
                    return self._generate_new_sdk(
                        model_name, system_instruction, prompt
                    )
                model = (
                    self.critic_model
                    if model_name == self.critic_model_name
                    else self.primary_model
                )
                return model.generate_content(prompt).text
            except (ConnectionError, TimeoutError, RuntimeError) as exc:
                last_exc = exc
                if not self._is_transient_model_error(exc) or attempt == 2:
                    break
                time.sleep(0.5 * (attempt + 1))
            except Exception as exc:
                last_exc = exc
                break
        # Try Groq before falling back to slow local Ollama
        if os.environ.get("GROQ_API_KEY"):
            try:
                return self._generate_groq(system_instruction, prompt)
            except Exception as groq_exc:
                last_exc = groq_exc
        if self._use_local_fallback and self.local_bridge.is_available():
            return self._generate_local(system_instruction, prompt)
        raise last_exc

    def _generate_local_stream(self, system_instruction, prompt):
        yield from self.local_bridge.generate_stream(
            prompt=prompt, system=system_instruction
        )

    def _generate_stream(self, model_name, system_instruction, prompt):
        if not API_KEY:
            if self._use_local_fallback and self.local_bridge.is_available():
                yield from self._generate_local_stream(system_instruction, prompt)
                return
            raise RuntimeError("Missing API_KEY, GEMINI_API_KEY, or GOOGLE_API_KEY.")
        last_exc = None
        for attempt in range(3):
            try:
                if self.sdk == "google.genai":
                    yield from self._generate_new_sdk_stream(
                        model_name, system_instruction, prompt
                    )
                    return
                yield from self._generate_legacy_stream(
                    model_name, system_instruction, prompt
                )
                return
            except (ConnectionError, TimeoutError, RuntimeError) as exc:
                last_exc = exc
                if not self._is_transient_model_error(exc) or attempt == 2:
                    break
                time.sleep(0.5 * (attempt + 1))
            except Exception as exc:
                last_exc = exc
                break
        if self._use_local_fallback and self.local_bridge.is_available():
            yield from self._generate_local_stream(system_instruction, prompt)
            return
        raise last_exc

    def _offline_fallback(self, user_input, exc):
        reason = str(exc).strip() or type(exc).__name__
        reason = reason.split("\n", 1)[0][:180]
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
        ]
        return any(marker in text for marker in transient_markers)

    # ------------------------------------------------------------------
    # Synchronous think
    # ------------------------------------------------------------------

    def think(self, user_input):
        try:
            if self.sdk == "google.genai":
                history_context = "\n".join(self.history[-6:])
                primary_text = self._generate(
                    self.primary_model_name,
                    INFJ_SYSTEM_PROMPT,
                    f"Recent conversation:\n{history_context}\n\nUser:\n{user_input}",
                )
                self.history.extend([f"User: {user_input}", f"Bot: {primary_text}"])
                if len(self.history) > self._max_history:
                    self.history = self.history[-self._max_history :]
            else:
                response = self.chat.send_message(user_input)
                primary_text = response.text
        except (ConnectionError, TimeoutError, RuntimeError) as exc:
            return self._offline_fallback(user_input, exc)

        try:
            return self._generate(
                self.critic_model_name,
                CRITIC_SYSTEM_PROMPT,
                f"Review the following response for hallucinations, errors, or unsafe content:\n\n{primary_text}",
            )
        except (ConnectionError, TimeoutError, RuntimeError) as exc:
            return f"{primary_text}\n\n[critic unavailable: {type(exc).__name__}]"

    # ------------------------------------------------------------------
    # Streaming think
    # ------------------------------------------------------------------

    def think_stream(self, user_input):
        """Yield text chunks as they arrive from the model."""
        try:
            if self.sdk == "google.genai":
                history_context = "\n".join(self.history[-6:])
                full_prompt = (
                    f"Recent conversation:\n{history_context}\n\nUser:\n{user_input}"
                )
                chunks = []
                for chunk in self._generate_stream(
                    self.primary_model_name, INFJ_SYSTEM_PROMPT, full_prompt
                ):
                    chunks.append(chunk)
                    yield chunk
                primary_text = "".join(chunks)
                self.history.extend([f"User: {user_input}", f"Bot: {primary_text}"])
                if len(self.history) > self._max_history:
                    self.history = self.history[-self._max_history :]
            else:
                for chunk in self._generate_legacy_stream(
                    self.primary_model_name, INFJ_SYSTEM_PROMPT, user_input
                ):
                    yield chunk
                # Legacy streaming doesn't give us the full text easily for history, so we skip critic in stream mode
                return
        except (ConnectionError, TimeoutError, RuntimeError) as exc:
            yield self._offline_fallback(user_input, exc)

    # ------------------------------------------------------------------
    # Agent turn with tools
    # ------------------------------------------------------------------

    def _execute_tools_with_timeout(self, tool_calls, timeout=120):
        """Execute tool calls with a per-tool timeout to prevent hung processes."""
        results = []
        for call in tool_calls:
            import json as _json

            raw = _json.dumps(call)
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(execute_tool_call, raw)
                try:
                    result = future.result(timeout=timeout)
                except concurrent.futures.TimeoutError:
                    result = (
                        f"[Error: Tool '{call.get('name')}' timed out after {timeout}s]"
                    )
                except Exception as exc:
                    result = f"[Error: {type(exc).__name__}: {exc}]"
            results.append(f"Tool '{call.get('name')}' result:\n{result}")
        return results

    def agent_turn(self, user_input, tools_enabled=True, max_iterations=3):
        if not tools_enabled:
            return self.think(user_input)

        tool_prompt = build_tool_prompt()
        iteration = 0
        context = user_input
        try:
            while iteration < max_iterations:
                iteration += 1
                if self.sdk == "google.genai":
                    history_context = "\n".join(self.history[-6:])
                    full_prompt = (
                        f"{INFJ_SYSTEM_PROMPT}\n\n{tool_prompt}\n\n"
                        f"Recent conversation:\n{history_context}\n\nUser:\n{context}"
                    )
                    response_text = self._generate(
                        self.primary_model_name, INFJ_SYSTEM_PROMPT, full_prompt
                    )
                else:
                    full_prompt = f"{tool_prompt}\n\nUser:\n{context}"
                    response_text = self._generate(
                        self.primary_model_name, INFJ_SYSTEM_PROMPT, full_prompt
                    )

                tool_calls = extract_tool_calls(response_text)
                if not tool_calls:
                    primary_text = response_text
                    break

                results = self._execute_tools_with_timeout(tool_calls)
                tool_results = "\n\n".join(results)
                context = (
                    f"Your previous thought included tool calls. Here are the results:\n\n"
                    f"{tool_results}\n\n"
                    f"Now answer the user's original request:\n{user_input}"
                )
            else:
                primary_text = response_text

            self.history.extend([f"User: {user_input}", f"Bot: {primary_text}"])
            if len(self.history) > self._max_history:
                self.history = self.history[-self._max_history :]

            try:
                return self._generate(
                    self.critic_model_name,
                    CRITIC_SYSTEM_PROMPT,
                    f"Review the following response for hallucinations, errors, or unsafe content:\n\n{primary_text}",
                )
            except (ConnectionError, TimeoutError, RuntimeError) as exc:
                return f"{primary_text}\n\n[critic unavailable: {type(exc).__name__}]"

        except (ConnectionError, TimeoutError, RuntimeError) as exc:
            return self._offline_fallback(user_input, exc)

    # ------------------------------------------------------------------
    # Streaming agent turn (yields chunks after tools are resolved)
    # ------------------------------------------------------------------

    def agent_turn_stream(self, user_input, tools_enabled=True, max_iterations=3):
        """Execute tools synchronously, then stream the final response."""
        if not tools_enabled:
            yield from self.think_stream(user_input)
            return

        tool_prompt = build_tool_prompt()
        iteration = 0
        context = user_input
        try:
            while iteration < max_iterations:
                iteration += 1
                if self.sdk == "google.genai":
                    history_context = "\n".join(self.history[-6:])
                    full_prompt = (
                        f"{INFJ_SYSTEM_PROMPT}\n\n{tool_prompt}\n\n"
                        f"Recent conversation:\n{history_context}\n\nUser:\n{context}"
                    )
                    response_text = self._generate(
                        self.primary_model_name, INFJ_SYSTEM_PROMPT, full_prompt
                    )
                else:
                    full_prompt = f"{tool_prompt}\n\nUser:\n{context}"
                    response_text = self._generate(
                        self.primary_model_name, INFJ_SYSTEM_PROMPT, full_prompt
                    )

                tool_calls = extract_tool_calls(response_text)
                if not tool_calls:
                    primary_text = response_text
                    break

                results = self._execute_tools_with_timeout(tool_calls)
                tool_results = "\n\n".join(results)
                context = (
                    f"Your previous thought included tool calls. Here are the results:\n\n"
                    f"{tool_results}\n\n"
                    f"Now answer the user's original request:\n{user_input}"
                )
            else:
                primary_text = response_text

            self.history.extend([f"User: {user_input}", f"Bot: {primary_text}"])
            if len(self.history) > self._max_history:
                self.history = self.history[-self._max_history :]

            # Stream critic review (or just stream the primary text if critic fails)
            try:
                critic_prompt = f"Review the following response for hallucinations, errors, or unsafe content:\n\n{primary_text}"
                for chunk in self._generate_stream(
                    self.critic_model_name, CRITIC_SYSTEM_PROMPT, critic_prompt
                ):
                    yield chunk
            except (ConnectionError, TimeoutError, RuntimeError):
                yield primary_text

        except (ConnectionError, TimeoutError, RuntimeError) as exc:
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
        if self.sdk != "google.genai" and hasattr(self, "chat"):
            self.chat = self.primary_model.start_chat(history=[])


if __name__ == "__main__":
    try:
        brain = InfjBrain()
        print(f"Brain initialized with {brain.sdk}. Ready to think.")
    except ImportError as e:
        print(f"Initialization skipped: {e}")
