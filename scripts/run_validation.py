"""Run complete regression and explicit infrastructure checks with evidence.

Live provider/API tests require --live. Docker/Foundry checks run real tools and
remain BLOCKED (with a nonzero exit) when the environment is absent.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DVD_PATHS = "test/{abi-smuggling,backdoor,naive-receiver,side-entrance,truster,unstoppable}/*.t.sol"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--docker", action="store_true")
    parser.add_argument("--foundry", action="store_true")
    parser.add_argument("--dvd-root", type=Path)
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()
    stamp = dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%SZ")
    output = (args.output_dir or ROOT / "logs" / f"validation-{stamp}").resolve()
    output.mkdir(parents=True, exist_ok=True)
    results: list[dict] = []
    env = os.environ.copy()
    env["PATH"] = str(Path(sys.executable).parent) + os.pathsep + env.get("PATH", "")
    env.setdefault("DRIFT_USE_LOCAL_EMBEDDINGS", "true")
    env["DRIFT_RUN_ENV_TESTS"] = "1" if args.live else "0"

    def blocked(name: str, detail: str) -> None:
        results.append({"name": name, "status": "BLOCKED", "detail": detail})
        print(f"{name}: BLOCKED — {detail}", flush=True)

    def run(
        name: str, command: list[str], *, cwd: Path = ROOT, timeout: int = 1200
    ) -> bool:
        logfile = output / f"{name}.log"
        try:
            with logfile.open("w") as log:
                proc = subprocess.run(
                    command,
                    cwd=cwd,
                    env=env,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    timeout=timeout,
                    check=False,
                )
            code = proc.returncode
            detail = None
        except (OSError, subprocess.TimeoutExpired) as exc:
            code = -1
            detail = str(exc)
        results.append(
            {
                "name": name,
                "status": "PASS" if code == 0 else "FAIL",
                "returncode": code,
                "command": command,
                "cwd": str(cwd),
                "log": str(logfile),
                "detail": detail,
            }
        )
        print(f"{name}: {results[-1]['status']} ({logfile})", flush=True)
        return code == 0

    with tempfile.TemporaryDirectory(prefix="drift-validation-") as state_root:
        env["DRIFT_OS_ROOT"] = state_root
        run("provenance", ["git", "rev-parse", "HEAD"])
        run(
            "syntax",
            [
                sys.executable,
                "-c",
                (
                    "import pathlib,py_compile,subprocess; "
                    "paths=subprocess.check_output(['git','ls-files','-z','*.py']).decode().split(chr(0)); "
                    "[py_compile.compile(p,doraise=True) for p in paths if p and pathlib.Path(p).is_file()]"
                ),
            ],
        )
        run("dependencies", [sys.executable, "-m", "pip", "check"])
        run(
            "pytest",
            [
                sys.executable,
                "-m",
                "pytest",
                "tests/",
                "-q",
                "--tb=short",
                f"--junitxml={output / 'pytest.xml'}",
            ],
        )

        if args.foundry:
            dvd = (args.dvd_root or ROOT.parent / "damn-vulnerable-defi").resolve()
            if not shutil.which("forge", path=env["PATH"]):
                blocked("foundry", "forge is not installed")
            elif not (dvd / "foundry.toml").is_file():
                blocked("foundry", f"DVD checkout missing: {dvd}")
            else:
                run("dvd-revision", ["git", "rev-parse", "HEAD"], cwd=dvd)
                run("forge-version", ["forge", "--version"])
                run(
                    "foundry",
                    ["forge", "test", "--match-path", DVD_PATHS, "-vv"],
                    cwd=dvd,
                )

        if args.docker:
            if not shutil.which("docker", path=env["PATH"]):
                blocked(
                    "docker",
                    "Docker CLI/daemon unavailable; use a Docker-capable runner",
                )
            elif run("docker-info", ["docker", "info"], timeout=30):
                tag = f"drift-validation:{stamp.lower()}"
                if run(
                    "docker-build", ["docker", "build", "-t", tag, "."], timeout=2400
                ):
                    run(
                        "docker-smoke",
                        ["bash", "scripts/docker_smoke.sh", tag],
                        timeout=180,
                    )

    summary = {"timestamp": stamp, "python": sys.version, "results": results}
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(f"Evidence: {output}", flush=True)
    return int(any(result["status"] != "PASS" for result in results))


if __name__ == "__main__":
    raise SystemExit(main())
