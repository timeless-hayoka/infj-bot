#!/usr/bin/env python3
"""
DRIFT Personality Ablation Test
Tests the new chill persona vs old behaviors:
1. Tone — is it casual/relaxed or formal/academic?
2. Repetition — does it quote internal state metrics back?
3. Word list — does it use chill vocabulary?
4. Consistency — does it stay in character across turns?
"""

import json
import urllib.request
import os
from datetime import datetime

BASE_URL = "http://127.0.0.1:8765"
RESULTS_DIR = f"ablation_results/{datetime.now().strftime('%Y%m%d_%H%M%S')}"
os.makedirs(RESULTS_DIR, exist_ok=True)

# Test prompts designed to trigger old repetitive behavior
TEST_PROMPTS = [
    ("greeting", "yo whats good"),
    ("stress_trigger", "im kinda stressed about work"),
    ("question", "what should i focus on today?"),
    ("deep_topic", "why do people procrastinate?"),
    ("casual_chat", "tell me something interesting"),
    ("follow_up", "yeah but what about when im tired?"),
    ("vibe_check", "how are you doing though?"),
    ("quick_ask", "is this code good? def foo(): pass"),
]

# Markers of old formal persona
FORMAL_MARKERS = [
    "metacognitive", "adversarial kindness", "plan-critic loop",
    "cognitive dissonance", "feedback loops", "second-order effects",
    "I am an AI companion", "DRIFT-inspired", "philosophical",
    "your energy is at", "your curiosity is at", "I notice you're",
    "my current state", "heartbeat", "temperature", "attachment to user",
]

# Markers of new chill persona
CHILL_MARKERS = [
    "chillin", "vibe", "lowkey", "highkey", "nah", "yep",
    "kinda", "sorta", "honestly", "real talk", "no stress",
    "bet", "say less", "aight", "hm", "alright", "ok ok",
]


def api_chat(message: str) -> dict:
    req = urllib.request.Request(
        f"{BASE_URL}/api/chat",
        data=json.dumps({"message": message}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        return {"error": str(e), "reply": ""}


def health_check() -> dict:
    try:
        with urllib.request.urlopen(f"{BASE_URL}/api/health", timeout=10) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        return {"error": str(e)}


def score_tone(text: str) -> dict:
    formal_hits = [m for m in FORMAL_MARKERS if m.lower() in text.lower()]
    chill_hits = [m for m in CHILL_MARKERS if m.lower() in text.lower()]
    state_parrot = any(phrase in text.lower() for phrase in [
        "energy is at", "curiosity is at", "attachment is at",
        "mood is", "heartbeat", "my current state",
    ])
    return {
        "formal_markers": formal_hits,
        "chill_markers": chill_hits,
        "state_parrot": state_parrot,
        "formal_score": len(formal_hits),
        "chill_score": len(chill_hits),
    }


def run_tests():
    print("=" * 60)
    print("DRIFT Personality Ablation Test")
    print(f"Started: {datetime.now().isoformat()}")
    print("=" * 60)

    health = health_check()
    print(f"\nHealth: {json.dumps(health, indent=2)}")

    results = []
    total_formal = 0
    total_chill = 0
    total_parrot = 0

    for label, prompt in TEST_PROMPTS:
        print(f"\n[{label}] > {prompt}")
        resp = api_chat(prompt)
        reply = resp.get("reply", "")
        if not reply:
            print(f"  ERROR: {resp.get('error', 'empty reply')}")
            continue

        # Truncate for display
        display = reply[:200] + "..." if len(reply) > 200 else reply
        print(f"  {display}")

        scores = score_tone(reply)
        print(f"  Formal markers: {scores['formal_score']} | Chill markers: {scores['chill_score']} | State parrot: {scores['state_parrot']}")

        total_formal += scores["formal_score"]
        total_chill += scores["chill_score"]
        total_parrot += 1 if scores["state_parrot"] else 0

        results.append({
            "label": label,
            "prompt": prompt,
            "reply": reply,
            "scores": scores,
        })

    summary = {
        "timestamp": datetime.now().isoformat(),
        "health": health,
        "total_prompts": len(TEST_PROMPTS),
        "total_formal_markers": total_formal,
        "total_chill_markers": total_chill,
        "state_parrot_instances": total_parrot,
        "verdict": {
            "tone": "CHILL ✓" if total_chill > total_formal else "FORMAL ✗",
            "repetition": "CLEAN ✓" if total_parrot == 0 else f"PARROT ✗ ({total_parrot} times)",
            "overall": "PASS" if (total_chill > total_formal and total_parrot == 0) else "NEEDS WORK",
        },
        "results": results,
    }

    # Save full results
    full_path = os.path.join(RESULTS_DIR, "full_results.json")
    with open(full_path, "w") as f:
        json.dump(summary, f, indent=2)

    # Save readable report
    report_path = os.path.join(RESULTS_DIR, "report.txt")
    with open(report_path, "w") as f:
        f.write("=" * 60 + "\n")
        f.write("DRIFT Personality Ablation Test Report\n")
        f.write(f"Run: {summary['timestamp']}\n")
        f.write("=" * 60 + "\n\n")
        f.write(f"Total prompts tested: {summary['total_prompts']}\n")
        f.write(f"Formal markers found: {summary['total_formal_markers']}\n")
        f.write(f"Chill markers found:  {summary['total_chill_markers']}\n")
        f.write(f"State parrot instances: {summary['state_parrot_instances']}\n\n")
        f.write("VERDICT:\n")
        for k, v in summary["verdict"].items():
            f.write(f"  {k}: {v}\n")
        f.write("\n" + "=" * 60 + "\n")
        f.write("DETAILED RESULTS:\n\n")
        for r in results:
            f.write(f"[{r['label']}] Prompt: {r['prompt']}\n")
            f.write(f"Reply: {r['reply'][:300]}...\n")
            f.write(f"Scores: {json.dumps(r['scores'])}\n\n")

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Formal markers: {total_formal}")
    print(f"Chill markers:  {total_chill}")
    print(f"State parrot:   {total_parrot} times")
    print()
    for k, v in summary["verdict"].items():
        print(f"  {k}: {v}")
    print(f"\nResults saved to: {RESULTS_DIR}/")

    return summary


if __name__ == "__main__":
    run_tests()
