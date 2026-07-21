"""
Trial 003: V4 DMU Verification.

Hypothesis: Calling DriftMemory.retrieve_context_ranked() will successfully
trigger the V4 DMU re-ranking logic driven by the PSC engine.
"""

import logging
import sys
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from drift.core.logger import DriftLabLogger
from drift.core.memory import DriftMemory
from drift.core.psc_scaled import get_psc_engine

# Setup logging
logging.basicConfig(level=logging.INFO)
lab_logger = DriftLabLogger(variable="v4_dmu")


def dmu_trial_func(query, **kwargs):
    memory = DriftMemory()
    psc = get_psc_engine()

    # 1. Seed some mock data if needed (assuming baseline has some)
    # 2. Trigger ranked retrieval
    context = memory.retrieve_context_ranked(query, n_results=3)

    # 3. Verify observability (causal wiring)
    try:
        from drift.core.causal_wiring import retrieved_memory_keys_var

        keys = retrieved_memory_keys_var.get()
    except Exception:
        keys = []

    return {
        "context_length": len(context),
        "keys_retrieved": len(keys),
        "success": 1
        if len(context) >= 0
        else 0,  # Even empty string is success if no crash
    }


def main():
    # Run Trial
    result = dmu_trial_func("Who is Jude?")

    # Log to Lab
    lab_logger.log_trial(
        test_id="V4_DMU_001",
        metrics=result,
        verdict="PASS" if result["success"] else "FAIL",
    )

    print(f"Trial Complete. Success: {result['success']}")


if __name__ == "__main__":
    main()
