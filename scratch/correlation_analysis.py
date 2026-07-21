#!/usr/bin/env python3
import sys
import time
from dotenv import load_dotenv

sys.path.insert(0, "/home/crexs/drift")

# Load env variables explicitly
env_path = "/home/crexs/drift/.env"
load_dotenv(env_path)

from drift.core.brain import DriftBrain
from drift.core.memory import DriftMemory
from drift.core.history import ChatHistory
from drift.core.commands import BotState
from drift.core.plugins.goals import GoalsDB
from drift.core.plugins.documents import DocumentStore
from drift.core.prompt_builder import build_chat_prompt

PROMPTS = [
    "hello",
    "what is 123 * 456?",
    "explain general relativity in 3 bullet points",
    "calculate 1/2 + 1/4 + 1/8",
    "write a short poem about coding in the middle of the night",
    "what is 2**8?",
    "tell me a quick joke",
    "what is the derivative of x**3 with respect to x?",
    "explain the difference between tcp and udp",
    "calculate sqrt(256) * 2",
    "describe the main cause of the fall of the roman empire in one short paragraph",
    "what is 10 / 0?",
]


def generate_logs():
    print("Generating simulated conversation logs...")
    brain = DriftBrain()
    memory = DriftMemory()
    history = ChatHistory()
    state = BotState()
    goals_db = GoalsDB()
    doc_store = DocumentStore()

    for idx, msg in enumerate(PROMPTS, 1):
        print(f"Turn {idx}/{len(PROMPTS)}: {msg}")
        prompt, emotion, dissonance = build_chat_prompt(
            msg,
            state,
            memory,
            goals_db=goals_db,
            doc_store=doc_store,
            prefs=state.prefs,
        )
        # Run turn
        output = brain.agent_turn(
            prompt, tools_enabled=True, raw_user_input=msg, mode=state.mode
        )
        print(f"  -> Response length: {len(output)}")
        time.sleep(0.5)


def analyze_correlations():
    print("\nLoading trajectory dataframe...")
    from core.trajectory import load_dataframe

    df = load_dataframe("logs/state_trace.jsonl")
    if df is None or df.empty:
        print("Error: DataFrame is empty or could not be loaded!")
        return

    print(f"Successfully loaded DataFrame with {len(df)} rows.")

    # Flatten nested fields
    df["energy_val"] = df["state"].apply(lambda x: x.get("energy"))
    df["fatigue_val"] = df["state"].apply(lambda x: x.get("fatigue"))
    df["dii_val"] = df["state"].apply(lambda x: x.get("dii"))
    df["wall_ms"] = df["timing"].apply(lambda x: x.get("wall_ms"))

    print("\n--- Correlation Analysis ---")

    # Pearson correlations
    corr_energy_prompt = df["energy_val"].corr(df["prompt_length"])
    corr_fatigue_resp = df["fatigue_val"].corr(df["response_length"])
    corr_dii_resp = df["dii_val"].corr(df["response_length"])
    corr_energy_wall = df["energy_val"].corr(df["wall_ms"])

    print(f"Correlation (Energy vs Prompt Length): {corr_energy_prompt:.4f}")
    print(f"Correlation (Fatigue vs Response Length): {corr_fatigue_resp:.4f}")
    print(f"Correlation (DII vs Response Length): {corr_dii_resp:.4f}")
    print(f"Correlation (Energy vs Latency/wall_ms): {corr_energy_wall:.4f}")

    # Describe variables
    print("\n--- Summary Statistics ---")
    print(
        df[
            [
                "prompt_length",
                "response_length",
                "energy_val",
                "fatigue_val",
                "dii_val",
                "wall_ms",
            ]
        ].describe()
    )


if __name__ == "__main__":
    generate_logs()
    analyze_correlations()
