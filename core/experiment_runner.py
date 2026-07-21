"""
ExperimentRunner — The PHI Scientific Testing Framework.

Ensures reproducibility, isolation of variables, and structured reporting
for cognitive experiments. Handles baseline snapshots, memory bucketing,
and metric aggregation.
"""

import json
import logging
import os
import shutil
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Dict, List

from drift.core.config import DATA_DIR

logger = logging.getLogger("drift.experiment")

# Experiment paths
EXPERIMENT_ROOT = DATA_DIR / "experiments"
BASELINE_DIR = EXPERIMENT_ROOT / "baselines"
RUNS_DIR = EXPERIMENT_ROOT / "runs"


@dataclass
class ExperimentRun:
    run_id: int
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    input: str = ""
    variables: Dict[str, Any] = field(default_factory=dict)
    metrics: Dict[str, Any] = field(default_factory=dict)
    errors: int = 0
    duration_ms: float = 0.0


@dataclass
class ExperimentReport:
    experiment_id: str
    baseline_hash: str
    variable_tested: str
    start_time: str = field(default_factory=lambda: datetime.now().isoformat())
    runs: List[ExperimentRun] = field(default_factory=list)
    aggregate: Dict[str, Any] = field(default_factory=dict)


class ExperimentRunner:
    """Orchestrates controlled experiments on the PHI organism."""

    def __init__(self, experiment_id: str):
        self.experiment_id = experiment_id
        self.report = ExperimentReport(
            experiment_id=experiment_id,
            baseline_hash="pending",
            variable_tested="unknown",
        )
        self._ensure_dirs()

    def _ensure_dirs(self):
        for d in [EXPERIMENT_ROOT, BASELINE_DIR, RUNS_DIR]:
            d.mkdir(parents=True, exist_ok=True)

    def create_baseline(self, name: str = "default"):
        """Snapshot the current system state as a Control Baseline."""
        target = BASELINE_DIR / name
        if target.exists():
            shutil.rmtree(target)
        target.mkdir(parents=True)

        # Files to snapshot
        to_snapshot = [
            "being.db",
            "homeostasis.db",
            "nexus.db",
            "phi_proxy.db",
            "cognitive_architecture.db",
            "chroma_db/chroma.sqlite3",
            "memory/chroma",
        ]

        for item in to_snapshot:
            src = DATA_DIR / item
            if src.exists():
                dst = target / item
                dst.parent.mkdir(parents=True, exist_ok=True)
                if src.is_dir():
                    shutil.copytree(src, dst)
                else:
                    shutil.copy2(src, dst)

        logger.info(f"Baseline '{name}' created at {target}")
        return target

    def restore_baseline(self, name: str = "default"):
        """Restore the system to a clean baseline state."""
        src = BASELINE_DIR / name
        if not src.exists():
            raise FileNotFoundError(f"Baseline '{name}' not found.")

        # Wipe current state
        to_wipe = [
            "being.db",
            "homeostasis.db",
            "nexus.db",
            "phi_proxy.db",
            "cognitive_architecture.db",
            "chroma_db/chroma.sqlite3",
            "memory/chroma",
        ]

        for item in to_wipe:
            path = DATA_DIR / item
            if path.exists():
                if path.is_dir():
                    shutil.rmtree(path)
                else:
                    path.unlink()

        # Restore from baseline
        for item in os.listdir(src):
            s = src / item
            d = DATA_DIR / item
            if s.is_dir():
                shutil.copytree(s, d, dirs_exist_ok=True)
            else:
                shutil.copy2(s, d)

        logger.info(f"Baseline '{name}' restored.")

    def run_trial(
        self, trial_func: callable, input_text: str, variables: Dict[str, Any]
    ) -> ExperimentRun:
        """Execute a single trial run with isolation."""
        start_time = time.monotonic()
        run_id = len(self.report.runs) + 1

        logger.info(f"Starting Trial {run_id} for Experiment {self.experiment_id}")

        try:
            # Execute the cognitive turn
            metrics = trial_func(input_text, **variables)
            errors = 0
        except Exception as e:
            logger.exception(f"Trial {run_id} failed")
            metrics = {"error": str(e)}
            errors = 1

        duration = (time.monotonic() - start_time) * 1000

        run = ExperimentRun(
            run_id=run_id,
            input=input_text,
            variables=variables,
            metrics=metrics,
            errors=errors,
            duration_ms=duration,
        )

        self.report.runs.append(run)
        return run

    def finalize(self):
        """Compute aggregates and save the experiment report."""
        if not self.report.runs:
            return

        # Simple aggregation: mean of numeric metrics
        numeric_keys = set()
        for run in self.report.runs:
            for k, v in run.metrics.items():
                if isinstance(v, (int, float)):
                    numeric_keys.add(k)

        for k in numeric_keys:
            vals = [r.metrics[k] for r in self.report.runs if k in r.metrics]
            if vals:
                self.report.aggregate[f"avg_{k}"] = sum(vals) / len(vals)
                # Variance (population)
                avg = self.report.aggregate[f"avg_{k}"]
                self.report.aggregate[f"var_{k}"] = sum(
                    (x - avg) ** 2 for x in vals
                ) / len(vals)

        # Save report
        report_path = RUNS_DIR / f"{self.experiment_id}_report.json"
        with open(report_path, "w") as f:
            json.dump(asdict(self.report), f, indent=2)

        logger.info(f"Experiment {self.experiment_id} finalized. Report: {report_path}")
        return report_path
