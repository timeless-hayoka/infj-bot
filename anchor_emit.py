"""anchor_emit.py - stream a real hunt into the ANCHOR console.

Drop this file next to your pipeline, import it, and call one helper at each
stage. The events show up live in the console's Live Run and Proof Gate views,
and the ladder climbs in real time as your tools finish.

When the ANCHOR server launches your pipeline (hunt mode), it sets
ANCHOR_SERVER_URL and ANCHOR_RUN_ID in the environment, so you do not wire
anything: just call the helpers. Running the pipeline standalone instead? Call
start_run() once to create a run, or configure(url=..., run_id=...) by hand.

Every call is best-effort. If the server is unreachable the call quietly no-ops
and never raises, so adding these lines cannot break your pipeline. Only the
Python standard library is used, so there is nothing to install.

Typical use inside a stage loop:

    import anchor_emit as ax

    ax.case_started(case_id, contract=name, expected=[swc])
    ax.stage(case_id, "slither")
    if slither_hit:
        ax.detected(case_id, swc=swc, source="slither", severity=sev)
    ax.stage(case_id, "mythril")
    if tools_agree:
        ax.correlated(case_id, swc=swc, evidence=["slither", "mythril"])
    ax.stage(case_id, "forge")
    ax.poc_result(case_id, swc=swc, exploit_verified=ok, test_path=path)
    ax.case_completed(case_id, "REPRODUCED_REAL" if ok else "CORRELATED")

Under the server you do NOT call run_started / run_completed; the server brackets
the run for you. Call them only when running standalone.
"""

import json
import os
import urllib.request

_URL = os.environ.get("ANCHOR_SERVER_URL", "http://127.0.0.1:8000").rstrip("/")
_RUN = os.environ.get("ANCHOR_RUN_ID")
_TIMEOUT = 3


def configure(url=None, run_id=None):
    """Override the server URL and/or run id (otherwise taken from the environment)."""
    global _URL, _RUN
    if url:
        _URL = url.rstrip("/")
    if run_id:
        _RUN = run_id
    return _RUN


def start_run(benchmark="3a8b8bf0", mode="hunt"):
    """Create a run and remember its id. Needed only when running standalone,
    not when the ANCHOR server launched the pipeline. Returns the run id or None."""
    global _RUN
    try:
        data = json.dumps({"benchmark": benchmark, "mode": mode}).encode()
        req = urllib.request.Request(
            f"{_URL}/runs",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            _RUN = json.loads(resp.read()).get("run_id")
    except Exception:
        _RUN = None
    return _RUN


def _emit(event_type, payload):
    if not _RUN:
        return False
    try:
        data = json.dumps({"type": event_type, "payload": payload}).encode()
        req = urllib.request.Request(
            f"{_URL}/runs/{_RUN}/ingest",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=_TIMEOUT).read()
        return True
    except Exception:
        return False


# --- run brackets (standalone only; the server does these in hunt mode) ----
def run_started(benchmark="3a8b8bf0", total_cases=0):
    return _emit("run.started", {"benchmark_id": benchmark, "total_cases": total_cases})


def run_completed(reproduced=0, precision=0.0, recall=0.0, f1=0.0):
    return _emit("run.completed", {"reproduced": reproduced, "precision": precision, "recall": recall, "f1": f1})


# --- one helper per ladder rung --------------------------------------------
def case_started(case_id, contract=None, expected=None):
    return _emit("case.started", {"case_id": case_id, "contract": contract, "expected": expected or []})


def stage(case_id, name):
    return _emit("stage.started", {"case_id": case_id, "stage": name})


def detected(case_id, swc=None, source="pipeline", severity=None):
    return _emit("finding.detected", {"case_id": case_id, "swc": swc, "source": source, "severity": severity})


def correlated(case_id, swc=None, evidence=None):
    return _emit("finding.correlated", {"case_id": case_id, "swc": swc, "evidence": evidence or []})


def poc_result(case_id, swc=None, exploit_verified=False, test_path=None, assertion_count=1):
    return _emit("poc.result", {"case_id": case_id, "swc": swc, "exploit_verified": exploit_verified, "test_path": test_path, "assertion_count": assertion_count})


def case_completed(case_id, validation_state):
    return _emit("case.completed", {"case_id": case_id, "validation_state": validation_state})


def log(text):
    return _emit("log.line", {"text": text, "message": text})


log_line = log
