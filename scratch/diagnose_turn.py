#!/usr/bin/env python3
import sys
import time
from dotenv import load_dotenv

sys.path.insert(0, '/home/crexs/drift')

# Load env variables explicitly
env_path = '/home/crexs/drift/.env'
load_dotenv(env_path)

from drift.core.brain import DriftBrain
from drift.core.memory import DriftMemory
from drift.core.commands import BotState
from drift.core.plugins.goals import GoalsDB
from drift.core.plugins.documents import DocumentStore
from drift.core.prompt_builder import build_chat_prompt

def run_diagnostic(msg):
    print(f"\nRunning diagnostic for query: {msg}")
    
    brain = DriftBrain()
    memory = DriftMemory()
    state = BotState()
    goals_db = GoalsDB()
    doc_store = DocumentStore()

    t0 = time.time()
    prompt, emotion, dissonance = build_chat_prompt(
        msg, state, memory, goals_db=goals_db, doc_store=doc_store, prefs=state.prefs
    )
    t1 = time.time()
    print(f"  Prompt built in {t1-t0:.3f}s. Contains [MATH ENGINE]?", "[MATH ENGINE" in prompt)

    t2 = time.time()
    output = brain.agent_turn(prompt, tools_enabled=True, raw_user_input=msg, mode=state.mode)
    t3 = time.time()
    print(f"  Agent turn executed in {t3-t2:.3f}s.")
    print(f"  Response: {output}")

if __name__ == "__main__":
    # Test simple arithmetic query
    run_diagnostic("what is 123 * 456?")
