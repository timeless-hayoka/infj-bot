"""
core/trajectory.py — droplet-safe state trajectory logger for DRIFT.

This is a CORE infrastructure module, not a sandboxed cognitive plugin, so it is
exempt from the plugin FORBIDDEN_IMPORTS list and may use os/fcntl directly.

WHY THE NAIVE VERSION LIES
    The common "append with a threading.Lock" logger breaks in exactly the setup
    DRIFT runs in:
      1. threading.Lock protects threads in ONE process. The moment you run >1
         uvicorn worker — or the process restarts mid-write — it protects nothing,
         and a torn write corrupts the JSONL so pandas.read_json(lines=True) throws
         on the WHOLE file.
      2. Unbounded append fills a small droplet/host volume and takes the bot down.
      3. wall-clock latency on a shared box is contaminated by noisy neighbors
         (vCPU steal) and network. If that feeds your energy/fatigue model, your
         "internal state" is partly a readout of someone else's workload.
      4. With inference in the Ollama daemon (separate process) or remote (Gemini),
         this Python process's CPU time is NOT model compute. Feeding it to energy
         is measuring the wrong thing.

WHAT THIS DOES
    - Cross-process-safe append via fcntl.flock on a dedicated lockfile (not the
      data file's own fd, which would race with rotation's rename).
    - Size-based rotation done under the same lock.
    - A reader that tolerates partial/corrupt lines and reads rotated files in order.
    - A CPUSampler that separates wall time, this-thread CPU, the INFERENCE process's
      CPU (via /proc/<pid>), and vCPU steal — so you feed the right number to energy.

DEGRADES GRACEFULLY: /proc and fcntl are Linux. On macOS (local dev) steal/proc-cpu
read as None and writes fall back to an in-process lock — fine for single-process dev.
"""

from __future__ import annotations

import json
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

try:
    import fcntl  # Linux/macOS

    _HAVE_FCNTL = True
except ImportError:  # pragma: no cover - Windows dev only
    _HAVE_FCNTL = False

try:
    _CLK_TCK = os.sysconf("SC_CLK_TCK")
except (ValueError, AttributeError, OSError):  # pragma: no cover
    _CLK_TCK = 100


# --------------------------------------------------------------------------- #
# Compute attribution — separate model time from wall time and neighbor noise
# --------------------------------------------------------------------------- #
def _read_total_and_steal() -> Optional[tuple[int, int]]:
    """System-wide (total_ticks, steal_ticks) from /proc/stat. None off-Linux."""
    try:
        with open("/proc/stat", "r") as f:
            for line in f:
                if line.startswith("cpu "):
                    nums = [int(x) for x in line.split()[1:]]
                    total = sum(nums)
                    steal = nums[7] if len(nums) > 7 else 0
                    return total, steal
    except (OSError, ValueError):
        return None
    return None


def _read_pid_cpu_ms(pid: int) -> Optional[float]:
    """CPU ms (utime+stime) consumed by a process, from /proc/<pid>/stat.

    Use this with the OLLAMA pid to capture real local-inference compute. Returns
    None for remote providers (no local pid) or off-Linux.
    """
    try:
        with open(f"/proc/{pid}/stat", "r") as f:
            data = f.read()
        # The comm field (field 2) may contain spaces/parens; split after the ')'.
        rparen = data.rfind(")")
        fields = data[rparen + 2 :].split()
        # After comm, fields are 0-indexed; utime=11, stime=12 in that slice.
        utime, stime = int(fields[11]), int(fields[12])
        return (utime + stime) * 1000.0 / _CLK_TCK
    except (OSError, ValueError, IndexError):
        return None


