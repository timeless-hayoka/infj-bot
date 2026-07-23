"""
logger.py — Standardized JSON reporting for DRIFT Lab.
Enforces schema integrity for all experimental trials.
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Any, Dict, Optional


@dataclass
class LabRecord:
    timestamp: str
    test_id: str
    control_hash: str
    variable_tested: str
    metrics: Dict[str, Any]
    verdict: str  # PASS | FAIL | INCONCLUSIVE
    metadata: Dict[str, Any]


class DriftLabLogger:
    """Enforces mandatory JSON output schema for scientific repeatability."""

    def __init__(self, variable: str):
        self.variable = variable
        # Resolve state root from environment (sandbox) or default to canonical
        self.state_root = Path(
            os.getenv("DRIFT_OS_ROOT", str(Path.home() / ".drift_os"))
        )
        self.log_path = self.state_root / "logs" / "experiment_record.json"

        # Ensure log directory exists
        try:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
        except PermissionError:
            # Fallback to /tmp if workspace is locked down
            self.log_path = Path("/tmp/drift_lab_experiment_record.json")

    def log_trial(
        self,
        test_id: str,
        metrics: Dict[str, Any],
        verdict: str,
        meta: Optional[Dict[str, Any]] = None,
    ):
        """Record a single trial to the standardized JSON log."""
        record = LabRecord(
            timestamp=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            test_id=test_id,
            control_hash=os.getenv("DRIFT_LAB_HASH", "UNKNOWN"),
            variable_tested=self.variable,
            metrics=metrics,
            verdict=verdict,
            metadata=meta or {},
        )

        # Atomic append to run log
        try:
            with open(self.log_path, "a") as f:
                f.write(json.dumps(asdict(record)) + "\n")
        except Exception as e:
            print(f"[❌ LOGGER ERROR] Failed to write trial record: {e}")


if __name__ == "__main__":
    # Smoke test
    logger = DriftLabLogger(variable="smoke_test")
    logger.log_trial(test_id="ST_001", metrics={"status": "functional"}, verdict="PASS")
    print(f"Logged smoke test to {logger.log_path}")
