#!/usr/bin/env python3
import sys
import os
from dotenv import load_dotenv

sys.path.insert(0, '/home/crexs/drift')

# Load env variables explicitly
env_path = '/home/crexs/drift/.env'
print(f"Loading .env from {env_path}: {load_dotenv(env_path)}")

from drift.core.brain import DriftBrain
from drift.core.memory import DriftMemory
from drift.core.history import ChatHistory
from drift.core.commands import BotState
from drift.core.plugins.goals import GoalsDB
from drift.core.plugins.documents import DocumentStore
from drift.core.prompt_builder import build_chat_prompt

def main():
    print("Instantiating components...")
    brain = DriftBrain()
    memory = DriftMemory()
    history = ChatHistory()
    state = BotState()
    goals_db = GoalsDB()
    doc_store = DocumentStore()
    
    # Enable math engine by sending a mathematical query
    user_query = "what is 1/3 + 1/3 + 1/3?"
    print(f"\nUser query: {user_query}")
    
    # 1. Build the prompt (which triggers inject_grounded_math)
    print("\n1. Building chat prompt...")
    prompt, emotion, dissonance = build_chat_prompt(
        user_query, state, memory, goals_db=goals_db, doc_store=doc_store, prefs=state.prefs
    )
    print("Prompt built.")
    print("Does prompt contain [MATH ENGINE]? ", "[MATH ENGINE" in prompt)
    
    # 2. Run agent turn (which triggers inference, CPUSampler, critic check, and trajectory logging)
    print("\n2. Running agent turn...")
    output = brain.agent_turn(prompt, tools_enabled=True, raw_user_input=user_query, mode=state.mode)
    print(f"Agent response: {output}")
    
    # 3. Verify trajectory log
    log_path = '/home/crexs/drift/logs/state_trace.jsonl'
    print(f"\n3. Checking trajectory log at {log_path}...")
    if os.path.exists(log_path):
        print("Log exists!")
        with open(log_path, 'r') as f:
            lines = f.readlines()
            print(f"Total entries in log: {len(lines)}")
            if lines:
                print(f"Last log entry: {lines[-1].strip()}")
    else:
        print("Log does NOT exist!")

if __name__ == "__main__":
    main()
