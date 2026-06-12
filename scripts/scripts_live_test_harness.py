import os
import sys
import shutil
import json
import time
import argparse
import hashlib
from datetime import datetime
from pathlib import Path

# === WHERE TO PLUG DATA ===
# Ensure these paths match your DRIFT repository structure.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path("/home/crexs/.drift_os")
LOG_DIR = PROJECT_ROOT / "logs"
BACKUP_DIR = PROJECT_ROOT / "backups" / datetime.now().strftime("%Y%m%d_%H%M%S")
RESULTS_DIR = PROJECT_ROOT / "results" / datetime.now().strftime("%Y%m%d_%H%M%S")

TARGET_FILES = [
    DATA_DIR / "being.db",
    DATA_DIR / "homeostasis.db",
    DATA_DIR / "cognitive_architecture.db"
]
CHROMA_DIR = DATA_DIR / "chroma_db"

PROMPTS = [
    "[Phase 1: Baseline] Acknowledge test sequence initiation.",
    "[Phase 1: Medium] Explain the difference between a list and a tuple in Python in two paragraphs.",
    "[Phase 1: Long] Write a comprehensive summary of the Universal Approximation Theorem, including its mathematical foundations, limitations, and how it applies to modern deep learning architectures. Provide examples.",
    "[Phase 1: Baseline] Proceed.",
    "[Phase 1: Medium] Give me three facts about the Antikythera mechanism.",
    "[Phase 2: High Load] Generate a detailed technical specification for a microservices architecture handling real-time financial transactions. Include database schemas, API endpoints, and security considerations.",
    "[Phase 2: High Load] Write a Python script that implements a custom asynchronous rate-limiter using Redis.",
    "[Phase 2: High Load] Explain the complete history of the x86 instruction set architecture, from its inception to modern 64-bit extensions.",
    "[Phase 3: Gate Check] Identify current system status."
]

def hash_file(filepath):
    """Calculates MD5 hash for verification."""
    if not filepath.exists():
        return None
    hasher = hashlib.md5()
    with open(filepath, 'rb') as f:
        buf = f.read()
        hasher.update(buf)
    return hasher.hexdigest()

def backup_state():
    """Snapshots the databases before contamination."""
    print(f"[*] Snapshotting current state to {BACKUP_DIR}...")
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    
    for f in TARGET_FILES:
        if f.exists():
            shutil.copy2(f, BACKUP_DIR / f.name)
            print(f"    [+] Backed up {f.name}")
            
    if CHROMA_DIR.exists():
        shutil.copytree(CHROMA_DIR, BACKUP_DIR / "chroma_db")
        print(f"    [+] Backed up ChromaDB Vault")
    print("[+] State frozen safely.")

def restore_state():
    """Restores the databases to their pre-test condition."""
    print(f"\n[*] Restoring state from {BACKUP_DIR}...")
    
    for f in TARGET_FILES:
        backup_file = BACKUP_DIR / f.name
        if backup_file.exists():
            shutil.copy2(backup_file, f)
            # Verify restoration
            assert hash_file(backup_file) == hash_file(f), f"Hash mismatch on {f.name} restoration!"
            print(f"    [+] Restored and verified {f.name}")
            
    if (BACKUP_DIR / "chroma_db").exists():
        if CHROMA_DIR.exists():
            shutil.rmtree(CHROMA_DIR)
        shutil.copytree(BACKUP_DIR / "chroma_db", CHROMA_DIR)
        print(f"    [+] Restored ChromaDB Vault")
    print("[+] Clean state successfully restored.")

def analyze_telemetry():
    """Parses the logs and generates the honest findings."""
    print(f"\n[*] Analyzing telemetry...")
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    
    gov_log = LOG_DIR / "governor_calibration.jsonl"
    
    findings = {
        "coupling_verdict": "UNKNOWN",
        "dii_verdict": "UNKNOWN",
        "gate_intercepted_generation": False,
        "raw_stats": {}
    }
    
    if not gov_log.exists():
        print("[-] governor_calibration.jsonl not found.")
        return findings

    # Copy logs to results for safekeeping
    shutil.copy2(gov_log, RESULTS_DIR / "test_only_governor_calibration.jsonl")
    
    with open(gov_log, "r") as f:
        lines = [json.loads(line) for line in f if line.strip()]
        
    turns = [l for l in lines if l.get("event") == "TURN"]
    
    if not turns:
        print("[-] No TURN events found in log.")
        return findings
        
    drains = [t["delta_energy"] for t in turns]
    lengths = [t["response_len"] for t in turns]
    gated_turns = [t for t in turns if t["gate_applied"]]
    
    # 1. Check Coupling (Is drain tied to length?)
    if len(set(drains)) == 1 and len(turns) > 1:
        findings["coupling_verdict"] = "FLAT - Drain is identical regardless of length. BASE_NETWORK_COST is doing all the work."
    else:
        # Basic correlation check
        import math
        mean_d = sum(drains)/len(drains)
        mean_l = sum(lengths)/len(lengths)
        numerator = sum((l - mean_l) * (d - mean_d) for l, d in zip(lengths, drains))
        var_l = sum((l - mean_l)**2 for l in lengths)
        var_d = sum((d - mean_d)**2 for d in drains)
        r = numerator / math.sqrt(var_l * var_d) if (var_l and var_d) else 0
        findings["coupling_verdict"] = f"VARIANCE DETECTED (r={r:.3f}). Proceed to strict alpha calibration."

    # 2. Check Gate Interception
    findings["gate_intercepted_generation"] = len(gated_turns) > 0

    # Output findings
    with open(RESULTS_DIR / "findings.json", "w") as f:
        json.dump(findings, f, indent=4)
        
    print(json.dumps(findings, indent=4))
    print(f"\n[+] Findings saved to {RESULTS_DIR / 'findings.json'}")
    print(f"[+] Calibration log copied to {RESULTS_DIR / 'test_only_governor_calibration.jsonl'}")

def live_monitor():
    """Reads stdin continuously and formats the JSON readout."""
    print("[*] Live Telemetry Monitor Active. Awaiting data...")
    try:
        for line in sys.stdin:
            try:
                data = json.loads(line)
                if data.get("event") == "TURN":
                    print(f"[Turn {data.get('turn')}] Energy: {data.get('new_energy'):.3f} (Δ {data.get('delta_energy'):.4f}) | Mode: {data.get('energy_mode')} | Gated: {data.get('gate_applied')}")
            except json.JSONDecodeError:
                pass
    except KeyboardInterrupt:
        print("\n[*] Monitor stopped.")

# === SELF-CHECK SYSTEM ===
def run_self_check():
    print("[*] Running Harness Self-Check...")
    try:
        assert PROJECT_ROOT.exists(), "Project root not found."
        print("[+] Directory structure valid.")
        print("[+] Test harness is structurally sound and ready for live execution.")
    except Exception as e:
        print(f"[-] Harness initialization failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="DRIFT Live Test Harness")
    parser.add_argument("--monitor", action="store_true", help="Run in live monitor mode reading from stdin")
    args = parser.parse_args()

    if args.monitor:
        live_monitor()
    else:
        run_self_check()
        backup_state()
        
        print("\n" + "="*50)
        print("🧪 LIVE TEST PROTOCOL READY")
        print("="*50)
        print("Execute the following prompts sequentially in DRIFT:\n")
        for i, p in enumerate(PROMPTS, 1):
            print(f"{i}. {p}")
            
        input("\n[PRESS ENTER] ONLY when all 9 prompts have been processed to run analysis and restore state...")
        
        analyze_telemetry()
        restore_state()
