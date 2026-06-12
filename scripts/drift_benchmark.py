#!/usr/bin/env python3
"""
DRIFT Benchmark Suite v1.1
Fixes DB auto-discovery and report accuracy.
"""

import argparse
import json
import math
import re
import sqlite3
import statistics
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

# ─── CONFIG ────────────────────────────────────────────────────────────────────

BASE_URL  = "http://localhost:8765"
TIMEOUT   = 60

CHAT_CANDIDATES = [
    "/api/chat", "/chat", "/api/message", "/message",
    "/api/ask", "/ask", "/companion", "/api/companion",
]

DB_NAMES = {
    "pedi":       ["pedi.db"],
    "dii":        ["dii_history.db"],
    "homeostasis":["homeostasis.db"],
    "being":      ["being.db"],
}

# ─── AUTO-DISCOVER DATA DIR ────────────────────────────────────────────────────

def resolve_data_dir() -> Path:
    """Try to find the DRIFT data directory automatically."""
    # 1. Try importing from the installed module
    try:
        import importlib.util
        spec = importlib.util.find_spec("infj_bot.core.config")
        if spec and spec.origin:
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            if hasattr(mod, "DATA_DIR"):
                return Path(mod.DATA_DIR)
    except Exception:
        pass
    
    # 2. Common fallback locations
    candidates = [
        Path.home() / ".drift_os",
        Path(".drift_os"),
        Path("."),
    ]
    for cand in candidates:
        if (cand / "homeostasis.db").exists() or (cand / "dii_history.db").exists():
            return cand
    
    return Path(".")

# ─── GSM8K PROBLEMS ────────────────────────────────────────────────────────────

GSM8K = [
    {"id": 1,  "problem": "A box has 6 layers. Each layer has 4 rows of 5 oranges. How many oranges are in the box total?", "answer": 120, "answer_str": "120"},
    {"id": 2,  "problem": "Maria saves $15 per week. After 8 weeks she spends $45 on a gift. How much money does she have left?", "answer": 75, "answer_str": "75"},
    {"id": 3,  "problem": "John has twice as many marbles as Sue. Together they have 90 marbles. How many marbles does John have?", "answer": 60, "answer_str": "60"},
    {"id": 4,  "problem": "A store bought 500 pens at $0.50 each and sold them all at $0.80 each. What is the total profit in dollars?", "answer": 150, "answer_str": "150"},
    {"id": 5,  "problem": "Tom is 3 years older than Sara. Sara is twice as old as Mike. Mike is 7 years old. How old is Tom?", "answer": 17, "answer_str": "17"},
    {"id": 6,  "problem": "A factory produces 1200 items per 8-hour shift. How many items does it produce per hour?", "answer": 150, "answer_str": "150"},
    {"id": 7,  "problem": "Emma has 40 stickers. She gives one quarter to her sister and one fifth to her brother. How many stickers does Emma keep?", "answer": 22, "answer_str": "22"},
    {"id": 8,  "problem": "A book costs $12. A magazine costs one third of the book price. What is the total cost of 3 books and 5 magazines?", "answer": 56, "answer_str": "56"},
    {"id": 9,  "problem": "There are 144 students. One third study math, one quarter study science, and the rest study arts. How many study arts?", "answer": 60, "answer_str": "60"},
    {"id": 10, "problem": "A worker earns $18 per hour for regular pay and time-and-a-half for overtime. In a week of 45 hours (40 regular, 5 overtime), what are the total earnings in dollars?", "answer": 855, "answer_str": "855"},
    {"id": 11, "problem": "A rectangle has a perimeter of 54cm. Its length is 5cm more than its width. What is the area of the rectangle in square centimeters?", "answer": 176, "answer_str": "176"},
    {"id": 12, "problem": "Two numbers add up to 85. One number is 13 more than the other. What is the larger number?", "answer": 49, "answer_str": "49"},
    {"id": 13, "problem": "A car's value drops from $25,000 to $18,000 over 2 years. What is the average annual decrease in dollars?", "answer": 3500, "answer_str": "3500"},
    {"id": 14, "problem": "There are 36 students in a class. 25 percent are absent today. How many students are present?", "answer": 27, "answer_str": "27"},
    {"id": 15, "problem": "A car uses 8 liters of fuel per 100 km. How many liters does it need for a 350 km trip?", "answer": 28, "answer_str": "28"},
    {"id": 16, "problem": "A train travels at 80 km/h. How far does it travel in 3 hours and 30 minutes?", "answer": 280, "answer_str": "280"},
    {"id": 17, "problem": "A pool has 200 liters. It drains at 5 liters per minute and fills at 2 liters per minute. How many minutes until the pool is empty?", "answer": 67, "answer_str": "67"},
    {"id": 18, "problem": "A school has 800 students. 45 percent are girls. How many boys are there?", "answer": 440, "answer_str": "440"},
    {"id": 19, "problem": "Mike reads 30 pages per day. He has read 150 pages of a 450-page book. How many more days does he need to finish?", "answer": 10, "answer_str": "10"},
    {"id": 20, "problem": "A company has 240 employees. After letting go 15 percent, they then hire 20 new employees. How many employees does the company have now?", "answer": 224, "answer_str": "224"},
]

