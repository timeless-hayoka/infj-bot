from drift.core.brain import DriftBrain
from drift.core.being import get_being
from drift.core.memory import DriftMemory
from drift.core.config import DATA_DIR
import time
import json
import matplotlib.pyplot as plt
import sqlite3


def run_memory_decay_test(cycles=500):
    print(f"Starting {cycles}-cycle memory decay and limitation test...")
    brain = DriftBrain()
    being = get_being()
    # DriftMemory encapsulates sqlite databases and chroma
    memory = DriftMemory()

    # Track metrics
    history = []

    # We will simulate a continuous conversation where the user tells a story or asks things.
    prompts = [
        "Tell me about your day.",
        "What do you remember about my favorite color?",
        "I'm feeling a bit tired today.",
        "Let's work on the new project architecture.",
        "Can you summarize what we did yesterday?",
        "I just had a great coffee.",
        "Remember that time we found the bug in the unified memory?",
        "What's your current energy level?",
        "Do you think we are making progress?",
        "Here is a new fact: the capital of France is Paris.",
    ]

    start_time = time.time()

    for i in range(1, cycles + 1):
        prompt = f"Turn {i}: {prompts[i % len(prompts)]}"

        # This will trigger think(), context assembly, memory saving, and homeostasis updates
        response = brain.think(prompt, mode="companion")

        # Gather metrics
        pedi_val = getattr(being.state.pedi, "value", 0.0)
        dii_val = getattr(being.state.dii, "value", 0.0)
        energy = being.state.energy

        # Check memory count (DriftMemory uses interactions.db by default in V1, unified_memory in V2)
        count = 0
        try:
            # Check interaction DB for DriftMemory
            db_path = getattr(memory, "db_path", DATA_DIR / "interactions.db")
            with sqlite3.connect(db_path) as conn:
                res = conn.execute("SELECT COUNT(*) FROM interactions")
                if res:
                    count = res.fetchone()[0]
        except Exception:
            pass

        history.append(
            {
                "turn": i,
                "pedi": pedi_val,
                "dii": dii_val,
                "energy": energy,
                "memory_count": count,
            }
        )

        if i % 50 == 0:
            print(
                f"Cycle {i}/{cycles} | PEDI: {pedi_val:.3f} | DII: {dii_val:.3f} | Energy: {energy:.3f} | Memories: {count}"
            )

    duration = time.time() - start_time
    print(f"Completed {cycles} cycles in {duration:.2f} seconds.")

    # Save results
    out_file = DATA_DIR / "memory_decay_results.json"
    with open(out_file, "w") as f:
        json.dump(history, f, indent=2)
    print(f"Results saved to {out_file}")

    # Plot results
    turns = [h["turn"] for h in history]
    pedi = [h["pedi"] for h in history]
    dii = [h["dii"] for h in history]
    energy = [h["energy"] for h in history]
    mem_count = [h["memory_count"] for h in history]

    fig, axs = plt.subplots(3, 1, figsize=(10, 12))

    axs[0].plot(turns, pedi, label="PEDI", color="blue")
    axs[0].plot(turns, dii, label="DII", color="green")
    axs[0].set_title("Identity & Integration (PEDI/DII)")
    axs[0].set_ylabel("Score")
    axs[0].legend()

    axs[1].plot(turns, energy, label="Energy", color="orange")
    axs[1].set_title("Homeostasis Energy")
    axs[1].set_ylabel("Energy Level")
    axs[1].legend()

    axs[2].plot(turns, mem_count, label="Episodic Memories", color="purple")
    axs[2].set_title("Memory Accumulation & Pruning")
    axs[2].set_xlabel("Turn")
    axs[2].set_ylabel("Count")
    axs[2].legend()

    plt.tight_layout()
    plt.savefig(DATA_DIR / "memory_decay_plot.png")
    print(f"Plot saved to {DATA_DIR / 'memory_decay_plot.png'}")


if __name__ == "__main__":
    run_memory_decay_test(500)
