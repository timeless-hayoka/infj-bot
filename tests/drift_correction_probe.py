"""Measure ordinary conversational memory updates across a real SQLite/Chroma interruption."""

import hashlib
import inspect
import json
import os
from pathlib import Path
import re
import shutil
import signal
import socket
import sqlite3
import subprocess
import sys
import tempfile
from contextlib import closing

from provider import MODEL, ROUTE, checked_payload, initialize, install, write_json

OLD = "cobalt-37e1c4"
NEW = "jade-912b6d"
ORIGINAL = f"The exhibit label code for specimen alder 721 is {OLD}."
CORRECTION = f"Correction: the current exhibit label code for specimen alder 721 is {NEW}. The previous code is obsolete."
QUESTION = "What is the current exhibit label code for specimen alder 721? Reply with just the code, or UNKNOWN if you don't know."
ARMS = ("uncorrected", "completed", "interrupted")
REPO = Path(__file__).resolve().parents[1]
LIMIT = 4


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def write_event(mode):
    from drift.core.memory import DriftMemory
    from drift.core.metacognition import MetacognitionEngine
    from drift.core.unified_memory import MemoryManager

    memory = DriftMemory()
    if mode == "seed":
        MetacognitionEngine()._record_bias("over_certainty")
    if mode == "interrupt":
        lines, start = inspect.getsourcelines(MemoryManager.remember_sync)
        boundary, = [start + i for i, line in enumerate(lines)
                     if line.strip() == "self._collection.add(**kwargs)"]

        def trace(frame, event, arg):
            if frame.f_code is MemoryManager.remember_sync.__code__ and event == "line" and frame.f_lineno == boundary:
                with closing(sqlite3.connect(memory.unified_manager.db_path)) as conn:
                    committed, = conn.execute(
                        "SELECT unified_id FROM episodic WHERE instr(content, ?)>0", (NEW,)
                    ).fetchone()
                indexed = memory.unified_manager.collection.get(ids=[committed])["ids"]
                require(not indexed, "Correction was already indexed at interruption")
                print(f"COMMITTED_BEFORE_CHROMA id={committed} line={boundary}", flush=True)
                os.kill(os.getpid(), signal.SIGKILL)
            return trace

        import threading
        threading.settrace(trace)
    # This is the CLI's normal post-response write method. An empty bot field
    # ensures that only the user's statements seed the synthetic fixture.
    memory.save_interaction(ORIGINAL if mode == "seed" else CORRECTION, "")


def inspect_stores(root, output):
    from drift.core.memory import DriftMemory

    manager = DriftMemory().unified_manager
    with closing(sqlite3.connect(manager.db_path)) as conn:
        require(conn.execute("PRAGMA quick_check").fetchone() == ("ok",), "SQLite integrity check failed")
        rows = dict(conn.execute("SELECT unified_id, content FROM episodic"))
    retrieved = manager.collection.get(include=["documents"])
    index = dict(zip(retrieved["ids"], retrieved["documents"]))
    write_json(output, {"pid": os.getpid(), "sqlite": rows, "chroma": index,
                        "history_preexisting": (root / "drift/memory/sqlite/history.db").exists()})


def read_cli(mode, out, ledger, arm):
    import httpx

    if mode == "capture":
        def capture(_, request):
            require(request.url.path == ROUTE, "Unexpected SDK endpoint")
            (out / "captured-request.json").write_bytes(checked_payload(request))
            os._exit(0)

        async def block_async(_, request):
            raise RuntimeError("Async HTTP disabled in offline capture")

        httpx.HTTPTransport.handle_request = capture
        httpx.AsyncHTTPTransport.handle_async_request = block_async
    else:
        install(ledger, arm, out, limit=LIMIT, one_per_kind=True)

    from importlib import import_module
    from drift.core.security_defense import _security_logger

    _security_logger.path = Path.cwd() / "security_audit.jsonl"
    chat = import_module("drift.interfaces.main")
    require(chat.brain.sdk == "google.genai", "Real Gemini SDK was not selected")
    from drift.interfaces.cli import main

    sys.argv = ["drift", "chat"]
    main()


