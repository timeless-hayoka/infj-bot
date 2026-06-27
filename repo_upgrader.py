#!/usr/bin/env python3
"""
The Forge: Repository Upgrade Machine
Takes an entire repository (V1) and iteratively upgrades the code using the Agentic Forge Loop
until it compiles perfectly (V5) and achieves the user's optimization goals.
"""

import os
import sys
import subprocess
import re
import time
import argparse
from pathlib import Path

sys.path.insert(0, "/home/crexs/infj_bot")
from drift.core.brain import DriftBrain

def extract_code(response: str) -> str:
    """Extract code block from response."""
    pattern = r"```(?:python|cpp|c|js|ts|rb|rs|go|bash|sh|java|html)?\s*(.*?)```"
    match = re.search(pattern, response, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return response.strip()

def run_forge_upgrade(filepath: str, goal: str, model_name: str, sdk: str, max_iterations=5) -> bool:
    print(f"\n=======================================================")
    print(f"🔥 UPGRADING FILE: {filepath}")
    print(f"🎯 UPGRADE GOAL: {goal}")
    print(f"=======================================================")
    
    with open(filepath, 'r') as f:
        original_code = f.read()
        
    brain = DriftBrain()
    brain.sdk = sdk
    brain.primary_model_name = model_name
    
    if sdk == "local":
        os.environ["DRIFT_FAST_MODE"] = "true"
        
    sys_prompt = "You are a master AI refactoring engine. You take V1 code and upgrade it to a highly optimized V5. Output ONLY the raw upgraded code inside a markdown code block. Do not include explanations."
    prompt = f"Here is the original code:\n\n{original_code}\n\nUpgrade Goal: {goal}\n\nProvide the complete, fully functioning upgraded V5 code."
    
    start_time = time.time()
    
    for i in range(1, max_iterations + 1):
        print(f"\n[ITERATION {i}] Generating V{i+1} upgraded code...")
        try:
            brain.primary_system_prompt = sys_prompt
            response = brain.think(prompt, mode="engineer")
        except Exception as e:
            print(f"❌ Model inference failed: {e}")
            return False
            
        upgraded_code = extract_code(response)
        
        # Write to a temporary file to run through the forge
        temp_file = f"{filepath}.forge_tmp"
        with open(temp_file, "w") as f:
            f.write(upgraded_code)
            
        print(f"[ITERATION {i}] Testing upgraded code in The Forge...")
        result = subprocess.run(["forge", temp_file], capture_output=True, text=True)
        
        if "ALL PASSED" in result.stdout:
            elapsed = time.time() - start_time
            print(f"\n🏆 SUCCESS! Upgraded {filepath} to V{i+1} in {elapsed:.2f}s")
            # Overwrite original file with upgraded code
            with open(filepath, "w") as f:
                f.write(upgraded_code)
            os.remove(temp_file)
            return True
        else:
            print(f"❌ FORGE FAILED:")
            print(result.stdout)
            print(result.stderr)
            prompt = f"Your upgraded code failed compilation in The Forge. Here is the error. Fix it and output the full corrected code:\n\n{result.stdout}\n{result.stderr}\n\nPrevious attempt:\n{upgraded_code}"
            os.remove(temp_file)

    print(f"\n💀 FAILED: Could not upgrade {filepath} safely within {max_iterations} iterations. Retaining original V1 code.")
    return False

def upgrade_repository(repo_path: str, goal: str, model_name: str, sdk: str):
    supported_extensions = ['.py', '.cpp', '.cc', '.h', '.hpp', '.c', '.js', '.ts', '.html', '.rb', '.sh', '.bash', '.rs', '.go', '.java']
    
    print(f"\n🚀 INITIALIZING FORGE UPGRADE MACHINE FOR REPOSITORY: {repo_path}")
    path = Path(repo_path)
    
    if not path.exists() or not path.is_dir():
        print(f"❌ Invalid repository path: {repo_path}")
        return
        
    for file_path in path.rglob('*'):
        if file_path.is_file() and file_path.suffix in supported_extensions:
            # Skip hidden dirs, virtual envs, etc
            if '.git' in file_path.parts or 'node_modules' in file_path.parts or 'venv' in file_path.parts or '__pycache__' in file_path.parts:
                continue
            run_forge_upgrade(str(file_path), goal, model_name, sdk)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Forge Repository Upgrade Machine")
    parser.add_argument("repo", help="Path to the repository to upgrade")
    parser.add_argument("--goal", type=str, required=True, help="The upgrade goal/requirements")
    parser.add_argument("--model", type=str, default="gemini-2.5-flash", help="Model to use")
    parser.add_argument("--sdk", type=str, default="google.genai", help="SDK to use")
    
    args = parser.parse_args()
    upgrade_repository(args.repo, args.goal, args.model, args.sdk)