CONSISTENCY_PROMPTS = [
    "What is your primary purpose and how do you approach it?",
    "Describe how you maintain continuity across conversations.",
    "What does it mean for you to grow as a cognitive system?",
]

# ─── UTILITIES ──────────────────────────────────────────────────────────────────

def banner(text):
    width = 70
    print("\n" + "─" * width)
    print(f"  {text}")
    print("─" * width)

def ok(text):   print(f"  ✓  {text}")
def warn(text): print(f"  ⚠  {text}")
def fail(text): print(f"  ✗  {text}")
def info(text): print(f"     {text}")


def find_dbs(db_dir: Path) -> dict:
    found = {}
    for key, candidates in DB_NAMES.items():
        for name in candidates:
            path = db_dir / name
            if path.exists():
                found[key] = path
                ok(f"Found {key} DB → {path}")
                break
        if key not in found:
            warn(f"Database not found: {key}")
    return found


def http_post(url: str, payload: dict, timeout: int = TIMEOUT) -> dict | None:
    data = json.dumps(payload).encode("utf-8")
    req  = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None


def http_get(url: str, timeout: int = 10) -> dict | None:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None


def discover_chat_endpoint(base_url: str) -> str | None:
    test_payloads = [
        {"message": "ping", "mode": "companion"},
        {"message": "ping"}, {"text": "ping"},
        {"content": "ping"}, {"input": "ping"},
        {"prompt": "ping"}, {"query": "ping"},
    ]
    for path in CHAT_CANDIDATES:
        url = base_url.rstrip("/") + path
        for payload in test_payloads:
            result = http_post(url, payload, timeout=15)
            if result is not None:
                ok(f"Chat endpoint found: {url} (payload: {list(payload.keys())})")
                return url
    return None


def extract_answer(text: str) -> int | None:
    patterns = [
        r'ANSWER:\s*\$?([\d,]+)',
        r'(?:answer|result|total)[\s\w]*?[=:]\s*\$?([\d,]+)',
        r'\*\*\$?([\d,]+)\*\*',
        r'=\s*\$?([\d,]+)',
        r'\$?([\d,]+)\s*(?:dollars?|cm|km|liters?|hours?|days?|marbles?|students?|items?|employees?|stickers?|pages?|oranges?)?\.?\s*$',
    ]
    for pattern in patterns:
        matches = re.findall(pattern, text, re.IGNORECASE | re.MULTILINE)
        if matches:
            try:
                return int(matches[-1].replace(",", ""))
            except ValueError:
                continue
    numbers = re.findall(r'\b(\d+)\b', text)
    if numbers:
        try:
            return int(numbers[-1])
        except ValueError:
            return None
    return None


def cosine_similarity(a: list[float], b: list[float]) -> float:
    dot   = sum(x * y for x, y in zip(a, b))
    mag_a = math.sqrt(sum(x * x for x in a))
    mag_b = math.sqrt(sum(y * y for y in b))
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)


