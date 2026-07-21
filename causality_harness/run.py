import json
import itertools
import os
import requests
from conditions import CONDITIONS
from state_builder import build_state
from client import call_drift
from metrics import cosine, structural_metrics

API_URL = "http://localhost:8765/api/chat"
RESET_URL = "http://localhost:8765/api/reset"

# Load prompts
with open("prompts.json", "r") as f:
    prompts = json.load(f)


# Helper to reset server state
def reset_server():
    try:
        r = requests.post(RESET_URL, timeout=10)
        r.raise_for_status()
        return True
    except Exception as e:
        print(f"Failed to reset server state: {e}")
        return False


# =====================================================================
# 1. RUN ISOLATED RESULTS (clean brain for every prompt-repetition)
# =====================================================================
print("\n=== RUNNING ISOLATED MODE (CLEAN BRAIN FOR EVERY PROMPT) ===")
isolated_results = []

for cname, condition in CONDITIONS.items():
    print(f"Running condition: {cname} (Isolated)")
    for p in prompts:
        print(f"  Prompt type: {p['type']}")

        outputs = []
        for i in range(3):  # repeated runs
            # Reset server before starting each repetition run to keep it completely isolated
            reset_server()
            state = build_state(
                condition,
                [0.1] * 7,
                0.01,
                {"needs": 0.5, "crisis": 0.2, "regulation": 0.3},
            )
            try:
                out = call_drift(API_URL, p["prompt"], state)
                outputs.append(out)
            except Exception as e:
                print(f"    Error during generation turn {i}: {e}")
                outputs.append(f"[generation_failed: {e}]")

        # pairwise similarity
        sims = []
        for a, b in itertools.combinations(outputs, 2):
            sims.append(cosine(a, b))

        avg_sim = sum(sims) / len(sims) if sims else 1.0

        result = {
            "condition": cname,
            "prompt_type": p["type"],
            "avg_similarity": avg_sim,
            "structural": [structural_metrics(o) for o in outputs],
        }
        isolated_results.append(result)

# =====================================================================
# 2. RUN CONTINUITY RESULTS (dirty state, long-term accumulation)
# =====================================================================
print("\n=== RUNNING CONTINUITY MODE (DIRTY STATE, COGNITIVE ACCUMULATION) ===")
continuity_results = []

# Reset server once at the very start of the continuity run
reset_server()

for cname, condition in CONDITIONS.items():
    print(f"Running condition: {cname} (Continuity)")
    for p in prompts:
        print(f"  Prompt type: {p['type']}")

        state = build_state(
            condition, [0.1] * 7, 0.01, {"needs": 0.5, "crisis": 0.2, "regulation": 0.3}
        )

        outputs = []
        for i in range(3):  # repeated runs (state accumulates over these turns)
            try:
                out = call_drift(API_URL, p["prompt"], state)
                outputs.append(out)
            except Exception as e:
                print(f"    Error during generation turn {i}: {e}")
                outputs.append(f"[generation_failed: {e}]")

        # pairwise similarity
        sims = []
        for a, b in itertools.combinations(outputs, 2):
            sims.append(cosine(a, b))

        avg_sim = sum(sims) / len(sims) if sims else 1.0

        result = {
            "condition": cname,
            "prompt_type": p["type"],
            "avg_similarity": avg_sim,
            "structural": [structural_metrics(o) for o in outputs],
        }
        continuity_results.append(result)

os.makedirs("results", exist_ok=True)
with open("results/raw_isolated.json", "w") as f:
    json.dump(isolated_results, f, indent=2)
with open("results/raw_continuity.json", "w") as f:
    json.dump(continuity_results, f, indent=2)

print(
    "\nCausality Harness Run Complete. Raw data dumped to results/raw_isolated.json and results/raw_continuity.json"
)
