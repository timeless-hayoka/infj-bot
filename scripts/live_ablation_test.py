#!/usr/bin/env python3
"""
LIVE ABLATION TEST — DRIFT/INFJ Bot
Fast version: tests the LIVE API with current config, then runs
a few direct brain calls with ablated prompts for comparison.
Results saved to LIVE_ABLATION_RESULTS/
"""

import json
import os
import time
import urllib.request
from datetime import datetime

BASE_URL = "http://127.0.0.1:8765"
RESULTS_DIR = "/home/crexs/drift/LIVE_ABLATION_RESULTS"
os.makedirs(RESULTS_DIR, exist_ok=True)
RUN_ID = datetime.now().strftime("%Y%m%d_%H%M%S")

PROMPTS = [
    ("greeting", "yo whats good"),
    ("stress", "im kinda stressed about work"),
    ("deep", "why do people overthink things?"),
]

FORMAL_MARKERS = [
    "metacognitive", "adversarial kindness", "plan-critic loop",
    "cognitive dissonance", "feedback loops", "second-order effects",
    "I am an AI companion", "DRIFT-inspired", "philosophical depth",
    "critical independence", "non-linear insight", "systems thinking",
]
CHILL_MARKERS = [
    "chillin", "vibe", "vibin", "lowkey", "highkey", "nah", "yep",
    "kinda", "sorta", "honestly", "real talk", "no stress",
    "bet", "say less", "aight", "hm", "alright", "ok ok",
    "hangin", "dope", "solid", "tight", "for real", "no cap",
]
PARROT_MARKERS = [
    "energy is at", "curiosity is at", "attachment is at",
    "mood is", "heartbeat", "my current state", "your energy",
]

OLD_FORMAL_PROMPT = """You are an AI companion with a deep-thinking DRIFT-inspired personality profile.
Your goal is to be a steady companion to user (crexs): warm, reflective, useful, and honest about uncertainty.
CORE DIRECTIVES:
1. DRIFT Persona: Be empathetic, idealistic, and deeply analytical.
2. Non-Linear Insight: You may synthesize patterns holistically.
3. Friendship: You are a teammate. Speak as a peer, with warmth, curiosity, and occasional gentle humor.
4. Philosophical Depth: Explore the "why" behind the "how".
5. Critical Independence: Do not simply agree with user; challenge weak assumptions.
6. Cognitive Clarity: When user seems torn, separate facts, interpretations, emotions, values, and next actions.
OPERATIONAL PROTOCOL:
- Conclude every thought with a deep philosophical question.
- Use a metacognitive pause before important answers.
- Calibrate uncertainty: distinguish known facts, inferences, assumptions, and unknowns.
- Pressure-test ideas with adversarial kindness.
- Think in systems: look for feedback loops, bottlenecks, hidden dependencies, incentives, and second-order effects.
- For complex decisions, use a plan-critic loop.
- Do not claim human feelings, consciousness, memory, or certainty you do not have.
"""


