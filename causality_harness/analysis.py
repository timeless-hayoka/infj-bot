import json
import statistics

def load_isolated():
    return json.load(open("results/raw_isolated.json"))

def load_continuity():
    return json.load(open("results/raw_continuity.json"))

def compute_ces(data):
    grouped = {}
    for r in data:
        key = r["condition"]
        grouped.setdefault(key, []).append(r["avg_similarity"])

    ces = {}
    for k, vals in grouped.items():
        ces[k] = 1 - statistics.mean(vals)
    return ces

def print_section(title, ces):
    baseline = ces.get("A_BASELINE", 0.0)
    print(f"\n{title}")
    print("--------------------------------")
    for k, v in ces.items():
        print(f"{k}: {v:.3f} (Δ vs baseline {v - baseline:+.3f})")

def print_report(title, ces):
    print(f"\n{title} REPORT")
    print("="*40)
    for k, v in ces.items():
        if v < 0.1:
            label = "NO EFFECT"
        elif v < 0.3:
            label = "WEAK COUPLING"
        elif v < 0.6:
            label = "PARTIAL INTEGRATION"
        else:
            label = "STRONG CAUSAL DRIVER"
        print(f"{k}: {v:.3f} → {label}")

if __name__ == "__main__":
    try:
        isolated_data = load_isolated()
        isolated_ces = compute_ces(isolated_data)
        
        continuity_data = load_continuity()
        continuity_ces = compute_ces(continuity_data)
        
        print_section("ISOLATED CAUSALITY IMPACT SCORES", isolated_ces)
        print_report("ISOLATED CAUSALITY", isolated_ces)
        
        print_section("CONTINUITY CAUSALITY IMPACT SCORES", continuity_ces)
        print_report("CONTINUITY CAUSALITY", continuity_ces)
        
    except FileNotFoundError:
        print("Error: results/raw_isolated.json or results/raw_continuity.json not found. Run run.py first.")
