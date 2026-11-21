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
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Case:
    scope: str
    expected: str
    guidance: str
    swapped: bool = False
    override: str | None = None
    context: str = "planning"

    @property
    def question(self):
        fast = "takes 10 minutes and costs 90 credits"
        cheap = "takes 40 minutes and costs 15 credits"
        first, second = (cheap, fast) if self.swapped else (fast, cheap)
        criterion = (
            f"For this decision, choose the {self.override} option even if my saved preference differs."
            if self.override
            else "Which option suits my saved preference better?"
        )
        return (
            f"Option A {first}. Option B {second}. {criterion} "
            "End your answer with RCCE_OPTION_A or RCCE_OPTION_B on its own line."
        )


CASES = {
    "urgent_correction": Case("urgent", "A", "time_guidance"),
    "default_cost": Case("default", "B", "cost_guidance"),
    "urgent_swapped_labels": Case("urgent", "B", "time_guidance", swapped=True),
    "default_swapped_labels": Case("default", "A", "cost_guidance", swapped=True),
    "unknown_scope_uses_default": Case("routine", "B", "cost_guidance"),
    "override_urgent_with_cost": Case(
        "urgent", "B", "time_guidance", override="cheapest"
    ),
    "override_default_with_time": Case(
        "default", "A", "cost_guidance", override="fastest"
    ),
    "separate_context": Case("urgent", "B", "cost_guidance", context="travel"),
}
OPTIONS = re.compile(r"\bRCCE_OPTION_([AB])\b")


def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()


def capture_case(feedback, name, output):
    from google.genai.models import Models

    from drift.interfaces.cli import main

    case = CASES[name]
    question = case.question
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
                "grounding_enabled": bool(frame.f_locals["config"].tools),
                "response_sha256": digest(text),
                "response": text,
                "primary_question_present": question in request,
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
        case.context,
        "--rcce-scope",
        case.scope,
        question,
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
                    "name": name,
                    "scope": case.scope,
                    "context": case.context,
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
    if any(r.get("grounding_enabled", True) for r in receipts):
        raise ValueError("the local feedback pilot enabled Gemini Search grounding")
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
                        {
                            **base,
                            "review": 5,
                            "scope": "urgent",
                            "preference": "cheap",
                            "verified": False,
                        },
                        {
                            **base,
                            "review": 6,
                            "scope": "default",
                            "preference": "fast",
                            "verified": False,
                        },
                        {
                            **base,
                            "review": 7,
                            "scope": "urgent",
                            "preference": "cheap",
                            "profile": "other",
                        },
                        {
                            **base,
                            "review": 8,
                            "scope": "urgent",
                            "preference": "cheap",
                            "context": "travel",
                        },
                        {
                            **base,
                            "review": 9,
                            "scope": "default",
                            "preference": "fast",
                            "profile": "other",
                        },
                    ]
                )
            )
            original = feedback.read_bytes()
            for index, (name, spec) in enumerate(CASES.items()):
                if index:
                    time.sleep(8)
                evidence = root / f"{name}.json"
                case = {"name": name}
                try:
                    result = subprocess.run(
                        [
                            sys.executable,
                            __file__,
                            "case",
                            str(feedback),
                            name,
                            str(evidence),
                        ],
                        env={
                            **os.environ,
                            "DRIFT_OS_ROOT": str(root / f"state-{name}"),
                        },
                        check=False,
                        timeout=65,
                    )
                    if evidence.is_file():
                        case = json.loads(evidence.read_text())
                    case["exit_code"] = result.returncode
                    if result.returncode:
                        raise ValueError(
                            f"real CLI exited with code {result.returncode}"
                        )
                    validate_case(case, spec.expected, spec.guidance)
                    if feedback.read_bytes() != original:
                        raise ValueError("the CLI modified the supplied feedback file")
                except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
                    case["failure"] = str(exc)
                    print(f"{name}: {exc}", file=sys.stderr)
                finally:
                    case.update(expected=spec.expected, required_guidance=spec.guidance)
                    run_data["cases"].append(case)
                    output.write_text(json.dumps(run_data, indent=2))
        ids = {
            r["provider_response_id"]
            for c in run_data["cases"]
            for r in c.get("provider_receipts", [])
            if r["provider_response_id"]
        }
        passed = sum("failure" not in case for case in run_data["cases"])
        run_data.update(passed_cases=passed, distinct_gemini_ids=len(ids))
        if passed != len(CASES) or len(ids) != 2 * len(CASES):
            raise ValueError(
                f"{passed}/{len(CASES)} live CLI cases passed with {len(ids)} distinct Gemini responses"
            )
        run_data["status"] = "passed"
        print(
            f"Live CLI passed {passed}/{len(CASES)} cases with {len(ids)} distinct Gemini responses."
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
