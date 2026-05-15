"""DRIFT config shim backed by the Project DRIFT state-root adapter."""

from __future__ import annotations

import os
import sys
from pathlib import Path

try:
    from dotenv import load_dotenv
except Exception:

    def load_dotenv(*args, **kwargs) -> bool:  # type: ignore[misc]
        return False


CORE_DIR = Path(__file__).resolve().parent
INFJ_ROOT = CORE_DIR.parent
if str(INFJ_ROOT) not in sys.path:
    sys.path.insert(0, str(INFJ_ROOT))

from config_adapter import (  # noqa: E402
    ADAPTER,
    ARCHITECTURE_DB,
    ASPIRATIONS_DB,
    BEING_DB,
    BODY_DB,
    CHROMA_DIR,
    COGNITIVE_FACTORY_DB,
    COLD_STORAGE_DIR,
    CONFIG_DIR,
    CONSISTENCY_EVAL_DB,
    DATA_DIR,
    DATA_ROOT,
    EMOTIONAL_FIELD_DB,
    EVALS_DIR,
    EXPLORER_DB,
    GOALS_DB,
    GROWTH_DB,
    HEALTH_DB,
    HISTORY_PATH,
    HUMANITY_DB,
    IIT_DB,
    INTUITION_DB,
    LOGS_DIR,
    MEMORY_DIR,
    METACOGNITION_DB,
    MODE_DISCRIMINATION_DB,
    PERSIST_DIRECTORY,
    PHYSICS_DB,
    PREFS_DB,
    PREDICTOR_DB,
    PROJECT_ROOT,
    RECON_DIR,
    RELATIONSHIP_DB,
    RELIABILITY_DB,
    SCHEDULER_DB,
    SELF_EVAL_DB,
    SELF_MODIFY_AUDIT_DB,
    SELF_MODIFY_DB,
    SHADOW_DB,
    SQLITE_DIR,
    STATE_ROOT,
    TEMPORAL_DB,
    TOOL_AUDIT_PATH,
    VALUES_DB,
    WORKSPACE_DB,
)

load_dotenv(CONFIG_DIR / ".env", override=False)

API_KEY = os.getenv("API_KEY") or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
REFLECTION_INTERVAL = int(os.getenv("REFLECTION_INTERVAL", "10"))

DRIFT_PRIMARY_MODEL = os.getenv("DRIFT_PRIMARY_MODEL", os.getenv("INFJ_PRIMARY_MODEL", "gemini-2.5-flash"))
DRIFT_CRITIC_MODEL = os.getenv("DRIFT_CRITIC_MODEL", os.getenv("INFJ_CRITIC_MODEL", "gemini-2.5-flash"))

_authorized_raw = os.getenv("DRIFT_AUTHORIZED_TARGETS", os.getenv("INFJ_AUTHORIZED_TARGETS", ""))
DEFAULT_AUTHORIZED_TARGETS = set(d.strip().lower() for d in _authorized_raw.split(",") if d.strip())

DRIFT_LOCAL_MODEL = os.getenv("DRIFT_LOCAL_MODEL", os.getenv("INFJ_LOCAL_MODEL", "qwen3:4b"))
DRIFT_USE_LOCAL_FALLBACK = os.getenv(
    "DRIFT_USE_LOCAL_FALLBACK",
    os.getenv("INFJ_USE_LOCAL_FALLBACK", "true"),
).lower() in ("1", "true", "yes", "on")
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