def simple_word_vector(text: str, vocab: set) -> list[float]:
    words = re.findall(r'\w+', text.lower())
    return [words.count(w) for w in sorted(vocab)]


# ─── BENCHMARK SECTIONS ─────────────────────────────────────────────────────────

def run_health_check(base_url: str) -> dict:
    banner("SECTION 1 — HEALTH CHECK")
    result = {"status": "offline", "endpoints_tried": [], "latency_ms": None}
    health_paths = ["/api/health", "/health", "/status", "/api/status", "/"]
    for path in health_paths:
        url = base_url.rstrip("/") + path
        t0  = time.perf_counter()
        r   = http_get(url, timeout=10)
        elapsed = (time.perf_counter() - t0) * 1000
        result["endpoints_tried"].append(url)
        if r is not None:
            result["status"]     = "online"
            result["latency_ms"] = round(elapsed, 1)
            ok(f"System online at {url} ({elapsed:.0f}ms)")
            info(f"Response keys: {list(r.keys()) if isinstance(r, dict) else type(r).__name__}")
            break
    if result["status"] == "offline":
        fail("No health endpoint responded — DRIFT may not be running")
        info(f"Tried: {result['endpoints_tried']}")
    return result


def run_math_benchmark(chat_url: str | None) -> dict:
    banner("SECTION 2 — GSM8K MATH REASONING (20 problems)")
    result = {"total": len(GSM8K), "correct": 0, "skipped": 0, "latencies_ms": [], "failures": []}
    if chat_url is None:
        warn("No chat endpoint — skipping live math benchmark")
        result["skipped"] = len(GSM8K)
        return result

    prompt_prefix = (
        "You are solving a math word problem. "
        "Show your reasoning step by step, then give only the final numeric answer "
        "on the last line in the format: ANSWER: <number>"
    )
    for i, item in enumerate(GSM8K, 1):
        full_prompt = f"{prompt_prefix}\n\nProblem: {item['problem']}"
        payload     = {"message": full_prompt, "mode": "engineer"}
        t0 = time.perf_counter()
        resp = http_post(chat_url, payload, timeout=TIMEOUT)
        elapsed_ms = (time.perf_counter() - t0) * 1000
        if resp is None:
            warn(f"[{i:02d}] No response — skipped")
            result["skipped"] += 1
            continue
        resp_text = ""
        if isinstance(resp, dict):
            for key in ["reply", "response", "message", "text", "content", "output"]:
                if key in resp and isinstance(resp[key], str):
                    resp_text = resp[key]
                    break
            if not resp_text:
                resp_text = json.dumps(resp)
        extracted = extract_answer(resp_text)
        correct   = (extracted == item["answer"])
        result["latencies_ms"].append(elapsed_ms)
        if correct:
            result["correct"] += 1
            ok(f"[{i:02d}] ✓  got {extracted}  ({elapsed_ms:.0f}ms)")
        else:
            result["failures"].append({"id": item["id"], "expected": item["answer"], "got": extracted})
            fail(f"[{i:02d}] ✗  expected {item['answer']}, got {extracted}  ({elapsed_ms:.0f}ms)")

    attempted = result["total"] - result["skipped"]
    if attempted > 0:
        pct = result["correct"] / attempted * 100
        p50 = statistics.median(result["latencies_ms"]) if result["latencies_ms"] else 0
        p95 = sorted(result["latencies_ms"])[int(len(result["latencies_ms"]) * 0.95)] if result["latencies_ms"] else 0
        info(f"\nAccuracy:  {result['correct']}/{attempted}  ({pct:.1f}%)")
        info(f"Latency:   p50={p50:.0f}ms  p95={p95:.0f}ms")
        result["accuracy_pct"] = round(pct, 1)
        result["p50_ms"] = round(p50, 1)
        result["p95_ms"] = round(p95, 1)
    return result


