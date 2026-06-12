#!/usr/bin/env python3
"""
GSM8K Evaluation Runner for DRIFT Framework

Downloads OpenAI's trusted GSM8K test dataset, queries the running bot API,
extracts final numeric answers, compares them against the ground truth,
and outputs validation metrics.
"""

import json
import urllib.request
import urllib.error
import argparse
import time
import os
import re
import sys
from pathlib import Path

GSM8K_URL = "https://raw.githubusercontent.com/openai/grade-school-math/master/grade_school_math/data/test.jsonl"
CACHE_PATH = Path("/home/crexs/infj_bot/data/gsm8k_test.jsonl")
RESULTS_PATH = Path("/home/crexs/infj_bot/evals/gsm8k_results.jsonl")

def download_dataset():
    """Download GSM8K test dataset if not cached."""
    if CACHE_PATH.exists():
        print(f"[*] Found cached GSM8K test dataset at {CACHE_PATH}")
        return
    
    print(f"[*] Downloading GSM8K test dataset from {GSM8K_URL}...")
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    try:
        urllib.request.urlretrieve(GSM8K_URL, CACHE_PATH)
        print(f"[+] Download complete. Saved to {CACHE_PATH}")
    except Exception as e:
        print(f"[!] Failed to download dataset: {e}")
        sys.exit(1)

def extract_numeric_answer(text: str) -> str:
    """Extract numeric answer from text. Looks for #### <number> first, then falls back."""
    text = text.strip()
    if "####" in text:
        parts = text.split("####")
        ans = parts[-1].strip()
        ans = ans.replace(",", "").replace("$", "").replace("%", "").strip()
        match = re.search(r"[-+]?\d*\.\d+|\d+", ans)
        if match:
            return match.group(0)
            
    # Fallback to the last number in the text
    numbers = re.findall(r"[-+]?\d*\.\d+|\d+", text)
    if numbers:
        return numbers[-1].replace(",", "").replace("$", "").strip()
    return ""

def query_bot(api_url: str, message: str) -> str:
    """Send chat message to the bot API and return the reply."""
    chat_req = urllib.request.Request(
        f"{api_url}/api/chat",
        data=json.dumps({"message": message}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    try:
        with urllib.request.urlopen(chat_req, timeout=120) as resp:
            resp_data = json.loads(resp.read().decode())
            return resp_data.get("reply", "")
    except Exception as e:
        print(f"[!] API query error: {e}")
        return f"ERROR: {e}"

def reset_session(api_url: str):
    """Reset the bot session."""
    reset_req = urllib.request.Request(
        f"{api_url}/api/command",
        data=json.dumps({"command": "reset", "args": ""}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    try:
        with urllib.request.urlopen(reset_req, timeout=10) as resp:
            resp.read()
    except Exception as e:
        print(f"[!] Warning: Failed to reset bot session: {e}")

def main():
    parser = argparse.ArgumentParser(description="Run GSM8K Evaluation on DRIFT bot")
    parser.add_argument('--limit', type=int, default=50, help='Number of questions to evaluate')
    parser.add_argument('--api_url', type=str, default='http://127.0.0.1:8765', help='Bot API URL')
    parser.add_argument('--delay', type=float, default=6.0, help='Delay between queries to respect rate limits')
    args = parser.parse_args()

    # 1. Ensure dataset is available
    download_dataset()

    # 2. Read dataset
    instances = []
    with open(CACHE_PATH, 'r') as f:
        for line in f:
            if line.strip():
                instances.append(json.loads(line))
    
    print(f"[*] Loaded {len(instances)} questions from GSM8K test set.")
    
    # 3. Select subset (deterministic selection, first N instances)
    limit = min(args.limit, len(instances))
    test_set = instances[:limit]
    print(f"[*] Starting evaluation on {limit} questions...")

    # Ensure results folder exists
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    
    correct_count = 0
    results = []

    with open(RESULTS_PATH, 'w') as out_f:
        for idx, entry in enumerate(test_set):
            question = entry['question']
            ref_solution = entry['answer']
            ref_numeric = extract_numeric_answer(ref_solution)
            
            print(f"\n[{idx+1}/{limit}] Question: {question[:80]}...")
            
            # Reset session for clean computation state
            reset_session(args.api_url)
            
            # Format prompt asking for step-by-step mathematical reasoning
            prompt = (
                "Solve the following grade-school math problem step-by-step. "
                "End your answer with the final numeric result after '#### ' (e.g. '#### 42').\n\n"
                f"Question: {question}\n"
                "Answer:"
            )
            
            start_time = time.time()
            bot_reply = query_bot(args.api_url, prompt)
            latency = time.time() - start_time
            
            hyp_numeric = extract_numeric_answer(bot_reply)
            
            # Check correctness
            is_correct = (hyp_numeric == ref_numeric)
            if is_correct:
                correct_count += 1
                status_str = "✅ CORRECT"
            else:
                status_str = "❌ INCORRECT"
                
            print(f"    Expected: {ref_numeric} | Got: {hyp_numeric} | {status_str} | Latency: {latency:.2f}s")
            
            # Log full details
            log_entry = {
                "question_id": f"gsm8k_{idx+1}",
                "question": question,
                "ref_solution": ref_solution,
                "ref_numeric": ref_numeric,
                "hypothesis": bot_reply,
                "hyp_numeric": hyp_numeric,
                "is_correct": is_correct,
                "latency": round(latency, 2)
            }
            results.append(log_entry)
            out_f.write(json.dumps(log_entry) + "\n")
            out_f.flush()
            
            # Sleep to respect rate limits
            if idx < limit - 1:
                time.sleep(args.delay)

    accuracy = correct_count / limit if limit > 0 else 0
    print("\n" + "=" * 60)
    print("GSM8K EVALUATION COMPLETE")
    print("=" * 60)
    print(f"Accuracy:  {accuracy:.1%} ({correct_count}/{limit})")
    print(f"Saved logs to {RESULTS_PATH}")
    print("=" * 60)

if __name__ == '__main__':
    main()
