#!/usr/bin/env python3
import sys
import os
import json
from dotenv import load_dotenv

sys.path.insert(0, '/home/crexs/infj_bot')

# Load env variables explicitly
env_path = '/home/crexs/infj_bot/.env'
load_dotenv(env_path)

from infj_bot.core.brain import DriftBrain
from infj_bot.core.memory import DriftMemory
from infj_bot.core.history import ChatHistory
from infj_bot.core.commands import BotState
from infj_bot.core.plugins.goals import GoalsDB
from infj_bot.core.plugins.documents import DocumentStore
from infj_bot.core.prompt_builder import build_chat_prompt

def main():
    # Remove old trace log to start clean
    log_path = '/home/crexs/infj_bot/logs/state_trace.jsonl'
    if os.path.exists(log_path):
        os.remove(log_path)
        print("Removed old state_trace.jsonl")

    print("Instantiating components...")
    brain = DriftBrain()
    memory = DriftMemory()
    history = ChatHistory()
    state = BotState()
    goals_db = GoalsDB()
    doc_store = DocumentStore()
    
    # --- TURN 1: Math query ---
    message_1 = "what is 2 + 2?"
    print(f"\n--- TURN 1: {message_1} ---")
    prompt_1, emotion_1, dissonance_1 = build_chat_prompt(
        message_1, state, memory, goals_db=goals_db, doc_store=doc_store, prefs=state.prefs
    )
    print("Prompt 1 contains [MATH ENGINE]?", "[MATH ENGINE" in prompt_1)
    
    output_1 = brain.agent_turn(prompt_1, tools_enabled=True, raw_user_input=message_1, mode=state.mode)
    print(f"Agent response 1: {output_1}")
    
    # --- TURN 2: Non-math query ---
    message_2 = "tell me a short 1-sentence joke."
    print(f"\n--- TURN 2: {message_2} ---")
    prompt_2, emotion_2, dissonance_2 = build_chat_prompt(
        message_2, state, memory, goals_db=goals_db, doc_store=doc_store, prefs=state.prefs
    )
    print("Prompt 2 contains [MATH ENGINE]?", "[MATH ENGINE" in prompt_2)
    
    output_2 = brain.agent_turn(prompt_2, tools_enabled=True, raw_user_input=message_2, mode=state.mode)
    print(f"Agent response 2: {output_2}")

    # --- VERIFICATION ---
    print("\n--- VERIFICATION ---")
    if os.path.exists(log_path):
        with open(log_path, 'r') as f:
            lines = f.readlines()
            print(f"Total log lines written: {len(lines)}")
            for idx, line in enumerate(lines, 1):
                data = json.loads(line)
                print(f"Turn {idx} logged: turn={data.get('turn')} prompt_length={data.get('prompt_length')} response_length={data.get('response_length')}")
    else:
        print("Error: state_trace.jsonl not created!")

if __name__ == "__main__":
    main()