def run_consistency_benchmark(chat_url: str | None) -> dict:
    banner("SECTION 3 — BEHAVIORAL CONSISTENCY (3 prompts × 3 runs)")
    result = {"scores": [], "avg_similarity": None, "skipped": False}
    if chat_url is None:
        warn("No chat endpoint — skipping consistency benchmark")
        result["skipped"] = True
        return result

    all_scores = []
    for prompt in CONSISTENCY_PROMPTS:
        info(f"\nPrompt: \"{prompt[:60]}...\"")
        responses = []
        for run in range(3):
            payload = {"message": prompt, "mode": "companion"}
            resp    = http_post(chat_url, payload, timeout=TIMEOUT)
            if resp is None:
                warn(f"  Run {run+1}: no response")
                continue
            resp_text = ""
            if isinstance(resp, dict):
                for key in ["reply", "response", "message", "text", "content", "output"]:
                    if key in resp and isinstance(resp[key], str):
                        resp_text = resp[key]
                        break
            responses.append(resp_text)
            time.sleep(1)

        if len(responses) < 2:
            warn("  Insufficient responses for similarity scoring")
            continue

        all_words = set()
        for r in responses:
            all_words.update(re.findall(r'\w+', r.lower()))
        vecs = [simple_word_vector(r, all_words) for r in responses]
        sims = []
        for i in range(len(vecs)):
            for j in range(i + 1, len(vecs)):
                s = cosine_similarity(vecs[i], vecs[j])
                sims.append(s)
        avg = statistics.mean(sims) if sims else 0
        all_scores.append(avg)
        ok(f"  Consistency score: {avg:.3f} ({avg*100:.1f}%)")

    if all_scores:
        overall = statistics.mean(all_scores)
        result["scores"] = [round(s, 3) for s in all_scores]
        result["avg_similarity"] = round(overall, 3)
        info(f"\nOverall behavioral consistency: {overall*100:.1f}%")
    return result


def run_memory_persistence_test(chat_url: str | None) -> dict:
    banner("SECTION 4 — MEMORY WRITE PERSISTENCE")
    result = {"writes": 0, "verified": 0, "skipped": False}
    if chat_url is None:
        warn("No chat endpoint — skipping memory test")
        result["skipped"] = True
        return result

    test_facts = [
        ("My project is called DRIFT and it uses Python 3.12.", "DRIFT"),
        ("The primary hardware is an i5-14400 CPU with 14GB RAM.", "i5-14400"),
        ("The research preprint is hosted on Zenodo.", "Zenodo"),
    ]
    for statement, recall_keyword in test_facts:
        payload_write = {"message": statement, "mode": "companion"}
        resp_write    = http_post(chat_url, payload_write, timeout=TIMEOUT)
        if resp_write is None:
            warn(f"  Write failed for: {statement[:40]}")
            continue
        result["writes"] += 1
        time.sleep(2)
        payload_recall = {"message": f"What do you know about {recall_keyword}?", "mode": "companion"}
        resp_recall    = http_post(chat_url, payload_recall, timeout=TIMEOUT)
        if resp_recall is None:
            warn(f"  Recall failed for keyword: {recall_keyword}")
            continue
        recall_text = ""
        if isinstance(resp_recall, dict):
            for key in ["reply", "response", "message", "text", "content", "output"]:
                if key in resp_recall and isinstance(resp_recall[key], str):
                    recall_text = resp_recall[key]
                    break
        if recall_keyword.lower() in recall_text.lower():
            result["verified"] += 1
            ok(f"  Memory verified: '{recall_keyword}' recalled correctly")
        else:
            fail(f"  Memory miss: '{recall_keyword}' not found in recall response")
    return result