class CPUSampler:
    """Wrap one turn to separate the timing signals that actually mean different things.

        s = CPUSampler(inference_pid=ollama_pid).start()
        ... run the turn ...
        timing = s.stop()

    timing keys:
        wall_ms          total elapsed — contaminated by network + scheduling + steal
        py_thread_cpu_ms CPU this Python thread burned — orchestration, NOT inference
        infer_cpu_ms     CPU the inference process burned — FEED THIS to energy/fatigue
                         (None for remote providers like Gemini — see provider tag)
        steal_pct        % of CPU the hypervisor gave to neighbors this interval
                         (~0 on bare-metal OmniSlim; >0 only matters on the droplet)
        loadavg_1m       host load, context for the above
    """

    def __init__(self, inference_pid: Optional[int] = None):
        self.inference_pid = inference_pid
        self._wall0 = self._tcpu0 = self._infer0 = None
        self._steal0: Optional[tuple[int, int]] = None

    def start(self) -> "CPUSampler":
        self._wall0 = time.monotonic()
        self._tcpu0 = (
            time.thread_time() if hasattr(time, "thread_time") else time.process_time()
        )
        self._infer0 = (
            _read_pid_cpu_ms(self.inference_pid) if self.inference_pid else None
        )
        self._steal0 = _read_total_and_steal()
        return self

    def stop(self) -> Dict[str, Any]:
        wall_ms = (time.monotonic() - self._wall0) * 1000.0
        tcpu_now = (
            time.thread_time() if hasattr(time, "thread_time") else time.process_time()
        )
        py_cpu_ms = (tcpu_now - self._tcpu0) * 1000.0

        infer_cpu_ms = None
        if self.inference_pid:
            infer_now = _read_pid_cpu_ms(self.inference_pid)
            if infer_now is not None and self._infer0 is not None:
                infer_cpu_ms = round(max(0.0, infer_now - self._infer0), 2)

        steal_pct = None
        s1 = _read_total_and_steal()
        if self._steal0 and s1:
            d_total, d_steal = s1[0] - self._steal0[0], s1[1] - self._steal0[1]
            if d_total > 0:
                steal_pct = round(100.0 * d_steal / d_total, 3)

        try:
            load1 = round(os.getloadavg()[0], 2)
        except (OSError, AttributeError):
            load1 = None

        return {
            "wall_ms": round(wall_ms, 2),
            "py_thread_cpu_ms": round(py_cpu_ms, 2),
            "infer_cpu_ms": infer_cpu_ms,
            "steal_pct": steal_pct,
            "loadavg_1m": load1,
        }


# --------------------------------------------------------------------------- #
# The logger — cross-process-safe append + rotation
# --------------------------------------------------------------------------- #
class StateTrajectoryLogger:
    def __init__(
        self,
        log_path: str = "logs/state_trace.jsonl",
        max_bytes: int = 50_000_000,  # rotate at ~50MB; protects small volumes
        backup_count: int = 5,
        fsync: bool = False,  # True = durable but slow; False = flush only
    ):
        self.log_path = Path(log_path)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self.lock_path = self.log_path.with_suffix(self.log_path.suffix + ".lock")
        self.max_bytes = max_bytes
        self.backup_count = backup_count
        self.fsync = fsync
        self.session_id = datetime.now(timezone.utc).isoformat()
        self._thread_lock = threading.Lock()  # intra-process guard

    def _rotate_if_needed(self) -> None:
        """Caller MUST hold the cross-process lock. Renames the chain if oversized."""
        try:
            if self.log_path.exists() and self.log_path.stat().st_size < self.max_bytes:
                return
            if not self.log_path.exists():
                return
        except OSError:
            return
        oldest = self.log_path.with_suffix(
            self.log_path.suffix + f".{self.backup_count}"
        )
        try:
            if oldest.exists():
                oldest.unlink()
            for i in range(self.backup_count - 1, 0, -1):
                src = self.log_path.with_suffix(self.log_path.suffix + f".{i}")
                if src.exists():
                    src.rename(
                        self.log_path.with_suffix(self.log_path.suffix + f".{i + 1}")
                    )
            self.log_path.rename(self.log_path.with_suffix(self.log_path.suffix + ".1"))
        except OSError:
            pass  # never let logging take down the bot

    def log_turn(
        self,
        turn: int,
        state: Dict[str, Any],
        *,
        prompt_len: int = 0,
        response_len: int = 0,
        provider: str = "unknown",
        timing: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict] = None,
    ) -> None:
        entry = {
            "timestamp_iso": datetime.now(timezone.utc).isoformat(),
            "timestamp": time.time(),
            "session_id": self.session_id,
            "turn": turn,
            "pedi": state.get("pedi", {}),
            "dii": state.get("dii", 0.0),
            "energy": state.get("energy", 0.0),
            "fatigue": state.get("fatigue", 0.0),
            "needs": state.get("needs", {}),
            "mode": state.get("mode", "unknown"),
            "provider": provider,
            "prompt_length": prompt_len,
            "response_length": response_len,
            "timing": timing or {},
            "memory_active_keys": len(state.get("memory_keys", []) or []),
            "metadata": metadata or {},
        }
        # One complete line, written under an exclusive cross-process lock so writes
        # from concurrent requests / multiple workers can never interleave.
        line = json.dumps(entry, separators=(",", ":")) + "\n"
        with self._thread_lock:
            self._write_locked(line)

    def _write_locked(self, line: str) -> None:
        if not (_HAVE_FCNTL):
            # Single-process dev fallback: thread lock only.
            self._rotate_if_needed()
            with self.log_path.open("a") as f:
                f.write(line)
                f.flush()
            return
        # Cross-process: serialize on a dedicated lockfile, not the data fd.
        lock_fd = os.open(str(self.lock_path), os.O_CREAT | os.O_RDWR, 0o644)
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX)
            self._rotate_if_needed()
            fd = os.open(
                str(self.log_path), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644
            )
            try:
                os.write(fd, line.encode("utf-8"))
                if self.fsync:
                    os.fsync(fd)
            finally:
                os.close(fd)
        finally:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
            os.close(lock_fd)


