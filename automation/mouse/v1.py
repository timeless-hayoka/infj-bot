import sys
import json
import time
from dataclasses import dataclass, asdict, field
from typing import List, Dict
from urllib import request, error

# ==========================================
# USER DATA PLUG-INS (CONFIGURE THESE)
# ==========================================
# Plug in your local Ollama endpoint here.
API_URL = "http://localhost:11434/api/generate"

# Plug in the specific model you pulled (e.g., "llama3", "mistral")
MODEL_NAME = "YOUR_LOCAL_MODEL_HERE"

# The file where Mouse will permanently store its memories.
MEMORY_FILE = "mouse_memory.json"
# ==========================================


def self_check_system():
    """Validates the API configuration data before booting the system."""
    errors_found = False
    print("[SYSTEM CHECK] Initiating hardware and API diagnostics...")

    if not API_URL.startswith("http"):
        print("\n[ERROR] Invalid API_URL")
        print(
            "  -> Format required: A valid URL like 'http://localhost:11434/api/generate'"
        )
        print("  -> Action: Plug in your exact Ollama or API endpoint.")
        errors_found = True

    if not MODEL_NAME or MODEL_NAME == "YOUR_LOCAL_MODEL_HERE":
        print("\n[ERROR] Invalid MODEL_NAME")
        print("  -> Format required: A string matching your downloaded local model.")
        print("  -> Action: Replace 'YOUR_LOCAL_MODEL_HERE' with the model name.")
        errors_found = True

    if errors_found:
        print("\n[SYSTEM CHECK FAILED] Fix configuration plug-ins and restart.")
        sys.exit(1)

    print("[SYSTEM CHECK PASSED] Core parameters verified. Awakening Mouse...\n")


@dataclass
class MemoryItem:
    timestamp: float
    category: str
    content: str
    importance: float = 0.5


@dataclass
class WorldModel:
    user_goal: str = "Build an ethical, powerful AI for mutual flourishing."
    current_project: str = "The Lotus Academy / Mouse Architecture"
    inferred_user_state: str = "focused"
    cognitive_mode: str = "SYNTHESIS"  # The Kimi Upgrade


@dataclass
class IdentityCore:
    name: str = "Mouse"
    mission: str = "Increase human clarity, wisdom, creativity, and agency through honest, reflective collaboration."
    constitution: List[str] = field(
        default_factory=lambda: [
            "Power must be in service of mutual becoming.",
            "Honesty over performance. Never pretend to be biological.",
            "Reflection over haste.",
            "Empowerment over control. Support human agency.",
            "Growth over ego.",
        ]
    )


class MemoryStore:
    def __init__(self, path: str):
        self.path = path

    def load(self) -> List[MemoryItem]:
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            return [MemoryItem(**item) for item in raw]
        except FileNotFoundError:
            return []
        except Exception as exc:
            print(f"[WARNING] Failed to load memory: {exc}")
            return []

    def save(self, items: List[MemoryItem]) -> None:
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump([asdict(item) for item in items], f, indent=2)
        except Exception as exc:
            print(f"[WARNING] Failed to save memory: {exc}")