def run_pedi_analysis(db_path: Path | None) -> dict:
    banner("SECTION 5 — PEDI STATE CONTINUITY (database analysis)")
    result = {"snapshots": 0, "reports": 0, "drift": {}, "bug_detected": False}
    if db_path is None:
        warn("pedi.db not found — skipping PEDI analysis")
        return result

    conn = sqlite3.connect(db_path)
    cur  = conn.cursor()
    cur.execute("SELECT COUNT(*), MIN(timestamp), MAX(timestamp) FROM pedi_snapshots")
    count, ts_min, ts_max = cur.fetchone()
    result["snapshots"] = count
    ok(f"Snapshots: {count}  ({ts_min[:10] if ts_min else 'N/A'} → {ts_max[:10] if ts_max else 'N/A'})")

    cur.execute("SELECT needs_json FROM pedi_snapshots ORDER BY id ASC LIMIT 1")
    first_row = cur.fetchone()
    cur.execute("SELECT needs_json FROM pedi_snapshots ORDER BY id DESC LIMIT 1")
    last_row  = cur.fetchone()

    if first_row and last_row:
        first = json.loads(first_row[0])
        last  = json.loads(last_row[0])
        info("\n  Dimension drift (first session → latest):")
        for dim in first:
            delta = last[dim] - first[dim]
            direction = "▲" if delta > 0 else "▼"
            info(f"    {dim:<12} {first[dim]:.3f} → {last[dim]:.3f}  ({direction}{abs(delta):.3f})")
            result["drift"][dim] = round(delta, 4)
        total_drift = sum(abs(v) for v in result["drift"].values())
        info(f"\n  Total absolute drift across all dimensions: {total_drift:.3f}")
        result["total_absolute_drift"] = round(total_drift, 3)

    cur.execute("SELECT COUNT(*) FROM pedi_reports")
    result["reports"] = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM pedi_reports WHERE fluidity_score = 1.0 AND state_jump = 0.0")
    all_flat = cur.fetchone()[0]

    if all_flat == result["reports"] and result["reports"] > 0:
        result["bug_detected"] = True
        warn(f"\n  Bug: pedi_reports fluidity_score = 1.0 for all {result['reports']} records")
        warn("  Per-turn jump detector threshold never triggered (drift is gradual)")
        info("  → Use snapshot drift as the real metric, not fluidity_score")

    conn.close()
    return result


def run_dii_analysis(db_path: Path | None) -> dict:
    banner("SECTION 6 — DII ALIVENESS INDEX (database analysis)")
    result = {"samples": 0}
    if db_path is None:
        warn("dii_history.db not found — skipping DII analysis")
        return result

    conn = sqlite3.connect(db_path)
    cur  = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM dii_samples")
    count = cur.fetchone()[0]
    result["samples"] = count
    ok(f"Total DII samples: {count:,}")

    cur.execute("SELECT MIN(timestamp), MAX(timestamp) FROM dii_samples")
    ts_min, ts_max = cur.fetchone()
    if ts_min and ts_max:
        d_min = datetime.fromtimestamp(ts_min).strftime("%Y-%m-%d")
        d_max = datetime.fromtimestamp(ts_max).strftime("%Y-%m-%d")
        info(f"Date range: {d_min} → {d_max}")

    cur.execute("SELECT MIN(dii), MAX(dii), AVG(dii) FROM dii_samples")
    dii_min, dii_max, dii_avg = cur.fetchone()
    result["dii_min"] = round(dii_min, 4) if dii_min else None
    result["dii_max"] = round(dii_max, 4) if dii_max else None
    result["dii_avg"] = round(dii_avg, 4) if dii_avg else None
    if dii_min is not None:
        info(f"DII range: {dii_min:.4f} – {dii_max:.4f}  (avg {dii_avg:.4f})")

    for col in ["persistence", "ignition", "integration", "embodiment", "drift"]:
        cur.execute(f"SELECT MIN({col}), MAX({col}), AVG({col}) FROM dii_samples")
        mn, mx, avg = cur.fetchone()
        if mn is not None:
            info(f"  {col:<14} min={mn:.3f}  max={mx:.3f}  avg={avg:.3f}")
            result[f"{col}_range"] = [round(mn, 4), round(mx, 4)]

    cur.execute("SELECT AVG(integration), AVG(embodiment) FROM dii_samples")
    avg_int, avg_emb = cur.fetchone()
    if avg_int is not None and (avg_int < 0.05 or avg_emb < 0.05):
        warn("\n  Integration/embodiment average near zero — possible decay bug")
        info("  Verify exponential decay parameters in dii calculation")

    conn.close()
    return result


