"""Unified state-root and path contract for Project DRIFT.

This adapter is the single source of truth for durable runtime paths during the
unification of drift, DRIFT, and hive_mind. It implements a strict Singleton
pattern to enforce a single data root (~/.drift_os).
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:

    def load_dotenv(*_args, **_kwargs) -> bool:  # type: ignore[misc]
        return False


logger = logging.getLogger("drift_os.config_adapter")

PROJECT_ROOT_PATH = Path(__file__).resolve().parent


class _ConfigAdapter:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(_ConfigAdapter, cls).__new__(cls)
            cls._instance._initialize()
        return cls._instance

    def _initialize(self):
        # The Canonical Root
        self.root_dir = Path(
            os.getenv("DRIFT_OS_ROOT", str(Path.home() / ".drift_os"))
        ).resolve()

        # Core Subdirectories
        self.config_dir = self.root_dir / "config"
        self.sqlite_dir = self.root_dir / "memory" / "sqlite"
        self.chroma_dir = self.root_dir / "memory" / "chroma"
        self.logs_dir = self.root_dir / "logs"

        # Ensure directories exist
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.sqlite_dir.mkdir(parents=True, exist_ok=True)
        self.chroma_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)

    def get_db_path(self, db_name: str) -> str:
        """Returns the absolute path to a unified SQLite database."""
        if not db_name.endswith(".db"):
            db_name += ".db"
        return str(self.sqlite_dir / db_name)

    def get_chroma_dir(self) -> str:
        """Returns the absolute path to the unified ChromaDB directory."""
        return str(self.chroma_dir)

    def get_log_path(self, log_name: str) -> str:
        """Returns the absolute path to a unified log file."""
        if not log_name.endswith(".log") and "." not in log_name:
            log_name += ".log"
        return str(self.logs_dir / log_name)

    def get_config_path(self, config_name: str) -> str:
        """Returns the absolute path to a unified config file."""
        return str(self.config_dir / config_name)

    @property
    def DATA_ROOT(self) -> str:
        return str(self.root_dir)


# Expose the singleton instance
ConfigAdapter = _ConfigAdapter()

# ----------------------------------------------------------------------------
# Legacy Constant Exports (Compatibility Spine for Phase 2)
# These wrap the Singleton so we don't break existing files before they migrate.
# ----------------------------------------------------------------------------

ADAPTER = "drift_os"
PROJECT_ROOT = PROJECT_ROOT_PATH
STATE_ROOT = Path(ConfigAdapter.DATA_ROOT)
DATA_ROOT = Path(ConfigAdapter.DATA_ROOT)
DATA_DIR = Path(ConfigAdapter.DATA_ROOT)

SQLITE_DIR = Path(ConfigAdapter.sqlite_dir)
MEMORY_DIR = SQLITE_DIR

CONFIG_DIR = Path(ConfigAdapter.config_dir)
LOGS_DIR = Path(ConfigAdapter.logs_dir)

CHROMA_DIR = Path(ConfigAdapter.get_chroma_dir())
PERSIST_DIRECTORY = CHROMA_DIR
COLD_STORAGE_DIR = Path(ConfigAdapter.chroma_dir / "cold_storage")
RECON_DIR = Path(ConfigAdapter.chroma_dir / "recon")
EVALS_DIR = Path(ConfigAdapter.chroma_dir / "evals")

# Databases
BEING_DB = ConfigAdapter.get_db_path("being")
BODY_DB = ConfigAdapter.get_db_path("body")
ARCHITECTURE_DB = ConfigAdapter.get_db_path("architecture")
ASPIRATIONS_DB = ConfigAdapter.get_db_path("aspirations")
COGNITIVE_FACTORY_DB = ConfigAdapter.get_db_path("cognitive_factory")
CONSISTENCY_EVAL_DB = ConfigAdapter.get_db_path("consistency_eval")
EMOTIONAL_FIELD_DB = ConfigAdapter.get_db_path("emotional_field")
EXPLORER_DB = ConfigAdapter.get_db_path("explorer")
GOALS_DB = ConfigAdapter.get_db_path("goals")
GROWTH_DB = ConfigAdapter.get_db_path("growth")
HEALTH_DB = ConfigAdapter.get_db_path("health")
HUMANITY_DB = ConfigAdapter.get_db_path("humanity")
HOMEOSTASIS_DB = ConfigAdapter.get_db_path("homeostasis")
IIT_DB = ConfigAdapter.get_db_path("iit")
INTUITION_DB = ConfigAdapter.get_db_path("intuition")
METACOGNITION_DB = ConfigAdapter.get_db_path("metacognition")
MODE_DISCRIMINATION_DB = ConfigAdapter.get_db_path("mode_discrimination")
PHYSICS_DB = ConfigAdapter.get_db_path("physics")
PREFS_DB = ConfigAdapter.get_db_path("prefs")
PREDICTOR_DB = ConfigAdapter.get_db_path("predictor")
RELATIONSHIP_DB = ConfigAdapter.get_db_path("relationship")
RELIABILITY_DB = ConfigAdapter.get_db_path("reliability")
SCHEDULER_DB = ConfigAdapter.get_db_path("scheduler")
SELF_EVAL_DB = ConfigAdapter.get_db_path("self_eval")
SELF_MODIFY_AUDIT_DB = ConfigAdapter.get_db_path("self_modify_audit")
SELF_MODIFY_DB = ConfigAdapter.get_db_path("self_modify")
SHADOW_DB = ConfigAdapter.get_db_path("shadow")
TEMPORAL_DB = ConfigAdapter.get_db_path("temporal")
VALUES_DB = ConfigAdapter.get_db_path("values")
WORKSPACE_DB = ConfigAdapter.get_db_path("workspace")

# Others
HISTORY_PATH = ConfigAdapter.get_db_path("history")
TOOL_AUDIT_PATH = Path(ConfigAdapter.get_log_path("tool_audit"))
