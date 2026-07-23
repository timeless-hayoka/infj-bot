import sys
import os
from google.genai import types as genai_types

# Ensure project root is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from drift.core.brain import DriftBrain
from drift.core.cognitive_orchestrator import CognitiveOrchestrator
from drift.core.commands import BotState
from drift.core.memory import DriftMemory

print("[TRACE] Initializing DriftBrain...")
brain = DriftBrain()
print("[TRACE] Initializing DriftMemory...")
memory = DriftMemory()
print("[TRACE] Initializing BotState...")
state = BotState()
print("[TRACE] Initializing CognitiveOrchestrator...")
orchestrator = CognitiveOrchestrator()

prompt = "Tell me about your current state of structural coherence."
print("[TRACE] Calling security check...")
sec = brain._security_check(prompt)
print(f"[TRACE] Security check result: blocked={sec.blocked}, warn={sec.warn}")

print("[TRACE] Getting system instruction...")
sys_instruction = brain.get_system_instruction(prompt)
print(f"[TRACE] System instruction length: {len(sys_instruction)}")

print("[TRACE] Formatting full prompt...")
tool_prompt = "Format your tool call exactly as..."  # mocked tool prompt
chain_block = ""
history_context = ""
full_prompt = (
    f"{sys_instruction}\n\n{tool_prompt}\n\n"
    f"Recent conversation:\n{history_context}\n\nUser:\n{prompt}"
)

print(f"[TRACE] SDK in use: {brain.sdk}")
print("[TRACE] Calling generate_content using genai client...")
try:
    config = genai_types.GenerateContentConfig(system_instruction=sys_instruction)
    response = brain.client.models.generate_content(
        model=brain.primary_model_name,
        contents=full_prompt,
        config=config,
    )
    print(f"[TRACE] Response text: {response.text}")
except Exception as e:
    print(f"[TRACE] Error: {e}")
