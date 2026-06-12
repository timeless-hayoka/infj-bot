import sys
import os
import asyncio

# Ensure project root is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from drift.core.brain import DriftBrain
from drift.core.global_workspace import get_workspace
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
print("[TRACE] Initializing GlobalWorkspace...")
workspace = get_workspace()

raw_active_state = {
    "coherence": 0.8,
    "resonance": 0.8,
    "tension": 0.2,
    "shadow_depth": 0.2
}
user_input = "Tell me about your current state of structural coherence."

def generate_response_func(u_input, _regulated_state):
    print("[TRACE] Inside generate_response_func. Assembling prompt...")
    prompt, emotion, dissonance = orchestrator.assemble_prompt(
        u_input,
        state,
        memory
    )
    print(f"[TRACE] Prompt assembled. Assembled prompt length: {len(prompt)}")
    print("[TRACE] Calling brain.agent_turn...")
    output = brain.agent_turn(prompt, tools_enabled=True)
    print(f"[TRACE] brain.agent_turn returned output of length: {len(output)}")
    return output

async def main():
    print("[TRACE] Calling execute_cli_cycle...")
    output, regulated_state, status = await asyncio.to_thread(
        workspace.execute_cli_cycle,
        raw_active_state,
        user_input,
        generate_response_func
    )
    print("[TRACE] execute_cli_cycle completed successfully!")
    print(f"[TRACE] Output: {output}")

if __name__ == "__main__":
    asyncio.run(main())
