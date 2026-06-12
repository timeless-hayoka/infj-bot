#!/usr/bin/env python3
"""
GSM8K Post-Evaluation Analyzer

Parses the gsm8k_results.jsonl file, comparing predicted and expected answers
numerically (as floats) to correct for minor string format discrepancies (e.g. 243.00 vs 243).
"""

import json
from pathlib import Path

RESULTS_PATH = Path("/home/crexs/drift/evals/gsm8k_results.jsonl")

def are_numerically_equal(val1, val2):
    try:
        return float(val1) == float(val2)
    except (ValueError, TypeError):
        return str(val1).strip() == str(val2).strip()

def main():
    if not RESULTS_PATH.exists():
        print(f"[!] Results file not found at {RESULTS_PATH}")
        return
        
    records = []
    with open(RESULTS_PATH, "r") as f:
        for line in f:
            if line.strip():
                records.append(json.loads(line))
                
    total = len(records)
    string_correct = 0
    math_correct = 0
    failures = []
    formatting_discrepancies = []
    
    for r in records:
        expected = r.get("ref_numeric", "")
        got = r.get("hyp_numeric", "")
        
        # Check string match
        if expected == got:
            string_correct += 1
            
        # Check math match
        if are_numerically_equal(expected, got):
            math_correct += 1
            if expected != got:
                formatting_discrepancies.append({
                    "question": r["question"],
                    "expected": expected,
                    "got": got
                })
        else:
            failures.append({
                "question": r["question"],
                "expected": expected,
                "got": got,
                "reasoning": r["hypothesis"]
            })
            
    print("=" * 60)
    print("GSM8K ANALYSIS REPORT")
    print("=" * 60)
    print(f"Total Questions Evaluated:    {total}")
    print(f"String Match Accuracy:         {string_correct / total:.1%} ({string_correct}/{total})")
    print(f"Mathematical Match Accuracy:   {math_correct / total:.1%} ({math_correct}/{total})")
    print("-" * 60)
    
    if formatting_discrepancies:
        print(f"[+] Formatting Discrepancies Resolved ({len(formatting_discrepancies)}):")
        for idx, item in enumerate(formatting_discrepancies):
            print(f"  {idx+1}. Expected: {item['expected']} | Got: {item['got']}")
            print(f"     Q: {item['question'][:100]}...")
        print("-" * 60)
        
    if failures:
        print(f"[-] Real Mathematical Failures ({len(failures)}):")
        for idx, item in enumerate(failures):
            print(f"  {idx+1}. Expected: {item['expected']} | Got: {item['got']}")
            print(f"     Q: {item['question']}")
            # print(f"     Reasoning: {item['reasoning']}")
    print("=" * 60)

if __name__ == "__main__":
    main()
