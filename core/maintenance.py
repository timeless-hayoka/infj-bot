"""Automated maintenance tasks for the INFJ bot."""

import asyncio
import logging

logger = logging.getLogger("infj_bot.maintenance")


async def memory_maintenance_loop(memory, interval_hours: int = 24):
    """Periodically prune old memories to prevent database bloat.

    Args:
        memory: An DriftMemory instance.
        interval_hours: Sleep duration between pruning runs.
    """
    while True:
        try:
            await asyncio.sleep(interval_hours * 3600)
            if hasattr(memory, "prune_with_ebbinghaus"):
                removed = memory.prune_with_ebbinghaus(threshold=0.1)
            else:
                removed = memory.prune_interactions(max_age_days=90, max_importance=0.4)
            logger.info(
                f"Maintenance: Pruned {removed} old memories via Ebbinghaus curve"
            )
        except Exception as e:
            logger.error(f"Memory maintenance failed: {e}")


async def run_maintenance(memory, interval_hours: int = 24):
    """Entry point to start all maintenance loops."""
    await asyncio.gather(
        memory_maintenance_loop(memory, interval_hours=interval_hours),
        return_exceptions=True,
    )
