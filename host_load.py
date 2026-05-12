"""Host CPU / RAM sampling for embodied and emotional counterweight.

Optional dependency: ``psutil``. If missing or disabled via env, callers get
``ok: false`` and should behave as if load is zero.
"""
from __future__ import annotations

import os
import time
from typing import Any, Dict, Optional

_MIN_INTERVAL = float(os.getenv("INFJ_HOST_LOAD_INTERVAL_SEC", "2.5"))

_cache: Optional[Dict[str, Any]] = None
_last_mono: float = 0.0
_cpu_warmed: bool = False


def _stress_from_samples(cpu_percent: float, memory_percent: float) -> float:
    """Map instantaneous CPU% and memory% to a single 0..1 strain scalar."""
    c = max(0.0, min(1.0, cpu_percent / 100.0))
    m = max(0.0, min(1.0, memory_percent / 100.0))
    # Memory pressure tends to dominate perceived "cramped" feeling for LLM stacks.
    return max(0.0, min(1.0, c * 0.42 + m * 0.58))


def sample_host_load(*, force: bool = False) -> Dict[str, Any]:
    """
    Return a cached snapshot of host load.

    Keys:
      ok: bool
      stress: float 0..1 (only meaningful when ok)
      cpu_percent, memory_percent: float | None
      available_mb: float | None
    """
    global _cache, _last_mono, _cpu_warmed

    if os.getenv("INFJ_DISABLE_HOST_LOAD", "").strip().lower() in ("1", "true", "yes", "on"):
        return {
            "ok": False,
            "stress": 0.0,
            "cpu_percent": None,
            "memory_percent": None,
            "available_mb": None,
            "reason": "disabled",
        }

    now = time.monotonic()
    if (
        not force
        and _cache is not None
        and now - _last_mono < _MIN_INTERVAL
    ):
        return _cache

    try:
        import psutil
    except ImportError:
        out: Dict[str, Any] = {
            "ok": False,
            "stress": 0.0,
            "cpu_percent": None,
            "memory_percent": None,
            "available_mb": None,
            "reason": "no_psutil",
        }
        _cache, _last_mono = out, now
        return out

    try:
        vm = psutil.virtual_memory()
        mem_pct = float(vm.percent)
        avail_mb = float(vm.available) / (1024.0 * 1024.0)
        if not _cpu_warmed:
            psutil.cpu_percent(interval=0.05)
            _cpu_warmed = True
        cpu_pct = float(psutil.cpu_percent(interval=None))
        st = _stress_from_samples(cpu_pct, mem_pct)
        out = {
            "ok": True,
            "stress": st,
            "cpu_percent": cpu_pct,
            "memory_percent": mem_pct,
            "available_mb": avail_mb,
        }
    except Exception as exc:  # noqa: BLE001 — best-effort host metrics
        out = {
            "ok": False,
            "stress": 0.0,
            "cpu_percent": None,
            "memory_percent": None,
            "available_mb": None,
            "reason": str(exc),
        }
    _cache, _last_mono = out, now
    return out


def host_stress_01() -> float:
    """Convenience for plugins: 0..1 strain or 0 if unavailable."""
    s = sample_host_load()
    if not s.get("ok"):
        return 0.0
    return float(s.get("stress", 0.0))


def stress_from_cpu_mem(cpu_percent: float, memory_percent: float) -> float:
    """Exposed for tests — same mapping as :func:`sample_host_load` internals."""
    return _stress_from_samples(cpu_percent, memory_percent)
