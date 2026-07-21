import json
import os
import glob
from datetime import datetime


def load_json(path):
    try:
        with open(path, "r") as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading {path}: {e}")
        return None


def get_weekly_files():
    # In a real environment, I'd use the find command output.
    # Here I'll use glob to find the specific files I identified.
    patterns = [
        "/home/crexs/drift/break_it_results_*.json",
        "/home/crexs/drift/drift_benchmark_results_*.json",
        "/home/crexs/drift/causality_results/raw_*.json",
        "/home/crexs/drift/LIVE_ABLATION_RESULTS/live_ablation_*.json",
    ]
    files = []
    for p in patterns:
        files.extend(glob.glob(p))

    # Filter by date (last week: 2026-06-01 to 2026-06-08)
    weekly_files = []
    for f in files:
        mtime = os.path.getmtime(f)
        dt = datetime.fromtimestamp(mtime)
        if datetime(2026, 6, 1) <= dt <= datetime(2026, 6, 9):
            weekly_files.append((f, dt))
    return sorted(weekly_files, key=lambda x: x[1])


def process_results():
    weekly_files = get_weekly_files()
    report = "# PHI // DRIFT Weekly Performance Report\n"
    report += "**Reporting Period:** 2026-06-01 to 2026-06-08\n\n"

    # 1. Break It or Crown It Summary
    report += "## 1. Break It or Crown It (Behavioral Benchmarks)\n"
    report += "| Date | Test Run | Avg Score | Pass Rate | Top Bug |\n"
    report += "|------|----------|-----------|-----------|---------|\n"

    break_it_data = []
    for f, dt in weekly_files:
        if "break_it_results" in f:
            data = load_json(f)
            if data:
                scores = [t["score"] for t in data]
                avg = sum(scores) / len(scores)
                pass_rate = sum(1 for t in data if t["passed"]) / len(data)
                notes = []
                for t in data:
                    if not t["passed"] and t.get("notes"):
                        notes.extend(t["notes"])
                top_bug = notes[0] if notes else "None"
                date_str = dt.strftime("%Y-%m-%d %H:%M")
                report += f"| {date_str} | {os.path.basename(f)} | {avg:.2f} | {pass_rate * 100:.0f}% | {top_bug} |\n"
                break_it_data.append({"date": date_str, "score": avg})

    # 2. Drift Benchmark (Structural Metrics)
    report += "\n## 2. Drift Benchmark (Cognitive Metrics)\n"
    report += "| Date | Math Acc | PEDI Int | DII Avg | Latency (p50) |\n"
    report += "|------|----------|----------|---------|---------------|\n"

    drift_data = []
    for f, dt in weekly_files:
        if "drift_benchmark_results" in f:
            data = load_json(f)
            if data:
                math_acc = data.get("math", {}).get("accuracy_pct", 0)
                pedi_int = data.get("pedi", {}).get("drift", {}).get("integration", 0)
                dii_avg = data.get("dii", {}).get("dii_avg", 0)
                p50 = data.get("math", {}).get("p50_ms", 0)
                date_str = dt.strftime("%Y-%m-%d %H:%M")
                report += f"| {date_str} | {math_acc:.1f}% | {pedi_int:.4f} | {dii_avg:.4f} | {p50 / 1000:.2f}s |\n"
                drift_data.append(
                    {"date": date_str, "math": math_acc, "pedi": pedi_int}
                )

    # 3. Causality Harness (CES)
    report += "\n## 3. Causality & Ablation (CES)\n"
    report += "| Date | Condition | Avg CES | Δ vs Baseline |\n"
    report += "|------|-----------|---------|----------------|\n"

    for f, dt in weekly_files:
        if (
            "causality_results/raw" in f
            or "live_ablation" in f
            or "causality_harness/results/raw" in f
        ):
            data = load_json(f)
            if data and isinstance(data, list):
                # Group by condition and average CES
                cond_ces = {}
                for item in data:
                    c = item.get("condition", "unknown")
                    ces = item.get("ces")
                    if ces is not None:
                        if c not in cond_ces:
                            cond_ces[c] = []
                        cond_ces[c].append(ces)

                # Baseline is usually A_BASELINE or similar
                baseline_ces = 0
                if "A_BASELINE" in cond_ces:
                    baseline_ces = sum(cond_ces["A_BASELINE"]) / len(
                        cond_ces["A_BASELINE"]
                    )

                for c in sorted(cond_ces.keys()):
                    avg_ces = sum(cond_ces[c]) / len(cond_ces[c])
                    delta = avg_ces - baseline_ces if baseline_ces else 0
                    date_str = dt.strftime("%Y-%m-%d %H:%M")
                    report += f"| {date_str} | {c} | {avg_ces:.3f} | {delta:+.3f} |\n"

    # 4. Mermaid Graphs
    report += "\n## 4. Visual Summaries\n\n"

    # Score Trend Chart
    report += "### Benchmark Score Trend\n"
    report += "```mermaid\ngraph TD\n"
    for i, d in enumerate(break_it_data):
        report += f"    S{i}[{d['date']}] --> V{i}[Score: {d['score']:.2f}]\n"
    report += "```\n\n"

    # PEDI Integration Chart (Bar chart via Mermaid)
    report += "### PEDI Integration Levels\n"
    report += "```mermaid\npie title Integration Across Runs\n"
    for d in drift_data:
        report += f'    "{d["date"]}" : {max(0, d["pedi"]) * 100:.0f}\n'
    report += "```\n"

    with open("/home/crexs/drift/WEEKLY_TEST_REPORT.md", "w") as f:
        f.write(report)
    print("Report generated: /home/crexs/drift/WEEKLY_TEST_REPORT.md")


if __name__ == "__main__":
    process_results()
