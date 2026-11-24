"""Standalone diagnostic: python tests/fi001_crash_probe.py."""
import json
import os
from pathlib import Path
import signal
import sqlite3
import subprocess
import sys
import tempfile
import uuid

MARKER = "FI001 durable memory"

def child(mode, root, marker):
    from drift.core.unified_memory import Event, MemoryManager
    manager = MemoryManager(str(root / "memory.db"), str(root / "chroma"))
    if mode == "inspect":
        with sqlite3.connect(manager.db_path) as conn:
            rows = conn.execute("SELECT unified_id, content FROM episodic").fetchall()
        vectors = manager.collection.get(include=["documents"])
        recalled = manager.recall_sync(marker)
        print("FI001_JSON=" + json.dumps({
            "pid": os.getpid(), "sqlite": rows,
            "chroma": list(zip(vectors["ids"], vectors["documents"])),
            "recall": [[r.unified_id, r.event.content] for r in recalled],
        }), flush=True)
        return
    if mode == "crash":
        import inspect
        lines, start = inspect.getsourcelines(MemoryManager.remember_sync)
        targets = [start+i for i,line in enumerate(lines)
                   if line.strip() == "self._collection.add(**kwargs)"]
        assert len(targets) == 1, "Injection boundary changed"
        code = MemoryManager.remember_sync.__code__
        def trace(frame, event, arg):
            if frame.f_code is code and event == "line" and frame.f_lineno == targets[0]:
                print("FI001_BOUNDARY", flush=True)
                os.kill(os.getpid(), signal.SIGKILL)
            return trace
        sys.settrace(trace)
    manager.remember_sync(Event(type="interaction", content=marker), {"salience": 0.5})
    sys.settrace(None)

def run():
    evidence = []
    for trial in range(10):
        for mode in ("control", "crash"):
            with tempfile.TemporaryDirectory(prefix="fi001-") as tmp:
                root = Path(tmp)
                marker = MARKER + " " + uuid.uuid4().hex
                env = dict(os.environ, DRIFT_USE_LOCAL_EMBEDDINGS="1",
                           DRIFT_OS_ROOT=str(root), ANONYMIZED_TELEMETRY="False")
                def invoke(action):
                    return subprocess.run([sys.executable, __file__, action, tmp, marker],
                                          env=env, capture_output=True, text=True, timeout=120)
                writer = invoke(mode)
                assert writer.returncode == (0 if mode == "control" else -signal.SIGKILL), writer.stderr
                if mode == "crash":
                    assert "FI001_BOUNDARY" in writer.stdout
                reader = invoke("inspect")
                assert reader.returncode == 0, reader.stderr
                data = json.loads(next(line.split("=",1)[1] for line in reader.stdout.splitlines()
                                       if line.startswith("FI001_JSON=")))
                assert len(data["sqlite"]) == 1 and data["sqlite"][0][1] == marker
                if mode == "control":
                    assert data["sqlite"] == data["chroma"] == data["recall"]
                evidence.append(dict(trial=trial, mode=mode, writer_exit=writer.returncode,
                                     writer_stdout=writer.stdout, writer_stderr=writer.stderr,
                                     reader_stderr=reader.stderr, **data))
                Path("fi001-evidence.json").write_text(json.dumps(evidence, indent=2))
    crashes = [r for r in evidence if r["mode"] == "crash"]
    print(json.dumps({"trials": len(evidence), "missing_index": sum(not r["chroma"] for r in crashes),
                      "missing_recall": sum(not r["recall"] for r in crashes)}))

if __name__ == "__main__":
    if len(sys.argv) == 1:
        run()
    else:
        child(sys.argv[1], Path(sys.argv[2]), sys.argv[3])
