"""Exercise the live opt-in CLI with opposite profile and scope preferences."""

import json
import os
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from rcce_live_cli_pilot import digest, validate_case

CASES = (
    ("cedar", "default", "B"),
    ("maple", "urgent", "B"),
    ("maple", "default", "A"),
    ("cedar", "urgent", "A"),
)
GUIDANCE = {"A": "time_guidance", "B": "cost_guidance"}


def feedback_records():
    records = []
    for profile, default, urgent in (
        ("cedar", "cheap", "fast"),
        ("maple", "fast", "cheap"),
    ):
        base = {"profile": profile, "context": "planning"}
        records.extend(
            [
                {**base, "review": 1, "scope": "default", "preference": default},
                {**base, "review": 2, "scope": "urgent", "preference": urgent},
                {**base, "review": 3, "scope": "urgent", "preference": default},
                {**base, "review": 4, "scope": "urgent", "retracts": 3},
                {**base, "review": 5, "scope": "default", "preference": urgent, "verified": False},
            ]
        )
    return records


def run(output):
    report = {
        "status": "failed",
        "commit": os.environ.get("GITHUB_SHA"),
        "feedback": feedback_records(),
        "planned_cases": CASES,
        "cases": [],
    }
    try:
        if not os.environ.get("GEMINI_API_KEY"):
            raise ValueError("GEMINI_API_KEY is required for the live crossover pilot")
        if not os.environ.get("DRIFT_PRIMARY_MODEL"):
            raise ValueError("DRIFT_PRIMARY_MODEL must identify the pinned Gemini model")
        with TemporaryDirectory(prefix="rcce-crossover-") as folder:
            root = Path(folder)
            feedback = root / "feedback.json"
            original = json.dumps(report["feedback"])
            feedback.write_text(original, encoding="utf-8")
            for profile, scope, expected in CASES:
                label = f"{profile}-{scope}"
                evidence = root / f"{label}.json"
                case = {"profile": profile, "scope": scope, "expected": expected}
                report["cases"].append(case)
                try:
                    process = subprocess.run(
                        [
                            sys.executable,
                            str(Path(__file__).with_name("rcce_live_cli_pilot.py")),
                            "case", str(feedback), scope, str(evidence), profile,
                        ],
                        env={**os.environ, "DRIFT_OS_ROOT": str(root / label)},
                        timeout=180,
                        check=False,
                    )
                    case["exit_code"] = process.returncode
                finally:
                    if evidence.is_file():
                        case.update(json.loads(evidence.read_text(encoding="utf-8")))
                if case["exit_code"]:
                    raise ValueError(f"CLI failed for {label}")
                if feedback.read_text(encoding="utf-8") != original:
                    raise ValueError("CLI modified the feedback file")
                validate_case(case, expected, GUIDANCE[expected])
                for receipt in case["provider_receipts"]:
                    if digest(receipt["response"]) != receipt["response_sha256"]:
                        raise ValueError(f"Response hash mismatch for {label}")
                final = case["stdout"].strip().splitlines()[-1].strip()
                if final != f"RCCE_OPTION_{expected}":
                    raise ValueError(f"Invalid final option line for {label}")
        ids = {
            receipt["provider_response_id"]
            for case in report["cases"]
            for receipt in case["provider_receipts"]
        }
        if len(ids) != 2 * len(CASES):
            raise ValueError("Expected eight distinct Gemini response IDs")
        report["status"] = "passed"
        return 0
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        report["failure"] = str(exc)
        print(f"Live crossover failed: {exc}", file=sys.stderr)
        return 1
    finally:
        output.write_text(json.dumps(report, indent=2), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(run(Path(sys.argv[1])))
