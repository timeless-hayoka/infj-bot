import os
import sys
import google.generativeai as genai

# =====================================================================
# SELF-CHECK SYSTEM: Environment and Path Validation
# =====================================================================
REQUIRED_FILES = {
    "DMU Engine": "memory/dmu.py",
    "PEDI Metrics": "metrics/pedi.py"
}


def execute_environment_check():
    """Validates local files and API keys before running the audit."""
    print("[*] Running pre-flight self-check...")

    # 1. Check API Key
    if not os.environ.get("GEMINI_API_KEY"):
        print("[!] ERROR: GEMINI_API_KEY environment variable is not set.")
        print("    Fix: Run 'export GEMINI_API_KEY=\"your_key_here\"' in your terminal.")
        sys.exit(1)

    # 2. Check File Paths
    missing_files = False
    for name, path in REQUIRED_FILES.items():
        if not os.path.exists(path):
            print(f"[!] ERROR: Target file missing for {name} at location: ./{path}")
            print(f"    Fix: Ensure you are running this script from the root of 'infj-bot/'.")
            missing_files = True

    if missing_files:
        print("[!] Self-check failed. Aborting audit.")
        sys.exit(1)

    print("[+] Pre-flight self-check passed. Local environment secure.\n")


# =====================================================================
# CORE AUDIT ENGINE
# =====================================================================
def audit_file(model, file_path, criteria):
    """Reads file content and passes it to Gemini for semantic verification."""
    print(f"[*] Auditing {file_path}...")

    with open(file_path, 'r', encoding='utf-8') as f:
        code_content = f.read()

    prompt = f"""
You are an elite, cynical open-source code reviewer evaluating an 18,000-line cognitive middleware architecture.
Your task is to verify if the file provided below complies with strict documentation standards.

Target File: {file_path}
Evaluation Criteria: {criteria}

Analyze the code and any inline comments. Provide your response in this exact format:

STATUS: [PASS or FAIL]
REASONING: [A short, direct explanation of why it passed or what specific logic/math explanation is missing]
SUGGESTED CORRECTION: [If FAIL, provide the exact inline comment text and where to insert it. If PASS, leave blank]

Source Code:
```python
{code_content}
```
"""

    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"STATUS: FAIL\nREASONING: API call failed with error: {str(e)}\nSUGGESTED CORRECTION: N/A"


def main():
    # Execute the self-check first
    execute_environment_check()

    # Initialize the Gemini client (using current standard model)
    genai.configure(api_key=os.environ["GEMINI_API_KEY"])
    model = genai.GenerativeModel('gemini-2.5-flash')

    # Define criteria for each architectural piece
    tasks = [
        {
            "path": REQUIRED_FILES["DMU Engine"],
            "criteria": (
                "Look for explicit inline comments or docstrings explaining the mathematical "
                "or algorithmic implementation of TIME DECAY scoring. The comments must explain "
                "how memories fade over time and how emotional weight weights the retention curve."
            )
        },
        {
            "path": REQUIRED_FILES["PEDI Metrics"],
            "criteria": (
                "Look for explicit inline comments or docstrings explaining STATE FLUIDITY scoring. "
                "The comments must mathematically or logically explain how the continuity of the "
                "internal homeostatic states is tracked across context window resets."
            )
        }
    ]

    # Run audit
    for task in tasks:
        print("-" * 60)
        report = audit_file(model, task["path"], task["criteria"])
        print(report)
        print("-" * 60 + "\n")


if __name__ == "__main__":
    main()
