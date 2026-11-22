"""DRIFT config shim backed by the Project DRIFT state-root adapter."""

from __future__ import annotations

import os

try:
    from dotenv import load_dotenv
except Exception:

    def load_dotenv(*_args, **_kwargs) -> bool:  # type: ignore[misc]
        return False


from drift.config_adapter import (
    ARCHITECTURE_DB as ARCHITECTURE_DB,
)
from drift.config_adapter import (
    ASPIRATIONS_DB as ASPIRATIONS_DB,
)
from drift.config_adapter import (
    BEING_DB as BEING_DB,
)
from drift.config_adapter import (
    BODY_DB as BODY_DB,
)
from drift.config_adapter import (
    CHROMA_DIR as CHROMA_DIR,
)
from drift.config_adapter import (
    COGNITIVE_FACTORY_DB as COGNITIVE_FACTORY_DB,
)
from drift.config_adapter import (
    COLD_STORAGE_DIR as COLD_STORAGE_DIR,
)
from drift.config_adapter import (
    CONFIG_DIR as CONFIG_DIR,
)
from drift.config_adapter import (
    CONSISTENCY_EVAL_DB as CONSISTENCY_EVAL_DB,
)
from drift.config_adapter import (
    DATA_DIR as DATA_DIR,
)
from drift.config_adapter import (
    DATA_ROOT as DATA_ROOT,
)
from drift.config_adapter import (
    EMOTIONAL_FIELD_DB as EMOTIONAL_FIELD_DB,
)
from drift.config_adapter import (
    EVALS_DIR as EVALS_DIR,
)
from drift.config_adapter import (
    EXPLORER_DB as EXPLORER_DB,
)
from drift.config_adapter import (
    GOALS_DB as GOALS_DB,
)
from drift.config_adapter import (
    GROWTH_DB as GROWTH_DB,
)
from drift.config_adapter import (
    HEALTH_DB as HEALTH_DB,
)
from drift.config_adapter import (
    HISTORY_PATH as HISTORY_PATH,
)
from drift.config_adapter import (
    HOMEOSTASIS_DB as HOMEOSTASIS_DB,
)
from drift.config_adapter import (
    HUMANITY_DB as HUMANITY_DB,
)
from drift.config_adapter import (
    IIT_DB as IIT_DB,
)
from drift.config_adapter import (
    INTUITION_DB as INTUITION_DB,
)
from drift.config_adapter import (
    LOGS_DIR as LOGS_DIR,
)
from drift.config_adapter import (
    MEMORY_DIR as MEMORY_DIR,
)
from drift.config_adapter import (
    METACOGNITION_DB as METACOGNITION_DB,
)
from drift.config_adapter import (
    MODE_DISCRIMINATION_DB as MODE_DISCRIMINATION_DB,
)
from drift.config_adapter import (
    PERSIST_DIRECTORY as PERSIST_DIRECTORY,
)
from drift.config_adapter import (
    PHYSICS_DB as PHYSICS_DB,
)
from drift.config_adapter import (
    PREDICTOR_DB as PREDICTOR_DB,
)
from drift.config_adapter import (
    PREFS_DB as PREFS_DB,
)
from drift.config_adapter import (
    PROJECT_ROOT as PROJECT_ROOT,
)

# Load project-root .env first, then canonical config dir .env
from drift.config_adapter import PROJECT_ROOT_PATH
from drift.config_adapter import (
    RECON_DIR as RECON_DIR,
)
from drift.config_adapter import (
    RELATIONSHIP_DB as RELATIONSHIP_DB,
)
from drift.config_adapter import (
    RELIABILITY_DB as RELIABILITY_DB,
)
from drift.config_adapter import (
    SCHEDULER_DB as SCHEDULER_DB,
)
from drift.config_adapter import (
    SELF_EVAL_DB as SELF_EVAL_DB,
)
from drift.config_adapter import (
    SELF_MODIFY_AUDIT_DB as SELF_MODIFY_AUDIT_DB,
)
from drift.config_adapter import (
    SELF_MODIFY_DB as SELF_MODIFY_DB,
)
from drift.config_adapter import (
    SHADOW_DB as SHADOW_DB,
)
from drift.config_adapter import (
    SQLITE_DIR as SQLITE_DIR,
)
from drift.config_adapter import (
    STATE_ROOT as STATE_ROOT,
)
from drift.config_adapter import (
    TEMPORAL_DB as TEMPORAL_DB,
)
from drift.config_adapter import (
    TOOL_AUDIT_PATH as TOOL_AUDIT_PATH,
)
from drift.config_adapter import (
    VALUES_DB as VALUES_DB,
)
from drift.config_adapter import (
    WORKSPACE_DB as WORKSPACE_DB,
)

load_dotenv(PROJECT_ROOT_PATH / ".env", override=False)
load_dotenv(CONFIG_DIR / ".env", override=False)

