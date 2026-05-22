"""
experiment_control.py
DRIFT Experimental Control Layer
---------------------------------
Manages freeze flags, run lifecycle, config validation, and ablation
discipline enforcement. Imports RunLogger for logging run events.

Usage:
    control = ExperimentControl()
    run_id = f"run_{int(time.time())}"
    control.start_run(run_id, config)
    ...
    if control.is_active("memory"):
        self.memory.store(...)
    ...
    control.end_run()
"""

import warnings
import subprocess
import time
from contextlib import contextmanager

from infj_bot.core.run_logger import RunLogger


class ExperimentControl:

    def __init__(self):
        self.run_id = None
        self.run_config = {}
        self.freeze_memory = False
        self.freeze_state = False
        self.freeze_self_modify = False
        self.freeze_mutation = False
        self.freeze_novelty = False
        self.mode = None  # "ablation" | "normal" | "baseline"

    # ------------------------------------------------------------------ #
    #  Config Validation                                                   #
    # ------------------------------------------------------------------ #

    def _validate_config(self, config: dict):
        """
        Soft warnings for inconsistent flags.
        Hard errors for ablation discipline violations.
        Returns list of warning strings (already emitted).
        """
        issues = []

        # Memory frozen but novelty unfrozen → novelty scores will be stale
        if config.get("freeze_memory") and not config.get("freeze_novelty", True):
            msg = (
                "freeze_memory=True with freeze_novelty=False: "
                "novelty scores may be stale or undefined."
            )
            warnings.warn(msg)
            issues.append(msg)

        # Ablation discipline:
        #   freeze_memory / freeze_state = experimental CONDITIONS
        #   mutation / self_modify / novelty = SYSTEMS UNDER TEST
        #   Only ONE system-under-test may be active per ablation run.
        #   Do not change this logic — it prevents multi-variable contamination.
        if config.get("mode") == "ablation":
            active_systems = sum([
                not config.get("freeze_mutation", True),
                not config.get("freeze_self_modify", True),
                not config.get("freeze_novelty", True),
            ])
            if active_systems > 1:
                raise ValueError(
                    f"Ablation mode violation: {active_systems} systems active. "
                    f"Only one system-under-test may be unfrozen per ablation run."
                )

        return issues

    # ------------------------------------------------------------------ #
    #  Run Lifecycle                                                       #
    # ------------------------------------------------------------------ #

    def start_run(self, run_id: str, config: dict):
        """
        Begin a new experimental run.
        Raises RuntimeError if a previous run was not ended.
        """
        if self.run_id is not None:
            raise RuntimeError(
                f"Previous run '{self.run_id}' not ended. "
                f"Call end_run() before starting a new run."
            )

        self._validate_config(config)

        self.run_id = run_id
        self.run_config = config
        self.freeze_memory     = config.get("freeze_memory", False)
        self.freeze_state      = config.get("freeze_state", False)
        self.freeze_self_modify = config.get("freeze_self_modify", False)
        self.freeze_mutation   = config.get("freeze_mutation", False)
        self.freeze_novelty    = config.get("freeze_novelty", False)
        self.mode              = config.get("mode", "normal")

        try:
            git_hash = subprocess.check_output(
                ["git", "rev-parse", "HEAD"]
            ).decode().strip()
        except Exception:
            git_hash = "unknown"

        RunLogger.get_instance().log_run_start(self.run_id, config, git_hash)

    def end_run(self):
        """
        End the current run, flush + log run_end, reset all flags.
        """
        if self.run_id:
            RunLogger.get_instance().log_run_end(self.run_id)

        self.run_id = None
        self.run_config = {}
        self.freeze_memory      = False
        self.freeze_state       = False
        self.freeze_self_modify = False
        self.freeze_mutation    = False
        self.freeze_novelty     = False
        self.mode               = None

    # ------------------------------------------------------------------ #
    #  Guard Pattern                                                       #
    # ------------------------------------------------------------------ #

    def is_active(self, system: str) -> bool:
        """
        Returns True if the system is NOT frozen.
        Use at every call site:
            if control.is_active("memory"):
                self.memory.store(...)
        """
        return not getattr(self, f"freeze_{system}", False)

    @contextmanager
    def guard(self, system: str):
        """
        Context manager version of is_active().
        Usage:
            with control.guard("memory") as active:
                if active:
                    self.memory.store(...)
        """
        yield self.is_active(system)


# ------------------------------------------------------------------ #
#  Canonical Run Configs                                               #
#  Copy these exactly for each ablation type.                         #
#  Do not improvise configs during live test runs.                    #
# ------------------------------------------------------------------ #

RUN_CONFIGS = {

    # Baseline — all systems live, no freezing.
    # Run this 3× (companion, task, exploration modes) before any ablation.
    "baseline": {
        "mode": "baseline",
        "freeze_memory": False,
        "freeze_state": False,
        "freeze_self_modify": True,   # keep self-modify off during all tests
        "freeze_mutation": True,
        "freeze_novelty": False,
    },

    # Identity Collapse — does state alone produce continuity?
    # Memory wiped. Homeostasis intact. novelty unfrozen (but will be stale — expected).
    "identity_collapse": {
        "mode": "ablation",
        "freeze_memory": True,
        "freeze_state": False,
        "freeze_self_modify": True,
        "freeze_mutation": True,
        "freeze_novelty": True,       # freeze to avoid stale scores with no memory
    },

    # Memory-Only Continuity — does memory alone produce continuity without state?
    "memory_only": {
        "mode": "ablation",
        "freeze_memory": False,
        "freeze_state": True,
        "freeze_self_modify": True,
        "freeze_mutation": True,
        "freeze_novelty": False,
    },

    # Mutation Interaction — does mutation drive behavior independently of novelty?
    "mutation_interaction": {
        "mode": "ablation",
        "freeze_memory": False,
        "freeze_state": False,
        "freeze_self_modify": True,
        "freeze_mutation": False,
        "freeze_novelty": True,       # isolate mutation from novelty interaction
    },

    # Novelty Interaction — does novelty drive behavior independently of mutation?
    "novelty_interaction": {
        "mode": "ablation",
        "freeze_memory": False,
        "freeze_state": False,
        "freeze_self_modify": True,
        "freeze_mutation": True,
        "freeze_novelty": False,
    },
}