# --------------------------------------------------------------------------- #
# Reader — tolerant of partial/corrupt lines, reads rotated files in order
# --------------------------------------------------------------------------- #
def _ordered_files(log_path: str) -> List[Path]:
    base = Path(log_path)
    files: List[Path] = []
    # Oldest first: .N ... .1, then the live file.
    for i in range(_MAX_BACKUPS, 0, -1):
        p = base.with_suffix(base.suffix + f".{i}")
        if p.exists():
            files.append(p)
    if base.exists():
        files.append(base)
    return files


_MAX_BACKUPS = 20  # generous ceiling for the reader; logger uses its own backup_count


def read_trace(
    log_path: str = "logs/state_trace.jsonl", include_rotated: bool = True
) -> Iterable[Dict[str, Any]]:
    """Yield entries, skipping any line that isn't valid JSON (torn/partial writes).

    NEVER use pandas.read_json(lines=True) directly on these files — one bad line
    fails the whole load. This is the safe path.
    """
    files = _ordered_files(log_path) if include_rotated else [Path(log_path)]
    for path in files:
        if not path.exists():
            continue
        try:
            with path.open("r") as f:
                for raw in f:
                    raw = raw.strip()
                    if not raw:
                        continue
                    try:
                        yield json.loads(raw)
                    except json.JSONDecodeError:
                        continue  # corrupt/partial line — skip, don't crash
        except OSError:
            continue


def load_dataframe(log_path: str = "logs/state_trace.jsonl"):
    """Return a pandas DataFrame if pandas is available, else a list of dicts.

    Run this on your LOCAL machine after scp-ing the logs down — not on the
    inference host, where Streamlit/pandas would steal vCPU from the model.
    """
    rows = list(read_trace(log_path))
    try:
        import pandas as pd

        return pd.json_normalize(rows)
    except ImportError:
        return rows


# --------------------------------------------------------------------------- #
# Integration sketch (NOT executed) — where this plugs into agent_turn
# --------------------------------------------------------------------------- #
_INTEGRATION_EXAMPLE = """
from core.trajectory import StateTrajectoryLogger, CPUSampler

logger = StateTrajectoryLogger(log_path="logs/state_trace.jsonl")  # module-level, once

# inside CognitiveOrchestrator / brain.agent_turn, around the inference call:
ollama_pid = get_ollama_pid()           # e.g. read once at boot; None when using Gemini
sampler = CPUSampler(inference_pid=ollama_pid if provider == "ollama" else None).start()

response = run_inference(assembled_prompt)   # Ollama (local) or Gemini (remote)

timing = sampler.stop()
logger.log_turn(
    turn=turn_number,
    state={
        "pedi": get_pedi_vector(),
        "dii": self.dii.current,
        "energy": self.homeostasis.energy,
        "fatigue": self.homeostasis.fatigue,
        "needs": self.homeostasis.get_needs_summary(),
        "mode": self.current_mode,
        "memory_keys": list(self.memory.active_concept_keys()),
    },
    prompt_len=len(assembled_prompt),
    response_len=len(response),
    provider=provider,           # "ollama" | "gemini" — lets analysis split local vs remote
    timing=timing,
)

# CRITICAL for the energy model: feed timing["infer_cpu_ms"] (real local compute) to
# homeostasis — NOT timing["wall_ms"]. On Gemini turns infer_cpu_ms is None (remote),
# so energy should reflect a network call, not local exertion. Using wall_ms would let
# a noisy neighbor or a slow network hop masquerade as cognitive fatigue.
"""
