import subprocess
import time
import sys
import os
import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PYTHON_BIN = str(PROJECT_ROOT / ".venv" / "bin" / "python3")

def main():
    print("[1] Starting live test harness...")
    harness_proc = subprocess.Popen(
        [PYTHON_BIN, "scripts/live_test_harness.py"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=str(PROJECT_ROOT),
        bufsize=1
    )

    # Read harness output character by character to avoid blocking on newline
    print("[2] Waiting for harness to complete snapshot...")
    prompt_found = False
    output_buf = ""
    
    while True:
        char = harness_proc.stdout.read(1)
        if not char:
            break
        output_buf += char
        sys.stdout.write(char)
        sys.stdout.flush()
        if "Press ENTER when you have finished all 9 prompts" in output_buf:
            prompt_found = True
            break
            
    if not prompt_found:
        print("ERROR: Harness did not reach the prompt line!")
        # Print stderr
        stderr_content = harness_proc.stderr.read()
        print(f"Stderr: {stderr_content}")
        harness_proc.terminate()
        sys.exit(1)

    # Reset active state to baseline zero before booting server
    print("\n[2b] Resetting active state to baseline zero...")
    import shutil
    state_dir = Path("/home/crexs/.drift_os")
    if state_dir.exists():
        for item in state_dir.iterdir():
            if item.name == "logs":
                continue
            try:
                if item.is_dir():
                    shutil.rmtree(item)
                else:
                    item.unlink()
                print(f"  [RESET] Deleted {item}")
            except Exception as e:
                print(f"  [RESET WARNING] Failed to delete {item}: {e}")

    print("[3] Booting up uvicorn API server...")
    # Start uvicorn server
    api_proc = subprocess.Popen(
        [PYTHON_BIN, "-m", "uvicorn", "interfaces.api:app", "--host", "127.0.0.1", "--port", "8765", "--no-access-log"],
        cwd=str(PROJECT_ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )

    # Wait a few seconds for the API server to be ready
    print("[4] Waiting for API server to bind to port 8765...")
    time.sleep(5)

    print("[5] Executing automated prompts against API server...")
    try:
        # Run automate_prompts.py
        result = subprocess.run(
            [PYTHON_BIN, "scripts/automate_prompts.py"],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True
        )
        print(result.stdout)
        if result.returncode != 0:
            print("ERROR: automate_prompts.py failed!")
            print(result.stderr)
    except Exception as e:
        print(f"Error running automated prompts: {e}")
    finally:
        # Kill API server
        print("[6] Terminating API server...")
        api_proc.terminate()
        try:
            api_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            api_proc.kill()

    # Now send ENTER to the harness
    print("[7] Sending ENTER key to live test harness...")
    harness_proc.stdin.write("\n")
    harness_proc.stdin.flush()

    # Read the rest of harness output
    print("[8] Waiting for harness to save telemetry, restore state, and finish...")
    while True:
        char = harness_proc.stdout.read(1)
        if not char:
            break
        sys.stdout.write(char)
        sys.stdout.flush()

    harness_proc.wait()
    print("[9] Harness execution completed.")

    # Locate findings
    # Find the most recent live_test directory inside ABLATION_RESULTS
    ablation_dir = PROJECT_ROOT / "ABLATION_RESULTS"
    if ablation_dir.exists():
        subdirs = [d for d in ablation_dir.iterdir() if d.is_dir() and d.name.startswith("live_test_")]
        if subdirs:
            latest_dir = max(subdirs, key=lambda d: d.name)
            findings_file = latest_dir / "results" / "findings.json"
            if findings_file.exists():
                print(f"\n[+] Found latest findings: {findings_file}")
                findings_data = json.loads(findings_file.read_text())
                print(json.dumps(findings_data, indent=2))
                
                # Print first 10 lines of test_only_governor_calibration.jsonl
                gov_file = latest_dir / "results" / "test_only_governor_calibration.jsonl"
                if gov_file.exists():
                    print(f"\n[+] First 10 lines of {gov_file.name}:")
                    with gov_file.open() as f:
                        for i in range(10):
                            l = f.readline()
                            if not l:
                                break
                            print(l.strip())

if __name__ == "__main__":
    main()
