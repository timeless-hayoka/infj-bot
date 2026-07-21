"""
Trial 002: V4 Telemetry Verification.

Hypothesis: Calling Being.evolve() will successfully trigger a snapshot write
to the cognitive_snapshots table without affecting the primary being_state.
"""

import logging
import sys
import sqlite3
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from drift.core.logger import DriftLabLogger
from drift.core.being import get_being
from drift.core.config import BEING_DB

# Setup logging
logging.basicConfig(level=logging.INFO)
lab_logger = DriftLabLogger(variable="v4_telemetry")


def telemetry_trial_func(input_text, **kwargs):
    being = get_being()
    from drift.core.being import _SNAPSHOT_ENABLED

    print(f"DEBUG: Snapshot Enabled: {_SNAPSHOT_ENABLED}")
    print(f"DEBUG: BEING_DB: {BEING_DB}")

    # 1. Check initial snapshot count
    with sqlite3.connect(BEING_DB) as conn:
        try:
            count_start = conn.execute(
                "SELECT COUNT(*) FROM cognitive_snapshots"
            ).fetchone()[0]
        except sqlite3.OperationalError:
            count_start = 0

    # 2. Trigger evolve
    being.evolve(interaction_happened=True)

    # 3. Check final snapshot count
    with sqlite3.connect(BEING_DB) as conn:
        count_end = conn.execute("SELECT COUNT(*) FROM cognitive_snapshots").fetchone()[
            0
        ]

    # 4. Verify data integrity
    success = count_end == count_start + 1

    return {
        "snapshots_created": count_end - count_start,
        "total_snapshots": count_end,
        "success": 1 if success else 0,
    }


def main():
    # Use existing Lab infrastructure
    # Note: lab_run.sh handles the [Purge -> Hydrate -> Execute -> Extract]

    # Run Trial
    result = telemetry_trial_func("system_tick")

    # Log to Lab
    lab_logger.log_trial(
        test_id="V4_TEL_001",
        metrics=result,
        verdict="PASS" if result["success"] else "FAIL",
    )

    print(f"Trial Complete. Success: {result['success']}")


if __name__ == "__main__":
    main()