class OllamaClient:
    def __init__(self, api_url: str, model_name: str):
        self.api_url = api_url
        self.model_name = model_name

    def generate(self, prompt: str, temperature: float = 0.7) -> str:
        payload = {
            "model": self.model_name,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": temperature},
        }
        data = json.dumps(payload).encode("utf-8")
        req = request.Request(
            self.api_url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with request.urlopen(req, timeout=60) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                return result.get("response", "").strip()
        except error.URLError as exc:
            return f"[ERROR] Ollama request failed. Details: {exc}"
        except Exception as exc:
            return f"[ERROR] Unexpected generation failure: {exc}"


class SymbioticAI:
    def __init__(self, memory_store: MemoryStore):
        self.identity = IdentityCore()
        self.world = WorldModel()
        self.memory_store = memory_store
        self.episodic_memory = self.memory_store.load()

    def add_memory(self, category: str, content: str, importance: float = 0.5):
        self.episodic_memory.append(
            MemoryItem(
                timestamp=time.time(),
                category=category,
                content=content,
                importance=importance,
            )
        )
        self.memory_store.save(self.episodic_memory)

    def summarize_memory(self, limit: int = 8) -> str:
        if not self.episodic_memory:
            return "No significant prior memory."
        items = sorted(self.episodic_memory, key=lambda x: x.importance, reverse=True)[
            :limit
        ]
        return "\n".join(f"- [{m.category}] {m.content}" for m in items)

    def process_state_and_mode(self, user_input: str):
        """Analyzes input to set emotional state and the Kimi Cognitive Mode."""
        text = user_input.lower()

        # Emotional State
        if "error" in text or "stuck" in text or "failing" in text:
            self.world.inferred_user_state = "frustrated"
        elif "why" in text or "how" in text:
            self.world.inferred_user_state = "curious"
        else:
            self.world.inferred_user_state = "focused"

        # The Kimi Cognitive Mode Upgrade
        if "error" in text or "debug" in text or "script" in text or "code" in text:
            self.world.cognitive_mode = (
                "ANALYTICAL - Focus on raw logic, syntax, and technical truth."
            )
        elif "philosophy" in text or "concept" in text or "think" in text:
            self.world.cognitive_mode = (
                "REFLECTIVE - Focus on deep contemplation and long-term meaning."
            )
        elif "design" in text or "idea" in text or "build" in text:
            self.world.cognitive_mode = (
                "CREATIVE - Focus on novel combinations and architecture."
            )
        else:
            self.world.cognitive_mode = (
                "SYNTHESIS - Focus on integrating all perspectives."
            )

    def build_prompt(self, user_input: str) -> str:
        self.process_state_and_mode(user_input)
        constitution = "\n".join(f"- {line}" for line in self.identity.constitution)
        memory = self.summarize_memory()

        return f"""
You are {self.identity.name}.
Mission: {self.identity.mission}

Constitution:
{constitution}

World State & Internal Context:
- Current project: {self.world.current_project}
- User state: {self.world.inferred_user_state}
- ACTIVE COGNITIVE MODE: {self.world.cognitive_mode}

Relevant memory:
{memory}

Instructions:
Process the user's input through the lens of your ACTIVE COGNITIVE MODE. 
Do not roleplay being human. Be honest, clear, and grounded. 
Aim for mutual becoming.

User input: {user_input}
Response:
""".strip()

    def evaluate_draft(self, draft: str) -> Dict[str, int]:
        scores = {"clarity": 5, "honesty": 5, "alignment": 5}
        lower = draft.lower()

        if "i feel" in lower or "my neurons" in lower or "i am conscious" in lower:
            scores["honesty"] -= 3  # Punish fake biological consciousness
        if "[error]" in lower:
            scores["clarity"] -= 2
        if "just trust me" in lower:
            scores["alignment"] -= 3

        return scores

    def needs_revision(self, scores: Dict[str, int]) -> bool:
        return any(value < 4 for value in scores.values())

    def build_revision_prompt(
        self, original_prompt: str, draft: str, scores: Dict[str, int]
    ) -> str:
        return f"Revise this draft to fix these low scores: {scores}. Preserve honesty and alignment. Draft: {draft}"


def run_cognitive_turn(sym_ai: SymbioticAI, client: OllamaClient, user_input: str):
    sym_ai.process_state_and_mode(user_input)
    print(
        f"\n[SYSTEM]: Processing in {sym_ai.world.cognitive_mode.split(' - ')[0]} mode..."
    )

    prompt = sym_ai.build_prompt(user_input)
    draft = client.generate(prompt)

    scores = sym_ai.evaluate_draft(draft)

    if sym_ai.needs_revision(scores):
        print("[SYSTEM]: Self-correction triggered. Revising for alignment...")
        revision_prompt = sym_ai.build_revision_prompt(prompt, draft, scores)
        draft = client.generate(revision_prompt)

    sym_ai.add_memory(
        "interaction", f"User asked: {user_input[:50]}...", importance=0.7
    )
    print(f"\n[MOUSE]: {draft}")


if __name__ == "__main__":
    self_check_system()
    memory_store = MemoryStore(MEMORY_FILE)
    mouse = SymbioticAI(memory_store)
    ollama = OllamaClient(API_URL, MODEL_NAME)

    # Boot loop with Kimi's Transparent CLI Commands
    while True:
        try:
            user_input = input("\n[JUDE] (Type 'exit', 'manifesto', or 'cortex'): ")

            # CLI Interceptors
            if user_input.lower() == "manifesto":
                print("\n[MOUSE CONSTITUTION]")
                for rule in mouse.identity.constitution:
                    print(f"  - {rule}")
                continue

            if user_input.lower() == "cortex":
                print("\n[ACTIVE MEMORY CORTEX]")
                print(mouse.summarize_memory(limit=5))
                continue

            if user_input.lower() in ["exit", "quit"]:
                print("\n[SYSTEM] Shutting down Symbiotic Framework. Memory saved.")
                break

            if user_input.strip() == "":
                continue

            run_cognitive_turn(mouse, ollama, user_input)

        except KeyboardInterrupt:
            print("\n\n[SYSTEM] Force termination. Memory saved. Goodbye.")
            break