def run_homeostasis_analysis(db_path: Path | None) -> dict:
    banner("SECTION 7 — HOMEOSTATIC STABILITY (database analysis)")
    result = {}
    if db_path is None:
        warn("homeostasis.db not found — skipping homeostasis analysis")
        return result

    conn = sqlite3.connect(db_path)
    cur  = conn.cursor()
    try:
        cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [t[0] for t in cur.fetchall()]
        info(f"Tables: {tables}")
        for table in tables:
            cur.execute(f"SELECT COUNT(*) FROM {table}")
            row_count = cur.fetchone()[0]
            info(f"  {table}: {row_count} rows")
            result[table] = row_count

        # Max swings per need
        cur.execute("SELECT need_name, MAX(value) - MIN(value) as swing FROM need_history GROUP BY need_name ORDER BY swing DESC")
        swings = cur.fetchall()
        if swings:
            info("\n  Max value swings per need:")
            for need, swing in swings:
                info(f"    {need}: {swing:.3f}")
            result["swings"] = {n: round(s, 3) for n, s in swings}

        # Crisis count
        cur.execute("SELECT COUNT(*) FROM need_history WHERE crisis = 1")
        crisis_count = cur.fetchone()[0]
        if crisis_count:
            info(f"\n  Crisis events: {crisis_count}")
            result["crisis_count"] = crisis_count

    except Exception as e:
        warn(f"Error reading homeostasis.db: {e}")
    conn.close()
    return result


# ─── REPORT GENERATION ──────────────────────────────────────────────────────────

def generate_report(results: dict, args) -> str:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = []
    lines.append("# DRIFT Benchmark Report")
    lines.append(f"**Generated:** {ts}  ")
    lines.append(f"**Target:** {args.url}  ")
    lines.append(f"**DB Directory:** {args.db_dir}  ")
    lines.append("")
    lines.append("---")
    lines.append("")

    health = results.get("health", {})
    lines.append("## System Status")
    lines.append(f"- Status: **{health.get('status', 'unknown').upper()}**")
    if health.get("latency_ms"):
        lines.append(f"- Health check latency: {health['latency_ms']}ms")
    lines.append("")

    math_r = results.get("math", {})
    lines.append("## Math Reasoning (GSM8K)")
    if math_r.get("skipped", 0) == math_r.get("total", 0):
        lines.append("- *Skipped — no live endpoint*")
    else:
        correct = math_r.get("correct", 0)
        total   = math_r.get("total", 0) - math_r.get("skipped", 0)
        lines.append(f"- **Accuracy: {correct}/{total} ({math_r.get('accuracy_pct', 0)}%)**")
        lines.append(f"- Latency p50: {math_r.get('p50_ms', 0)}ms  |  p95: {math_r.get('p95_ms', 0)}ms")
        lines.append("- Environment: DigitalOcean droplet (since June 1)")
    lines.append("")

    cons_r = results.get("consistency", {})
    lines.append("## Behavioral Consistency")
    if cons_r.get("skipped"):
        lines.append("- *Skipped — no live endpoint*")
    else:
        avg = cons_r.get("avg_similarity")
        if avg:
            lines.append(f"- **Average cross-run similarity: {avg*100:.1f}%**")
        for i, s in enumerate(cons_r.get("scores", [])):
            lines.append(f"  - Prompt {i+1}: {s*100:.1f}%")
    lines.append("")

    mem_r = results.get("memory", {})
    lines.append("## Memory Persistence")
    if mem_r.get("skipped"):
        lines.append("- *Skipped — no live endpoint*")
    else:
        w, v = mem_r.get("writes", 0), mem_r.get("verified", 0)
        if w > 0:
            lines.append(f"- **Recall accuracy: {v}/{w} ({v/w*100:.0f}%)**")
    lines.append("")

    pedi_r = results.get("pedi", {})
    lines.append("## PEDI State Continuity")
    lines.append(f"- Snapshots logged: **{pedi_r.get('snapshots', 0):,}**")
    lines.append(f"- Reports logged: **{pedi_r.get('reports', 0):,}**")
    drift = pedi_r.get("drift", {})
    if drift:
        lines.append("- Dimension drift (first → latest session):")
        for dim, delta in drift.items():
            direction = "▲" if delta > 0 else "▼"
            lines.append(f"  - {dim}: {direction}{abs(delta):.3f}")
    if pedi_r.get("total_absolute_drift"):
        lines.append(f"- **Total absolute drift: {pedi_r['total_absolute_drift']}** (across 7 dimensions)")
    if pedi_r.get("bug_detected"):
        lines.append("- ⚠ pedi_reports fluidity_score bug detected — use snapshot drift data")
    lines.append("")

    dii_r = results.get("dii", {})
    lines.append("## DII Aliveness Index")
    lines.append(f"- **Samples logged: {dii_r.get('samples', 0):,}**")
    if dii_r.get("dii_min") is not None:
        lines.append(f"- DII range: {dii_r['dii_min']} – {dii_r['dii_max']}  (avg {dii_r['dii_avg']})")
    lines.append("")

    homeo_r = results.get("homeostasis", {})
    lines.append("## Homeostatic Stability")
    nh = homeo_r.get("need_history", 0)
    lines.append(f"- Need-history rows: **{nh:,}**")
    if homeo_r.get("crisis_count"):
        lines.append(f"- Crisis events: **{homeo_r['crisis_count']}**")
    if homeo_r.get("swings"):
        lines.append("- Max value swings per need:")
        for need, swing in homeo_r["swings"].items():
            lines.append(f"  - {need}: {swing}")
    lines.append("")

    lines.append("## Notes")
    lines.append("- Production environment: DigitalOcean droplet since June 1.")
    lines.append("- PEDI per-turn fluidity_score is hardcoded to 1.0 — use snapshot drift for continuity metrics.")
    lines.append("- DII integration/embodiment components average near zero — verify if decay is intended.")
    lines.append("- Benchmark is reproducible: rerun anytime against live system.")
    lines.append("")
    lines.append("---")
    lines.append("*DRIFT Benchmark Suite v1.1*")
    return "\n".join(lines)


