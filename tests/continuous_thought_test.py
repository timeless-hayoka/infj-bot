"""
Tests for Strong Continuous Thought Mode.
Simulates background cycles and verifies inner continuity.
"""

import asyncio
import logging
import pytest
import sys
import os
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from infj_bot.core.being import get_being
from infj_bot.core.homeostasis import get_homeostasis
from infj_bot.core.shadow import get_shadow
from infj_bot.core.dii_tracker import get_dii_tracker
from infj_bot.core.cognitive_orchestrator import CognitiveOrchestrator
from infj_bot.core.global_workspace import get_workspace

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("continuous_thought_test")

async def run_simulated_cycles(minutes: int = 5, interval: int = 5):
    """
    Run simulated background cycles for a given duration.
    interval is reduced for faster testing.
    """
    logger.info(f"Starting simulated background cycles for {minutes} minutes (interval={interval}s)")
    
    being = get_being()
    homeostasis = get_homeostasis()
    shadow = get_shadow()
    tracker = get_dii_tracker()
    orchestrator = CognitiveOrchestrator()
    workspace = get_workspace()
    
    cycles = (minutes * 60) // interval
    
    thoughts_captured = []
    
    for i in range(cycles):
        logger.info(f"--- Cycle {i+1}/{cycles} ---")
        
        # 1. Being free thought
        thought = being.free_thought()
        if thought:
            logger.info(f"Captured Thought: {thought['content']}")
            thoughts_captured.append(thought['content'])
        
        # 2. Shadow background tick
        shadow.background_tick(being=being)
        
        # 3. Homeostasis background cycle
        homeostasis.background_cycle(being=being)
        
        # 4. Compute DII
        sample = tracker.compute(
            being=being,
            workspace=workspace,
            homeostasis=homeostasis,
            shadow=shadow,
            orchestrator=orchestrator
        )
        logger.info(f"DII Sample: {sample.dii:.4f} (Simple: {sample.dii_simple:.4f})")
        
        await asyncio.sleep(interval)
        
    return thoughts_captured

@pytest.mark.asyncio
async def test_continuity():
    """Verify that the bot can recall what it has been thinking about."""
    logger.info("Verifying inner continuity...")
    
    # Run some cycles
    captured = await run_simulated_cycles(minutes=1, interval=5)
    
    being = get_being()
    recent = being.recent_thoughts(limit=5)
    
    logger.info("Recent thoughts from DB:")
    for t in recent:
        logger.info(f" - [{t.get('timestamp')}] {t.get('content')}")
    
    tracker = get_dii_tracker()
    trend = tracker.get_trend(n=10)
    logger.info(f"DII Trend: {trend}")
    
    if len(recent) > 0:
        logger.info("CONTINUITY SUCCESS: Bot has persistent inner thoughts.")
    else:
        logger.error("CONTINUITY FAILURE: No thoughts recorded.")

if __name__ == "__main__":
    asyncio.run(test_continuity())