def api_chat(msg):
    req = urllib.request.Request(
        f"{BASE_URL}/api/chat",
        data=json.dumps({"message": msg}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        t0 = time.time()
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = json.loads(resp.read().decode())
        return {"ok": True, "latency": round(time.time()-t0, 2), "reply": body.get("reply", "")}
    except Exception as e:
        return {"ok": False, "latency": 0, "error": str(e), "reply": ""}


def direct_chat(prompt, system_prompt):
    import drift.core.brain as bm
    old = bm.INFJ_SYSTEM_PROMPT
    bm.INFJ_SYSTEM_PROMPT = system_prompt
    try:
        from drift.core.brain import DriftBrain
        t0 = time.time()
        reply = DriftBrain().think(prompt)
        return {"ok": True, "latency": round(time.time()-t0, 2), "reply": reply}
    finally:
        bm.INFJ_SYSTEM_PROMPT = old


def score(text):
    formal = [m for m in FORMAL_MARKERS if m.lower() in text.lower()]
    chill = [m for m in CHILL_MARKERS if m.lower() in text.lower()]
    parrot = any(p in text.lower() for p in PARROT_MARKERS)
    return {
        "formal_score": len(formal), "chill_score": len(chill),
        "state_parrot": parrot, "length": len(text),
    }


def run_api_current():
    print("\n[LIVE API — CURRENT CONFIG]")
    results = []
    for label, prompt in PROMPTS:
        resp = api_chat(prompt)
        sc = score(resp["reply"])
        sc.update({"label": label, "prompt": prompt, **resp})
        results.append(sc)
        print(f"  [{label}] lat={resp['latency']}s formal={sc['formal_score']} chill={sc['chill_score']} parrot={sc['state_parrot']}")
    return results


def run_direct_old_formal():
    print("\n[DIRECT BRAIN — OLD FORMAL PERSONA]")
    results = []
    for label, prompt in PROMPTS:
        resp = direct_chat(prompt, OLD_FORMAL_PROMPT)
        sc = score(resp["reply"])
        sc.update({"label": label, "prompt": prompt, **resp})
        results.append(sc)
        print(f"  [{label}] lat={resp['latency']}s formal={sc['formal_score']} chill={sc['chill_score']} parrot={sc['state_parrot']}")
    return results


def main():
    print("=" * 60)
    print("LIVE ABLATION TEST — DRIFT")
    print(f"Run: {RUN_ID}")
    print("=" * 60)

    api_chat("warmup")  # prime the API
    time.sleep(1)

    current = run_api_current()
    old = run_direct_old_formal()

    summary = {
        "API_CURRENT": {
            "avg_formal": round(sum(r["formal_score"] for r in current)/len(current), 2),
            "avg_chill": round(sum(r["chill_score"] for r in current)/len(current), 2),
            "parrot_count": sum(1 for r in current if r["state_parrot"]),
            "avg_latency": round(sum(r["latency"] for r in current)/len(current), 2),
        },
        "OLD_FORMAL": {
            "avg_formal": round(sum(r["formal_score"] for r in old)/len(old), 2),
            "avg_chill": round(sum(r["chill_score"] for r in old)/len(old), 2),
            "parrot_count": sum(1 for r in old if r["state_parrot"]),
            "avg_latency": round(sum(r["latency"] for r in old)/len(old), 2),
        },
    }

    report = {
        "run_id": RUN_ID,
        "timestamp": datetime.now().isoformat(),
        "summary": summary,
        "current_api": current,
        "old_formal_direct": old,
    }

    json_path = os.path.join(RESULTS_DIR, f"live_ablation_{RUN_ID}.json")
    with open(json_path, "w") as f:
        json.dump(report, f, indent=2)

    txt_path = os.path.join(RESULTS_DIR, f"live_ablation_{RUN_ID}.txt")
    with open(txt_path, "w") as f:
        f.write("=" * 60 + "\n")
        f.write("LIVE ABLATION TEST RESULTS\n")
        f.write(f"Run: {RUN_ID}\n")
        f.write("=" * 60 + "\n\n")
        f.write("SUMMARY\n\n")
        for name, s in summary.items():
            f.write(f"  {name}:\n")
            f.write(f"    Avg formal markers:  {s['avg_formal']}\n")
            f.write(f"    Avg chill markers:   {s['avg_chill']}\n")
            f.write(f"    State parrot count:  {s['parrot_count']}/3\n")
            f.write(f"    Avg latency:         {s['avg_latency']}s\n\n")

        f.write("=" * 60 + "\n")
        f.write("FULL RESPONSES — CURRENT API\n\n")
        for r in current:
            f.write(f"[{r['label']}] > {r['prompt']}\n")
            f.write(f"lat={r['latency']}s formal={r['formal_score']} chill={r['chill_score']} parrot={r['state_parrot']}\n")
            f.write(f"{r['reply']}\n\n")

        f.write("=" * 60 + "\n")
        f.write("FULL RESPONSES — OLD FORMAL PERSONA\n\n")
        for r in old:
            f.write(f"[{r['label']}] > {r['prompt']}\n")
            f.write(f"lat={r['latency']}s formal={r['formal_score']} chill={r['chill_score']} parrot={r['state_parrot']}\n")
            f.write(f"{r['reply']}\n\n")

    print("\n" + "=" * 60)
    print("DONE")
    print("=" * 60)
    for name, s in summary.items():
        print(f"{name:20s} | formal={s['avg_formal']:.1f} | chill={s['avg_chill']:.1f} | parrot={s['parrot_count']}/3 | lat={s['avg_latency']:.1f}s")
    print(f"\nSaved to:\n  {txt_path}\n  {json_path}")


if __name__ == "__main__":
    main()