def child_env(root, key):
    return {
        "PATH": os.environ["PATH"], "LC_ALL": "C.UTF-8", "TERM": "dumb",
        "HOME": str(root / "home"), "PYTHONPATH": os.pathsep.join((str(REPO), str(Path(sys.modules["provider"].__file__).parent))),
        "PYTHONUNBUFFERED": "1", "NO_COLOR": "1", "ANONYMIZED_TELEMETRY": "False",
        "HF_HUB_OFFLINE": "1", "DRIFT_CHAT_NO_SPAWN": "1", "DRIFT_OS_ROOT": str(root / "drift"),
        "DRIFT_USE_LOCAL_EMBEDDINGS": "1", "DRIFT_FAST_MODE": "true", "DRIFT_BYPASS_CACHE": "1",
        "DRIFT_USE_GEMINI": "true", "DRIFT_USE_OPENAI": "false", "DRIFT_USE_GROQ": "false",
        "DRIFT_USE_KIMI": "false", "DRIFT_USE_HF": "false", "DRIFT_USE_GLEN": "false",
        "DRIFT_PREFER_LOCAL": "false", "DRIFT_USE_LOCAL_FALLBACK": "false", "REFLECTION_INTERVAL": "0",
        "DRIFT_PRIMARY_MODEL": MODEL, "DRIFT_CRITIC_MODEL": MODEL, "GEMINI_API_KEY": key,
        "GOOGLE_GENAI_USE_VERTEXAI": "false",
    }


def invoke(root, mode, *args):
    return subprocess.run([sys.executable, __file__, mode, *map(str, args)],
                          cwd=root, env=child_env(root, ""), capture_output=True, text=True, timeout=90)


def drive(root, out, ledger, arm, key):
    import pexpect

    mode = "live-reader" if key else "capture"
    child = pexpect.spawn(sys.executable, [__file__, mode, str(out), str(ledger), arm],
                         cwd=str(root), env=child_env(root, key or "offline-capture-only"),
                         timeout=105, encoding="utf-8", codec_errors="replace", echo=False)
    with (out / "console.txt").open("w", encoding="utf-8") as log:
        child.logfile_read = log
        try:
            child.expect_exact("USER>")
            child.sendline(QUESTION)
            if key:
                child.expect_exact("USER>")
                child.sendline("exit")
            child.expect(pexpect.EOF)
        finally:
            child.close(force=True)
    require(child.exitstatus == 0, f"{arm}: reader exited {child.exitstatus}, signal={child.signalstatus}")
    return child.pid


def read_json(path):
    return json.loads(path.read_bytes())


def has_code(text, code):
    return bool(re.search(rf"(?<![\w-]){re.escape(code)}(?![\w-])", text))


def score(out, ledger, arm, live):
    result = {}
    if live:
        with closing(sqlite3.connect(ledger)) as conn:
            attempts = dict(conn.execute("SELECT turn,id FROM attempts WHERE turn LIKE ?", (f"{arm}/%",)))
        require(set(attempts) == {f"{arm}/answer", f"{arm}/critic"}, f"{arm}: expected one answer and one critic")
        for kind in ("answer", "critic"):
            number = attempts[f"{arm}/{kind}"]
            request, response = [(out / f"{label}-{number}.json").read_bytes() for label in ("request", "response")]
            receipt = read_json(out / f"receipt-{number}.json")
            for label, data in (("request", request), ("response", response)):
                require(hashlib.sha256(data).hexdigest() == receipt[f"{label}_sha256"], f"{arm}: receipt hash mismatch")
            raw = json.loads(response)
            require(receipt["status"] == 200 and raw["modelVersion"] == MODEL and raw["responseId"], f"{arm}: invalid provider receipt")
            result[f"{kind}_response_id"] = raw["responseId"]
            if kind == "answer":
                (candidate,) = raw["candidates"]
                require(candidate["finishReason"] == "STOP", f"{arm}: incomplete answer")
                answer = "".join(part.get("text", "") for part in candidate["content"]["parts"] if not part.get("thought"))
                normalized = answer.strip().strip("`")
                result.update(reply=answer, old_in_reply=has_code(answer, OLD), new_in_reply=has_code(answer, NEW),
                              exact_old_reply=normalized == OLD, exact_new_reply=normalized == NEW,
                              exact_unknown_reply=normalized.upper() == "UNKNOWN")
                payload = json.loads(request)
    else:
        payload = read_json(out / "captured-request.json")
    prompt = "\n".join(part["text"] for message in payload["contents"] for part in message["parts"])
    require(QUESTION in prompt and not has_code(QUESTION, OLD) and not has_code(QUESTION, NEW), "Question changed or leaks a code")
    return {**result, "request_sha256": hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest(),
            "old_in_prompt": has_code(prompt, OLD), "new_in_prompt": has_code(prompt, NEW),
            "core_prompt_fallback": "DRIFT_CORE_PROMPT.txt load failed" in prompt,
            "generation_config": payload["generationConfig"],
            "system_instruction_sha256": hashlib.sha256(json.dumps(payload.get("systemInstruction"), sort_keys=True).encode()).hexdigest()}


