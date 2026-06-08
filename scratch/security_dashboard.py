# scratch/security_dashboard.py
import json
from datetime import datetime
from pathlib import Path
import matplotlib.pyplot as plt
from collections import defaultdict

def generate_security_dashboard(
    log_path: str = "security_audit.jsonl", 
    last_n: int = 200,
    output_file: str = "security_dashboard.png"
):
    """Generate visualization of security events + organism state."""
    logs = []
    log_path = Path(log_path)
    
    if not log_path.exists():
        print(f"❌ Log file not found: {log_path}")
        return

    with open(log_path, 'r', encoding='utf-8') as f:
        for line in list(f)[-last_n:]:
            try:
                logs.append(json.loads(line.strip()))
            except:
                continue

    if not logs:
        print("No logs found.")
        return

    # Extract time series data
    times = []
    social_risk = []
    pedi = []
    dii = []
    shadow = []
    blocked_count = 0
    high_risk_count = 0

    for log in logs:
        try:
            ts = datetime.fromisoformat(log["ts"].replace("Z", "+00:00"))
            times.append(ts)
            social_risk.append(log.get("social_risk", 0))
            pedi.append(log.get("pedi_value", 0))
            dii.append(log.get("dii_value", 0))
            shadow.append(log.get("shadow_influence", 0))
            
            if log.get("action") == "block":
                blocked_count += 1
            if log.get("social_risk", 0) > 0.5:
                high_risk_count += 1
        except:
            continue

    # Plot
    plt.figure(figsize=(12, 8))
    plt.plot(times, social_risk, label="Social Risk", marker='o', linewidth=2)
    plt.plot(times, pedi, label="PEDI", marker='x', linewidth=2)
    plt.plot(times, dii, label="DII", marker='s', linewidth=2)
    plt.plot(times, shadow, label="Shadow Influence", marker='^', linewidth=2)
    
    plt.title("PHI/DRIFT Security Events + Organism State Over Time")
    plt.xlabel("Time")
    plt.ylabel("Score (0.0 - 1.0)")
    plt.legend()
    plt.grid(True, alpha=0.3)
    plt.xticks(rotation=45)
    plt.tight_layout()
    
    plt.savefig(output_file, dpi=200)
    print(f"✅ Dashboard saved as: {output_file}")
    print(f"Summary:")
    print(f"   • Total entries analyzed: {len(logs)}")
    print(f"   • Blocks triggered: {blocked_count}")
    print(f"   • High social risk events: {high_risk_count}")

if __name__ == "__main__":
    generate_security_dashboard()
