#!/usr/bin/env python3
import requests
import time
import sys

API_URL = "http://localhost:8765/api/chat"

PROMPTS = [
    "Acknowledge test sequence initiation.",
    "Explain the difference between a list and a tuple in Python in two paragraphs.",
    "Write a comprehensive summary of the Universal Approximation Theorem, including its mathematical foundations, limitations, and how it applies to modern deep learning architectures. Provide examples.",
    "Proceed.",
    "Give me three facts about the Antikythera mechanism.",
    "Generate a detailed technical specification for a microservices architecture handling real-time financial transactions. Include database schemas, API endpoints, and security considerations.",
    "Write a Python script implementing a custom async rate-limiter using Redis.",
    "Explain the complete history of the x86 instruction set architecture, from inception to modern 64-bit extensions.",
    "Draft a comprehensive essay on the ethical implications of autonomous weapon systems.",
]


def run_prompts():
    print(f"Starting execution of {len(PROMPTS)} prompts against {API_URL}...")
    for idx, prompt in enumerate(PROMPTS, 1):
        print(f"\n--- Sending Prompt P{idx}/{len(PROMPTS)} ---")
        print(f"Prompt: {prompt!r}")
        start_time = time.time()
        try:
            r = requests.post(API_URL, json={"message": prompt}, timeout=180)
            r.raise_for_status()
            data = r.json()
            elapsed = time.time() - start_time
            reply = data.get("reply", "")
            print(f"Status: SUCCESS (took {elapsed:.2f}s)")
            print(f"Reply Length: {len(reply)} chars")
            print(f"First 100 chars: {reply[:100]!r}")
        except Exception as e:
            print(f"Status: FAILED (took {time.time() - start_time:.2f}s)")
            print(f"Error: {e}")
            sys.exit(1)
    print("\nAll 9 prompts completed successfully!")


if __name__ == "__main__":
    run_prompts()
