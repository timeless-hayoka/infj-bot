#!/usr/bin/env python3
"""
Agentic Forge Loop
Tests different LLMs against the Forge to see how many iterations it takes to achieve perfectly compiling code.
"""

import os
import sys
import subprocess
import re
import time
from pathlib import Path

_BOT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(_BOT_ROOT))
from drift.core.brain import DriftBrain
from drift.core.forge_gate import gatekeeper_cli

def extract_code(response: str, lang: str = "python") -> str:
    """Extract code block from response."""
    # Match markdown code block
    pattern = rf"```{lang}\s*(.*?)```"
    match = re.search(pattern, response, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    # Fallback: if no markdown, just return the whole string if it doesn't look like chat
    return response.strip()

def run_forge_loop(model_name: str, sdk: str, goal: str, lang: str, ext: str, max_iterations=5):
    print(f"\n=======================================================")
    print(f"🔥 TESTING MODEL: {model_name} ({sdk})")
    print(f"🎯 GOAL: {goal}")
    print(f"=======================================================")
    
    # Configure brain
    brain = DriftBrain()
    brain.sdk = sdk
    brain.primary_model_name = model_name
    
    if sdk == "local":
        os.environ["DRIFT_FAST_MODE"] = "true" # Force GLEN

    sys_prompt = f"You are a master {lang} programmer. Output ONLY the raw {lang} code inside a ```{lang} block. No explanations. Write code to achieve the following goal."
    prompt = goal
    
    start_time = time.time()
    
    for i in range(1, max_iterations + 1):
        print(f"\n[ITERATION {i}] Generating code...")
        
        try:
            # Overwrite sys prompt
            brain.primary_system_prompt = sys_prompt
            response = brain.think(prompt, mode="engineer")
        except Exception as e:
            print(f"❌ Model inference failed: {e}")
            return False, 0
            
        code = extract_code(response, lang)
        
        filename = f"forge_test_arena_{model_name.replace('/', '_')}.{ext}"
        with open(filename, "w") as f:
            f.write(code)
            
        print(f"[ITERATION {i}] Code generated ({len(code)} bytes). Running Forge...")
        
        import tempfile
        import shutil
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_filename = os.path.join(tmpdir, f"test_arena.{ext}")
            shutil.copy(filename, tmp_filename)
            result = subprocess.run(
                ["python3", str(gatekeeper_cli()), tmpdir],
                capture_output=True,
                text=True,
            )
            
            if '"failed": 0' in result.stdout and '"total_files": 1' in result.stdout:
                elapsed = time.time() - start_time
                print(f"\n🏆 SUCCESS! {model_name} passed the Forge in {i} iterations! (Time: {elapsed:.2f}s)")
                print(f"Final output saved to {filename}")
                return True, i
            else:
                print(f"❌ FORGE FAILED:")
                print(result.stdout)
                print(result.stderr)
                prompt = f"The code you wrote failed validation. Here is the error. Fix it and output the full corrected code in a ```{lang} block:\n\n{result.stdout}\n{result.stderr}"

    print(f"\n💀 FAILED: {model_name} could not pass the Forge within {max_iterations} iterations.")
    return False, max_iterations

if __name__ == "__main__":
    goal = "Write a highly optimized binary search algorithm that takes an array and a target, and returns the index. Include a main function that tests it with 5 edge cases and prints the results."
    
    models = [
        {"name": "gemini-2.5-flash", "sdk": "google.genai", "lang": "cpp", "ext": "cpp"},
        {"name": "gemini-2.5-flash", "sdk": "google.genai", "lang": "python", "ext": "py"},
        {"name": "Qwen/Qwen2.5-1.5B-Instruct", "sdk": "local", "lang": "python", "ext": "py"}
    ]
    
    for m in models:
        run_forge_loop(m["name"], m["sdk"], goal, m["lang"], m["ext"])
