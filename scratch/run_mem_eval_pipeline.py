import subprocess
import time
import sys
import os
from pathlib import Path
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")

PYTHON_BIN = str(PROJECT_ROOT / ".venv" / "bin" / "python3")
EVAL_PYTHON_BIN = "/home/crexs/LongMemEval/longmemeval-lite-venv/bin/python3"
LONG_MEM_DIR = "/home/crexs/LongMemEval"


def main():
    print("[1] Booting up uvicorn API server on port 8765...")
    # Inherit GEMINI_API_KEY, etc.
    env = os.environ.copy()

    api_proc = subprocess.Popen(
        [
            PYTHON_BIN,
            "-m",
            "uvicorn",
            "interfaces.api:app",
            "--host",
            "127.0.0.1",
            "--port",
            "8765",
            "--no-access-log",
        ],
        cwd=str(PROJECT_ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )

    print("[2] Waiting for API server to bind to port 8765...")
    time.sleep(5)

    print("[3] Running adversarial evaluation (50 instances)...")
    try:
        # Run run_adversarial_eval.py
        result = subprocess.run(
            [EVAL_PYTHON_BIN, "run_adversarial_eval.py"],
            cwd=str(LONG_MEM_DIR),
            env=env,
            capture_output=True,
            text=True,
        )
        print("Adversarial eval stdout:")
        print(result.stdout)
        if result.returncode != 0:
            print("ERROR: run_adversarial_eval.py failed!")
            print(result.stderr)
            api_proc.terminate()
            sys.exit(1)

        print("[4] Grading responses using gemini-2.5-flash...")
        # run evaluate_qa.py
        grade_result = subprocess.run(
            [
                EVAL_PYTHON_BIN,
                "src/evaluation/evaluate_qa.py",
                "gemini-2.5-flash",
                "drift_longmemeval_adversarial_50.jsonl",
                "data/longmemeval_adversarial_50.json",
            ],
            cwd=str(LONG_MEM_DIR),
            env=env,
            capture_output=True,
            text=True,
        )
        print("Grading stdout:")
        print(grade_result.stdout)
        if grade_result.returncode != 0:
            print("ERROR: evaluate_qa.py failed!")
            print(grade_result.stderr)
            api_proc.terminate()
            sys.exit(1)

        print("[5] Analyzing and printing summary...")
        # run analyze_results.py
        analysis_result = subprocess.run(
            [EVAL_PYTHON_BIN, "analyze_results.py"],
            cwd=str(LONG_MEM_DIR),
            env=env,
            capture_output=True,
            text=True,
        )
        print("Analysis stdout:")
        print(analysis_result.stdout)
        if analysis_result.returncode != 0:
            print("ERROR: analyze_results.py failed!")
            print(analysis_result.stderr)
            api_proc.terminate()
            sys.exit(1)

    except Exception as e:
        print(f"Error running pipeline: {e}")
    finally:
        print("[6] Terminating API server...")
        api_proc.terminate()
        try:
            api_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            api_proc.kill()

    print("[7] Memory evaluation pipeline complete!")


if __name__ == "__main__":
    main()
