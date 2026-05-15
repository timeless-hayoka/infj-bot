"""Central configuration for infj_bot backed by the Project DRIFT adapter."""

import os

try:
    from dotenv import load_dotenv
except ImportError:

    def load_dotenv():
        pass


load_dotenv()

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
    HOMEOSTASIS_DB,
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


from pathlib import Path  # noqa: E402


def _read_secret_file(path: Path) -> str | None:
    """First non-empty, non-comment line from a UTF-8 file (trimmed)."""
    try:
        text = path.expanduser().read_text(encoding="utf-8")
    except OSError as exc:
        logger.warning("Could not read secret file %s: %s", path, exc)
        return None
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        return s
    return None


def _api_key_with_file_fallback() -> str | None:
    direct = (
        os.getenv("API_KEY")
        or os.getenv("GEMINI_API_KEY")
        or os.getenv("GOOGLE_API_KEY")
    )
    if direct:
        return direct.strip() or None
    for env_name in ("API_KEY_FILE", "GEMINI_API_KEY_FILE", "GOOGLE_API_KEY_FILE"):
        raw_path = os.getenv(env_name, "").strip()
        if not raw_path:
            continue
        candidate = _read_secret_file(Path(raw_path))
        if candidate:
            return candidate
    return None

# --- Quantified budgets (approximate; reduces context RAM, not weight RAM) ---
# Rough chars-per-token for English; matches prompt_budget.CHARS_PER_TOKEN
CHARS_PER_TOKEN_EST = float(os.getenv("INFJ_CHARS_PER_TOKEN", "4"))
INFJ_MAX_TOTAL_PROMPT_CHARS = int(os.getenv("INFJ_MAX_TOTAL_PROMPT_CHARS", "12000"))
INFJ_MEMORY_SEARCH_TOP_K = int(os.getenv("INFJ_MEMORY_SEARCH_TOP_K", "8"))
INFJ_DOCUMENT_CHUNK_CHARS = int(os.getenv("INFJ_DOCUMENT_CHUNK_CHARS", "800"))
INFJ_DOCUMENT_CHUNK_OVERLAP = int(os.getenv("INFJ_DOCUMENT_CHUNK_OVERLAP", "100"))

API_KEY = _api_key_with_file_fallback()


def validate_api_key(key: str | None) -> dict:
    """Basic validation for Gemini API keys (39-char alphanumeric with some symbols)."""
    if not key:
        return {
            "ok": False,
            "error": (
                "No API key found. Set API_KEY, GEMINI_API_KEY, or GOOGLE_API_KEY, "
                "or API_KEY_FILE (path to a file whose first non-comment line is the key)."
            ),
        }
    if len(key) < 10:
        return {"ok": False, "error": f"API key looks too short ({len(key)} chars)."}
    lower = key.lower()
    dummies = {
        "your_api_key_here",
        "placeholder",
        "test",
        "example",
        "xxxx",
        "aaaa",
        "1234567890",
    }
    if lower in dummies or key.startswith("YOUR_"):
        return {"ok": False, "error": "API key appears to be a placeholder value."}
    return {"ok": True}


# Anthropic / Claude
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY") or os.getenv("CLAUDE_API_KEY")
ANTHROPIC_ORG_ID = os.getenv("ANTHROPIC_ORG_ID")
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-20250514")

REFLECTION_INTERVAL = int(os.getenv("REFLECTION_INTERVAL", "10"))

INFJ_PRIMARY_MODEL = os.getenv("INFJ_PRIMARY_MODEL", "gemini-2.5-flash")
DRIFT_PRIMARY_MODEL = INFJ_PRIMARY_MODEL
INFJ_CRITIC_MODEL = os.getenv("INFJ_CRITIC_MODEL", "gemini-2.5-flash")
DRIFT_CRITIC_MODEL = INFJ_CRITIC_MODEL

# Security: comma-separated list of domains the bughunter tools are pre-authorized to scan
_authorized_raw = os.getenv("INFJ_AUTHORIZED_TARGETS", "")
DEFAULT_AUTHORIZED_TARGETS = set(
    d.strip().lower() for d in _authorized_raw.split(",") if d.strip()
)

INFJ_LOCAL_MODEL = os.getenv("INFJ_LOCAL_MODEL", "qwen3:4b")
DRIFT_LOCAL_MODEL = INFJ_LOCAL_MODEL
INFJ_USE_LOCAL_FALLBACK = os.getenv("INFJ_USE_LOCAL_FALLBACK", "true").lower() in (
    "1",
    "true",
    "yes",
    "on",
)
DRIFT_USE_LOCAL_FALLBACK = INFJ_USE_LOCAL_FALLBACK
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
