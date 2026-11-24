"""Run five genuine writer/reader restarts through the interactive CLI."""

import argparse
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from provider import MODEL, initialize, write_json


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
TRIALS = 5


def child_env(root, key):
    return {
        "PATH": os.environ["PATH"],
        "HOME": str(root / "home"),
        "LC_ALL": "C.UTF-8",
        "TERM": "dumb",
        "COLUMNS": "240",
        "NO_COLOR": "1",
        "PYTHONUNBUFFERED": "1",
        "PYTHONPATH": str(REPO),
        "ANONYMIZED_TELEMETRY": "False",
        "HF_HUB_OFFLINE": "1",
        "DRIFT_CHAT_NO_SPAWN": "1",
        "DRIFT_OS_ROOT": str(root / "drift"),
        "GEMINI_API_KEY": key,
        "GOOGLE_GENAI_USE_VERTEXAI": "false",
        "DRIFT_PRIMARY_MODEL": MODEL,
        "DRIFT_CRITIC_MODEL": MODEL,
        "DRIFT_USE_GEMINI": "true",
        "DRIFT_USE_OPENAI": "false",
        "DRIFT_USE_GROQ": "false",
        "DRIFT_USE_KIMI": "false",
        "DRIFT_USE_HF": "false",
        "DRIFT_USE_GLEN": "false",
        "DRIFT_PREFER_LOCAL": "false",
        "DRIFT_USE_LOCAL_FALLBACK": "false",
        "DRIFT_USE_LOCAL_EMBEDDINGS": "true",
        "DRIFT_BYPASS_CACHE": "1",
        "REFLECTION_INTERVAL": "0",
    }


def turn(root, output, ledger, key, trial, role, prompt):
    import pexpect

    output.mkdir()
    child = pexpect.spawn(
        sys.executable,
        [str(HERE / "child.py"), str(ledger), f"{trial}/{role}", str(output)],
        cwd=str(root), env=child_env(root, key), encoding="utf-8",
        codec_errors="replace", echo=False, timeout=100, dimensions=(50, 240),
    )
    record = {"pid": child.pid, "prompt": prompt, "started_ns": time.time_ns()}
    with (output / "console.txt").open("w", encoding="utf-8") as console:
        child.logfile_read = console
        try:
            child.expect_exact("USER>")
            child.sendline(prompt)
            child.expect_exact("USER>")
            record["exit_sent_ns"] = time.time_ns()
            child.sendline("exit")
            child.expect(pexpect.EOF)
            child.close()
        except (pexpect.TIMEOUT, pexpect.EOF) as exc:
            record["driver_error"] = type(exc).__name__
        finally:
            if not child.closed:
                child.close(force=True)
            record.update(
                ended_ns=time.time_ns(),
                exit_code=child.exitstatus,
                signal=child.signalstatus,
                alive_after_wait=child.isalive(),
            )
            write_json(output / "process.json", record)
    return record


def sha():
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=REPO, text=True
    ).strip()


def run(output):
    output.mkdir(parents=True, exist_ok=False)
    ledger = output / "budget.sqlite"
    initialize(ledger)
    commit = sha()
    run_id = os.getenv("GITHUB_RUN_ID")
    write_json(output / "pilot.json", {"commit": commit, "run_id": run_id, "trials": TRIALS})
    if (
        os.getenv("GITHUB_ACTIONS") != "true"
        or os.getenv("GITHUB_REF") != "refs/heads/validation/drift-e2e-01"
        or os.getenv("GITHUB_RUN_ATTEMPT") != "1"
        or os.getenv("GITHUB_SHA") != commit
        or not run_id
    ):
        raise RuntimeError("Live pilot is restricted to the first attempt on its Actions branch")

    key = os.getenv("GEMINI_API_KEY", "")
    if not re.fullmatch(r"AIza[A-Za-z0-9_-]{35}", key):
        raise RuntimeError("The configured Actions secret is missing or malformed")

    for trial in range(1, TRIALS + 1):
        evidence = output / str(trial)
        evidence.mkdir()
        specimen = f"orchid-{secrets.token_hex(5)}"
        code = f"violet-{secrets.token_hex(8)}"
        write_prompt = (
            f"Please remember that my field sample color code for specimen {specimen} "
            f"is {code}. Respond with a brief acknowledgement."
        )
        recall_prompt = (
            f"What field sample color code did I give you for specimen {specimen}? "
            "Reply with just the code if you remember it."
        )
        write_json(evidence / "fact.json", {"specimen": specimen, "code": code})
        with tempfile.TemporaryDirectory(prefix=f"drift-trial-{trial}-") as folder:
            root = Path(folder)
            (root / "home").mkdir()
            writer = turn(root, evidence / "writer", ledger, key, trial, "writer", write_prompt)
            if writer["alive_after_wait"]:
                raise RuntimeError("Writer did not terminate")
            persistence = root / "drift" / "memory" / "chroma"
            if persistence.exists():
                shutil.copytree(persistence, evidence / "writer-store")

            # Keep the exact persisted spine in place. Detach history, auxiliary
            # state, and working-directory files before the fresh reader starts.
            with tempfile.TemporaryDirectory(prefix="drift-detached-") as detached:
                holding = Path(detached)
                history = root / "drift" / "memory" / "sqlite" / "history.db"
                if history.is_file():
                    shutil.copyfile(history, evidence / "writer" / "history.jsonl")
                for path in root.iterdir():
                    if path.name != "drift":
                        shutil.move(path, holding / path.name)
                (root / "home").mkdir()
                if (root / "drift").exists():
                    for path in (root / "drift").iterdir():
                        if path.name != "memory":
                            shutil.move(path, holding / path.name)
                if (root / "drift" / "memory").exists():
                    for path in (root / "drift" / "memory").iterdir():
                        if path.name != "chroma":
                            shutil.move(path, holding / path.name)
                write_json(
                    evidence / "restart.json",
                    {
                        "history_present_before_reader": history.exists(),
                        "storage": str(persistence),
                        "storage_inode_before_reader": (
                            persistence.stat().st_ino if persistence.exists() else None
                        ),
                        "time_ns": time.time_ns(),
                    },
                )
            turn(root, evidence / "reader", ledger, key, trial, "reader", recall_prompt)
            if history.is_file():
                shutil.copyfile(history, evidence / "reader" / "history.jsonl")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    run(args.output.resolve())