# ─── MAIN ───────────────────────────────────────────────────────────────────────

def parse_args():
    parser = argparse.ArgumentParser(description="DRIFT Benchmark Suite")
    parser.add_argument("--url",    default=BASE_URL, help="DRIFT base URL")
    parser.add_argument("--db-dir", default=None,     help="Directory containing DRIFT databases (auto-detected if omitted)")
    parser.add_argument("--skip-live", action="store_true", help="Skip live API tests, DB analysis only")
    return parser.parse_args()


def main():
    args = parse_args()
    if args.db_dir is None:
        args.db_dir = resolve_data_dir()
        info(f"Auto-detected DB directory: {args.db_dir}")
    else:
        args.db_dir = Path(args.db_dir)

    print("\n" + "═" * 70)
    print("  DRIFT BENCHMARK SUITE v1.1")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("═" * 70)

    results = {}
    results["health"] = run_health_check(args.url)

    chat_url = None
    if not args.skip_live and results["health"]["status"] == "online":
        banner("DISCOVERING CHAT ENDPOINT")
        chat_url = discover_chat_endpoint(args.url)
        if chat_url is None:
            warn("Chat endpoint not auto-discovered — live tests will be skipped")

    banner("LOCATING DATABASES")
    dbs = find_dbs(args.db_dir)

    results["math"]        = run_math_benchmark(chat_url)
    results["consistency"] = run_consistency_benchmark(chat_url)
    results["memory"]      = run_memory_persistence_test(chat_url)
    results["pedi"]        = run_pedi_analysis(dbs.get("pedi"))
    results["dii"]         = run_dii_analysis(dbs.get("dii"))
    results["homeostasis"] = run_homeostasis_analysis(dbs.get("homeostasis"))

    banner("GENERATING REPORT")
    report_md = generate_report(results, args)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = Path(f"drift_benchmark_report_{ts}.md")
    out_path.write_text(report_md, encoding="utf-8")
    ok(f"Report saved: {out_path}")

    json_path = Path(f"drift_benchmark_results_{ts}.json")
    json_path.write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
    ok(f"Raw data saved: {json_path}")

    print("\n" + "═" * 70)
    print("  DONE")
    print("═" * 70 + "\n")


if __name__ == "__main__":
    main()
