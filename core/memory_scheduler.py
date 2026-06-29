"""Scheduled memory consolidation for the unified memory spine (Phase 2)."""

from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Optional

logger = logging.getLogger("drift.memory_scheduler")

_DEFAULT_INTERVAL_SECONDS = 6 * 3600  # 6 hours
_last_run_monotonic: float = 0.0


def consolidation_interval_seconds() -> int:
    raw = os.getenv("DRIFT_MEMORY_CONSOLIDATE_INTERVAL_SECONDS", "").strip()
    if raw.isdigit():
        return max(300, int(raw))
    return _DEFAULT_INTERVAL_SECONDS


def consolidation_enabled() -> bool:
    return os.getenv("DRIFT_MEMORY_CONSOLIDATE", "1").strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }


async def run_memory_consolidation(*, force: bool = False) -> dict[str, int]:
    """Run MemoryConsolidator if interval elapsed or force=True."""
    global _last_run_monotonic

    if not consolidation_enabled() and not force:
        return {"skipped": 1}

    now = time.monotonic()
    interval = consolidation_interval_seconds()
    if not force and _last_run_monotonic and (now - _last_run_monotonic) < interval:
        return {"skipped": 1}

    from core.memory_consolidator import MemoryConsolidator

    consolidator = MemoryConsolidator()
    stats = await consolidator.run_scheduled_maintenance()
    _last_run_monotonic = now
    logger.info("[memory_scheduler] consolidation complete: %s", stats)
    return stats


def run_memory_consolidation_sync(*, force: bool = False) -> dict[str, int]:
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(run_memory_consolidation(force=force))
    if loop.is_running():
        loop.create_task(run_memory_consolidation(force=force))
        return {"scheduled": 1}
    return loop.run_until_complete(run_memory_consolidation(force=force))
