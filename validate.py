#!/usr/bin/env python3
"""
DRIFT Validation Harness

Measures response latency, Phi, homeostatic state, and degradation under load.
Two modes:
  --mode conversational : paced cycles with delay between turns (normal load)
  --mode stress         : hammered cycles with no delay (load testing)

Outputs structured JSON lines to stdout; intended to be piped through tee.
"""

import argparse
import json
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime
from typing import Dict, List, Optional

BASE_URL = "http://127.0.0.1:8765"


def api_health() -> Optional[Dict]:
    try:
        with urllib.request.urlopen(f"{BASE_URL}/api/health", timeout=5) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        return {"error": str(e)}


def api_phi() -> Optional[Dict]:
    try:
        with urllib.request.urlopen(f"{BASE_URL}/api/phi", timeout=5) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        return {"error": str(e)}


def api_chat(message: str) -> tuple:
    """Returns (response_dict, latency_seconds)."""
    start = time.perf_counter()
    try:
        req = urllib.request.Request(
            f"{BASE_URL}/api/chat",
            data=json.dumps({"message": message}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = json.loads(resp.read().decode())
            latency = time.perf_counter() - start
            return body, latency
    except urllib.error.HTTPError as e:
        latency = time.perf_counter() - start
        return {"error": f"HTTP {e.code}", "reply": ""}, latency
    except Exception as e:
        latency = time.perf_counter() - start
        return {"error": str(e), "reply": ""}, latency


def run_cycle(cycle_num: int, message: str, mode: str) -> Dict:
    """Run one validation cycle and return metrics."""
    time.time()

    # Hit health before chat
    health_before = api_health()

    # Send chat message
    chat_body, latency = api_chat(message)

    # Hit health after chat
    health_after = api_health()

    # Hit phi endpoint
    phi_data = api_phi()

    record = {
        "cycle": cycle_num,
        "mode": mode,
        "timestamp": datetime.now().isoformat(),
        "message": message,
        "latency_seconds": round(latency, 3),
        "timed_out": latency >= 59.0,
        "http_error": "error" in chat_body and not chat_body.get("reply"),
        "reply_length": len(chat_body.get("reply", "")),
        "health_before": health_before,
        "health_after": health_after,
        "phi": phi_data,
    }
    return record


def conversational_run(cycles: int, delay: float = 2.0) -> List[Dict]:
    """Paced conversational test with delays between turns."""
    results = []
    messages = [
        "Hello, how are you feeling today?",
        "What do you remember about our last conversation?",
        "Tell me something that surprised you recently.",
        "How would you describe your current mood?",
        "What are you thinking about right now?",
        "Can you reflect on something you learned?",
        "What do you value most in a conversation?",
        "How do you handle stress?",
        "What makes you feel connected?",
        "Describe your inner world.",
    ]
    for i in range(cycles):
        msg = messages[i % len(messages)]
        record = run_cycle(i + 1, msg, "conversational")
        results.append(record)

        # Print immediate feedback
        status = "TIMEOUT" if record["timed_out"] else f"{record['latency_seconds']:.2f}s"
        phi_val = "N/A"
        if record.get("phi") and "phi" in record["phi"]:
            phi_val = f"{record['phi']['phi']:.2f}"
        needs = "N/A"
        if record.get("phi") and "needs" in record["phi"]:
            n = record["phi"]["needs"]
            e = n.get('energy', {}).get('level', 0) if isinstance(n.get('energy'), dict) else n.get('energy', 0)
            c = n.get('coherence', {}).get('level', 0) if isinstance(n.get('coherence'), dict) else n.get('coherence', 0)
            itg = n.get('integration', {}).get('level', 0) if isinstance(n.get('integration'), dict) else n.get('integration', 0)
            needs = f"E:{e:.2f} C:{c:.2f} I:{itg:.2f}"

        print(f"[CONV] cycle {int(i+1):3d}/{cycles} | latency {status:>8s} | phi {phi_val:>6s} | needs {needs}", flush=True)

        if not record["timed_out"] and delay > 0:
            time.sleep(delay)
    return results


def stress_run(cycles: int) -> List[Dict]:
    """Hammered stress test with no delay between turns."""
    results = []
    messages = [
        "Hello",
        "What?",
        "Why?",
        "How?",
        "Tell me",
        "Go on",
        "Explain",
        "Again",
        "More",
        "Continue",
    ]
    for i in range(cycles):
        msg = messages[i % len(messages)]
        record = run_cycle(i + 1, msg, "stress")
        results.append(record)

        status = "TIMEOUT" if record["timed_out"] else f"{record['latency_seconds']:.2f}s"
        phi_val = "N/A"
        if record.get("phi") and "phi" in record["phi"]:
            phi_val = f"{record['phi']['phi']:.2f}"
        needs = "N/A"
        if record.get("phi") and "needs" in record["phi"]:
            n = record["phi"]["needs"]
            e = n.get('energy', {}).get('level', 0) if isinstance(n.get('energy'), dict) else n.get('energy', 0)
            c = n.get('coherence', {}).get('level', 0) if isinstance(n.get('coherence'), dict) else n.get('coherence', 0)
            needs = f"E:{e:.2f} C:{c:.2f}"

        print(f"[STRESS] cycle {int(i+1):3d}/{cycles} | latency {status:>8s} | phi {phi_val:>6s} | needs {needs}", flush=True)
    return results


def summarize(results: List[Dict]) -> Dict:
    """Compute summary statistics."""
    latencies = [r["latency_seconds"] for r in results if not r["timed_out"] and not r.get("http_error")]
    timeouts = sum(1 for r in results if r["timed_out"])
    http_errors = sum(1 for r in results if r.get("http_error"))
    total = len(results)

    # Find degradation point (first timeout or latency > 2x median)
    degradation_point = None
    if latencies:
        median_lat = sorted(latencies)[len(latencies) // 2]
        for i, r in enumerate(results):
            if r["timed_out"]:
                degradation_point = i + 1
                break
            if r["latency_seconds"] > median_lat * 2:
                degradation_point = i + 1
                break

    # Phi tracking
    phi_values = []
    for r in results:
        if r.get("phi") and "phi" in r["phi"]:
            phi_values.append(r["phi"]["phi"])

    # Energy tracking
    energy_values = []
    for r in results:
        if r.get("phi") and "needs" in r["phi"]:
            ev = r["phi"]["needs"].get("energy", 0)
            if isinstance(ev, dict):
                ev = ev.get("level", 0)
            energy_values.append(ev)

    return {
        "total_cycles": total,
        "timeouts": timeouts,
        "http_errors": http_errors,
        "success_rate": round((total - timeouts - http_errors) / total, 3) if total else 0,
        "avg_latency": round(sum(latencies) / len(latencies), 3) if latencies else None,
        "min_latency": round(min(latencies), 3) if latencies else None,
        "max_latency": round(max(latencies), 3) if latencies else None,
        "median_latency": round(sorted(latencies)[len(latencies) // 2], 3) if latencies else None,
        "degradation_point": degradation_point,
        "phi_values": phi_values,
        "energy_values": energy_values,
    }


def main():
    parser = argparse.ArgumentParser(description="DRIFT Validation Harness")
    parser.add_argument("--cycles", type=int, default=20, help="Number of cycles to run")
    parser.add_argument("--mode", choices=["conversational", "stress"], default="conversational",
                        help="Test mode: conversational (paced) or stress (hammered)")
    parser.add_argument("--delay", type=float, default=2.0, help="Delay between cycles in conversational mode")
    args = parser.parse_args()

    # Verify server is up
    print("[*] Checking server health...")
    health = api_health()
    if health is None or "error" in health:
        print(f"[!] Server not responding at {BASE_URL}")
        print(f"    Health check returned: {health}")
        sys.exit(1)
    print(f"[+] Server OK: turns={health.get('turns', '?')}, memory={health.get('memory_count', '?')}, mode={health.get('mode', '?')}")
    print("")

    print(f"[*] Starting {args.mode} run: {args.cycles} cycles")
    print("=" * 80)

    if args.mode == "conversational":
        results = conversational_run(args.cycles, delay=args.delay)
    else:
        results = stress_run(args.cycles)

    print("=" * 80)
    summary = summarize(results)

    print("\n=== SUMMARY ===")
    print(f"Mode:              {args.mode}")
    print(f"Total cycles:      {summary['total_cycles']}")
    print(f"Timeouts:          {summary['timeouts']}")
    print(f"HTTP errors:       {summary.get('http_errors', 0)}")
    print(f"Success rate:      {summary['success_rate']:.1%}")
    if summary['avg_latency']:
        print(f"Avg latency:       {summary['avg_latency']:.2f}s")
        print(f"Min latency:       {summary['min_latency']:.2f}s")
        print(f"Max latency:       {summary['max_latency']:.2f}s")
        print(f"Median latency:    {summary['median_latency']:.2f}s")
    print(f"Degradation point: cycle {summary['degradation_point']}" if summary['degradation_point'] else "Degradation point: none detected")
    if summary['phi_values']:
        print(f"Phi range:         {min(summary['phi_values']):.2f} — {max(summary['phi_values']):.2f}")
    if summary['energy_values']:
        print(f"Energy range:      {min(summary['energy_values']):.2f} — {max(summary['energy_values']):.2f}")
    print("")

    # Output raw JSONL for downstream analysis
    for r in results:
        print(json.dumps(r))


if __name__ == "__main__":
    main()