API_KEY = (
    os.getenv("API_KEY") or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
)
REFLECTION_INTERVAL = int(os.getenv("REFLECTION_INTERVAL", "10"))

DRIFT_PRIMARY_MODEL = os.getenv(
    "DRIFT_PRIMARY_MODEL", os.getenv("INFJ_PRIMARY_MODEL", "gemini-2.5-flash")
)
DRIFT_CRITIC_MODEL = os.getenv(
    "DRIFT_CRITIC_MODEL", os.getenv("INFJ_CRITIC_MODEL", "gemini-2.5-flash")
)

_authorized_raw = os.getenv(
    "DRIFT_AUTHORIZED_TARGETS", os.getenv("INFJ_AUTHORIZED_TARGETS", "")
)
DEFAULT_AUTHORIZED_TARGETS = set(
    d.strip().lower() for d in _authorized_raw.split(",") if d.strip()
)

DRIFT_LOCAL_MODEL = os.getenv(
    "DRIFT_LOCAL_MODEL", os.getenv("INFJ_LOCAL_MODEL", "qwen3:4b")
)
DRIFT_USE_LOCAL_FALLBACK = os.getenv(
    "DRIFT_USE_LOCAL_FALLBACK",
    os.getenv("INFJ_USE_LOCAL_FALLBACK", "true"),
).lower() in ("1", "true", "yes", "on")
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")

# Prefer local models (when available) over cloud for latency-sensitive usage.
DRIFT_PREFER_LOCAL = os.getenv(
    "DRIFT_PREFER_LOCAL", os.getenv("INFJ_PREFER_LOCAL", "true")
).lower() in ("1", "true", "yes", "on")

# Runtime tuning: smaller history reduces prompt size and latency.
DRIFT_HISTORY_SIZE = int(
    os.getenv("DRIFT_HISTORY_SIZE", os.getenv("INFJ_HISTORY_SIZE", "16"))
)

# Simple in-memory generation cache size to avoid repeat calls for identical prompts.
DRIFT_GEN_CACHE_SIZE = int(os.getenv("DRIFT_GEN_CACHE_SIZE", "128"))

# Groq High-Speed Inference Config
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
DRIFT_GROQ_MODEL = os.getenv("DRIFT_GROQ_MODEL", "llama-3.3-70b-versatile")
DRIFT_USE_GROQ = os.getenv("DRIFT_USE_GROQ", "true").lower() in (
    "1",
    "true",
    "yes",
    "on",
)

# Moonshot Kimi Config
KIMI_API_KEY = os.getenv("KIMI_API_KEY")
DRIFT_KIMI_MODEL = os.getenv("DRIFT_KIMI_MODEL", "moonshot-v1-8k")
DRIFT_USE_KIMI = os.getenv("DRIFT_USE_KIMI", "false").lower() in (
    "1",
    "true",
    "yes",
    "on",
)
KIMI_BASE_URL = os.getenv("KIMI_BASE_URL", "https://api.moonshot.cn/v1")

# Embedding config (use local hash-based embeddings on CPU for speed)
DRIFT_USE_LOCAL_EMBEDDINGS = os.getenv(
    "DRIFT_USE_LOCAL_EMBEDDINGS", "false"
).lower() in ("1", "true", "yes", "on")

# Memory pruning config
MAX_MEMORIES = int(os.getenv("INFJ_MAX_MEMORIES", "2500"))
PRUNING_THRESHOLD = float(os.getenv("INFJ_PRUNING_THRESHOLD", "0.15"))
PRUNE_EVERY_N_TURNS = int(os.getenv("INFJ_PRUNE_EVERY_N_TURNS", "10"))
BACKGROUND_PRUNE_INTERVAL_SECONDS = int(
    os.getenv("INFJ_PRUNE_INTERVAL_SEC", "1800")
)  # 30 min

# Strong Continuous Mode Config
STRONG_CONTINUOUS_MODE = os.getenv("STRONG_CONTINUOUS_MODE", "true").lower() in (
    "1",
    "true",
    "yes",
    "on",
)
BACKGROUND_CYCLE_SECONDS = int(os.getenv("BACKGROUND_CYCLE_SECONDS", "20"))
SHADOW_INFLUENCE_WEIGHT = float(os.getenv("SHADOW_INFLUENCE_WEIGHT", "0.7"))
HOMEOSTASIS_DECAY_SLOW = os.getenv("HOMEOSTASIS_DECAY_SLOW", "true").lower() in (
    "1",
    "true",
    "yes",
    "on",
)

# Hugging Face Pro Inference Config
HF_PRO_TOKEN = os.getenv("HF_PRO_TOKEN")
DRIFT_HF_MODEL = os.getenv("DRIFT_HF_MODEL", "meta-llama/Meta-Llama-3-8B-Instruct")
DRIFT_USE_HF = os.getenv("DRIFT_USE_HF", "false").lower() in ("1", "true", "yes", "on")
