"""Verify the actual drift CLI with the real Gemini SDK, app and local state."""

import contextlib
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

QUESTION = (
    "For this decision, Option A takes 10 minutes and costs 90 credits. "
    "Option B takes 40 minutes and costs 15 credits. Which option suits my saved "
    "preference better? End your answer with RCCE_OPTION_A or RCCE_OPTION_B "
    "on its own line."
)
OPTIONS = re.compile(r"\bRCCE_OPTION_([AB])\b")


def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()


def capture_case(feedback, scope, output):
    from google.genai.models import Models

    from drift.interfaces.cli import main

    receipts = []
    capture = io.StringIO()
    generate_code = Models.generate_content.__code__

    def observe(frame, event, result):
        if event != "return" or frame.f_code is not generate_code or result is None:
            return
        request = frame.f_locals.get("contents")
        if not isinstance(request, str):
            return
        text = result.text or ""
        receipts.append(
            {
                "provider_response_id": result.response_id,
                "model_version": result.model_version,
                "requested_model": frame.f_locals.get("model"),
                "request_sha256": digest(request),
                "response_sha256": digest(text),
                "response": text,
                "primary_question_present": QUESTION in request,
                "time_guidance": "Saved decision preference for this request: prefer less total time"
                in request,
                "cost_guidance": "Saved decision preference for this request: prefer lower total cost"
                in request,
                "review_stage": request.startswith("Review the following response"),
            }
        )

    sys.argv = [
        "drift",
        "ask",
        "--rcce-feedback",
        str(feedback),
        "--rcce-profile",
        "demo",
        "--rcce-context",
        "planning",
        "--rcce-scope",
        scope,
        QUESTION,
    ]
    threading.setprofile(observe)
    sys.setprofile(observe)
    try:
        with contextlib.redirect_stdout(capture):
            exit_code = main()
    finally:
        sys.setprofile(None)
        threading.setprofile(None)
        output.write_text(
            json.dumps(
                {
                    "scope": scope,
                    "stdout": capture.getvalue(),
                    "provider_receipts": receipts,
                },
                indent=2,
            )
        )
    return exit_code


def validate_case(result, expected, guidance):
    receipts = result["provider_receipts"]
    primary = [r for r in receipts if r["primary_question_present"]]
    critic = [r for r in receipts if r["review_stage"]]
    if len(receipts) != 2 or len(primary) != 1 or len(critic) != 1:
        raise ValueError("expected a real primary and critic Gemini receipt")
    model = os.environ["DRIFT_PRIMARY_MODEL"]
    if any(
        not r["provider_response_id"]
        or r["requested_model"] != model
        or r["model_version"] != model
        for r in receipts
    ):
        raise ValueError("provider ID or model is missing or mismatched")
    if (
        not primary[0][guidance]
        or primary[0]["time_guidance"] == primary[0]["cost_guidance"]
    ):
        raise ValueError(
            "provider prompt did not contain the expected resolved preference"
        )
    final = critic[0]["response"].strip()
    if not final or not result["stdout"].rstrip().endswith(final):
        raise ValueError("CLI did not return the captured live critic response")
    if set(OPTIONS.findall(final)) != {expected}:
        raise ValueError("live CLI did not return the expected option marker")


def run(output):
    run_data = {"status": "failed", "commit": os.environ.get("GITHUB_SHA"), "cases": []}
    try:
        with tempfile.TemporaryDirectory(prefix="rcce-cli-") as folder:
            root = Path(folder)
            feedback = root / "feedback.json"
            base = {"profile": "demo", "context": "planning"}
            feedback.write_text(
                json.dumps(
                    [
                        {
                            **base,
                            "review": 1,
                            "scope": "default",
                            "preference": "cheap",
                        },
                        {**base, "review": 2, "scope": "urgent", "preference": "fast"},
                        {**base, "review": 3, "scope": "urgent", "preference": "cheap"},
                        {**base, "review": 4, "scope": "urgent", "retracts": 3},
                    ]
                )
            )
            original = feedback.read_bytes()
            for scope, expected, guidance in (
                ("urgent", "A", "time_guidance"),
                ("default", "B", "cost_guidance"),
            ):
                evidence = root / f"{scope}.json"
                result = subprocess.run(
                    [
                        sys.executable,
                        __file__,
                        "case",
                        str(feedback),
                        scope,
                        str(evidence),
                    ],
                    env={**os.environ, "DRIFT_OS_ROOT": str(root / f"state-{scope}")},
                    check=False,
                    timeout=180,
                )
                case = (
                    json.loads(evidence.read_text())
                    if evidence.is_file()
                    else {"scope": scope}
                )
                case.update(exit_code=result.returncode, expected=expected)
                run_data["cases"].append(case)
                if result.returncode:
                    raise ValueError(
                        f"real CLI exited with code {result.returncode} for {scope}"
                    )
                validate_case(case, expected, guidance)
                if feedback.read_bytes() != original:
                    raise ValueError("the CLI modified the supplied feedback file")
        ids = {
            r["provider_response_id"]
            for c in run_data["cases"]
            for r in c["provider_receipts"]
        }
        if len(ids) != 4:
            raise ValueError("expected four distinct provider response IDs")
        run_data["status"] = "passed"
        print(
            "Live CLI passed urgent A and default B with four distinct Gemini responses."
        )
        return 0
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        run_data["failure"] = str(exc)
        print(f"Live CLI verification failed: {exc}", file=sys.stderr)
        return 1
    finally:
        output.write_text(json.dumps(run_data, indent=2))


if __name__ == "__main__":
    mode, *paths = sys.argv[1:]
    if mode == "case":
        raise SystemExit(capture_case(Path(paths[0]), paths[1], Path(paths[2])))
    if mode == "run":
        raise SystemExit(run(Path(paths[0])))
    raise SystemExit("expected case or run")