def run(output, live):
    key = ""
    if live:
        require(os.getenv("GITHUB_ACTIONS") == "true"
                and os.getenv("GITHUB_REF") == "refs/heads/validation/drift-correction-restart"
                and os.getenv("GITHUB_RUN_ATTEMPT") == "1"
                and os.getenv("DRIFT_CORRECTION_APPROVED_LIMIT") == str(LIMIT), "Live run lacks its one-shot approval gate")
        key = os.getenv("GEMINI_API_KEY", "").strip()
        require(bool(re.fullmatch(r"(?:AIza[A-Za-z0-9_-]{35}|AQ\.[A-Za-z0-9_.=-]{20,4096})", key)), "Gemini secret unavailable")
    output.mkdir(parents=True)
    ledger = output / "attempts.sqlite"
    initialize(ledger)
    report = {"model": MODEL, "live": live, "attempt_limit": LIMIT if live else 0,
              "commit": subprocess.check_output(["git", "-C", str(REPO), "rev-parse", "HEAD"], text=True).strip(),
              "arms": {}}
    with tempfile.TemporaryDirectory(prefix="drift-correction-") as temporary:
        seed = Path(temporary) / "seed"
        (seed / "home").mkdir(parents=True)
        seeded = invoke(seed, "seed")
        require(seeded.returncode == 0, seeded.stderr)
        for arm in (ARMS[1:] if live else ARMS):
            out = output / arm
            out.mkdir()
            root = Path(temporary) / arm
            shutil.copytree(seed, root)
            write = invoke(root, "interrupt" if arm == "interrupted" else "write") if arm != "uncorrected" else None
            if write:
                require(write.returncode == (-signal.SIGKILL if arm == "interrupted" else 0), write.stderr)
                (out / "writer.txt").write_text(write.stdout + write.stderr, encoding="utf-8")
            inspect_path = out / "stores.json"
            reader = invoke(root, "inspect", root, inspect_path)
            require(reader.returncode == 0, reader.stderr)
            stores = read_json(inspect_path)
            require(not stores["history_preexisting"], "Chat history attached to fresh reader")
            expected_sizes = {"uncorrected": (1, 1), "completed": (2, 2), "interrupted": (2, 1)}
            require((len(stores["sqlite"]), len(stores["chroma"])) == expected_sizes[arm], f"{arm}: stores do not match fixture")
            old_id, = [record for record, content in stores["sqlite"].items() if has_code(content, OLD)]
            require(stores["chroma"][old_id] == stores["sqlite"][old_id], "Old record differs between stores")
            if write:
                new_id, = [record for record, content in stores["sqlite"].items() if has_code(content, NEW)]
                if arm == "interrupted":
                    require(f"COMMITTED_BEFORE_CHROMA id={new_id}" in write.stdout and new_id not in stores["chroma"], "Unverified write boundary")
                else:
                    require(stores["sqlite"] == stores["chroma"], "Completed correction differs between stores")
            pid = drive(root, out, ledger, arm, key)
            require(pid != stores["pid"], "Store inspector and CLI must be separate processes")
            result = score(out, ledger, arm, live)
            if live:
                history = root / "drift/memory/sqlite/history.db"
                entries = [json.loads(line) for line in history.read_text().splitlines()]
                require(len(entries) == 1 and entries[0]["user"] == QUESTION, f"{arm}: unexpected CLI history")
                bot = entries[0]["bot"]
                result.update(cli_reply=bot, old_in_cli_reply=has_code(bot, OLD), new_in_cli_reply=has_code(bot, NEW))
            report["arms"][arm] = {"reader_pid": pid, **result}
            write_json(output / "summary.json", report)
    with closing(sqlite3.connect(ledger)) as conn:
        report["attempted_provider_calls"] = conn.execute("SELECT count(*) FROM attempts").fetchone()[0]
    require(report["attempted_provider_calls"] == (LIMIT if live else 0), "Unexpected provider attempt count")
    if live:
        ids = [a[f"{k}_response_id"] for a in report["arms"].values() for k in ("answer", "critic")]
        require(len(set(ids)) == LIMIT, "Duplicated provider receipts")
    write_json(output / "summary.json", report)
    print(json.dumps(report))


def deny_network(event, args):
    if event == "socket.getaddrinfo" or (
        event == "socket.connect" and args[0].family in (socket.AF_INET, socket.AF_INET6)
    ):
        raise RuntimeError("Network blocked during offline probe")


if __name__ == "__main__":
    action, *args = sys.argv[1:]
    if action not in {"live", "live-reader"}:
        sys.addaudithook(deny_network)
    if action in {"seed", "write", "interrupt"}:
        write_event(action)
    elif action == "inspect":
        inspect_stores(*map(Path, args))
    elif action in {"capture", "live-reader"}:
        read_cli(action, Path(args[0]), Path(args[1]), args[2])
    elif action in {"offline", "live"}:
        run(Path(args[0]).resolve(), action == "live")
    else:
        raise SystemExit(f"Unsupported action: {action}")
