#!/usr/bin/env python3
"""Machine-readable Trinity status helper.

Runs `trin doctor --json` and emits a compact status wrapper that is safe for
automation, cron jobs, and lightweight health probes.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _doctor_command() -> Tuple[List[str], Path | None]:
    for candidate in ("trin", "drift"):
        launcher = shutil.which(candidate)
        if launcher:
            return [launcher, "doctor", "--json"], None
    return [sys.executable, "-m", "interfaces.cli", "doctor", "--json"], PROJECT_ROOT


def _release_info() -> Dict[str, Any]:
    try:
        from drift.trinity.release import get_release_info

        return get_release_info()
    except Exception:
        return {}


def _run_doctor() -> Dict[str, Any]:
    command, cwd = _doctor_command()
    proc = subprocess.run(
        command,
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        check=False,
    )

    raw_output = proc.stdout.strip() or proc.stderr.strip()
    if not raw_output:
        raise RuntimeError(
            f"trin doctor produced no output (exit code {proc.returncode})"
        )

    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"trin doctor did not return JSON: {exc}. Raw output: {raw_output[:500]}"
        ) from exc

    release = _release_info()
    return {
        "launcher": Path(command[0]).name,
        "command": command,
        "returncode": proc.returncode,
        "release": release,
        "doctor": payload,
        "healthy": payload.get("status") == "ok",
        "critical_missing_modules": payload.get("critical_missing_modules", []),
        "warning_missing_modules": payload.get("warning_missing_modules", []),
        "fixes": payload.get("fixes", []),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Emit a compact Trinity status summary.")
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print a machine-readable JSON summary.",
    )
    args = parser.parse_args(argv)

    try:
        summary = _run_doctor()
    except Exception as exc:
        error_payload = {
            "healthy": False,
            "status": "error",
            "error": str(exc),
        }
        if args.json:
            print(json.dumps(error_payload, indent=2, ensure_ascii=False))
        else:
            print(f"ANCHOR status: error - {exc}")
        return 1

    if args.json:
        print(json.dumps(summary, indent=2, ensure_ascii=False))
    else:
        doctor = summary["doctor"]
        release = summary.get("release", {})
        status = doctor.get("status", "unknown")
        critical = summary["critical_missing_modules"]
        warnings = summary["warning_missing_modules"]
        print(f"ANCHOR status: {status}")
        if release:
            print(
                f"Release: ANCHOR {release.get('version', 'unknown')} "
                f"({release.get('commit', 'unknown')})"
            )
        print(f"Healthy: {'yes' if summary['healthy'] else 'no'}")
        print(f"Critical missing modules: {', '.join(critical) if critical else 'none'}")
        print(f"Warning missing modules: {', '.join(warnings) if warnings else 'none'}")
        if summary["fixes"]:
            print("Suggested fixes:")
            for idx, fix in enumerate(summary["fixes"], start=1):
                print(f"  {idx}. {fix.get('summary', fix.get('issue', 'unknown'))}")
    return 0 if summary["healthy"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
