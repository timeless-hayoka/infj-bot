"""Central configuration and path resolution for the INFJ bot.

Portable state: set INFJ_DATA_DIR to a directory on a fast external drive (e.g. a
mounted SSD). All SQLite stores, Chroma, chat history, and tool audit logs then
live under that tree. Code and assets stay in PROJECT_ROOT; *learned* state moves
with INFJ_DATA_DIR.

Quantified budgets (tunable via env): prompt size and retrieval fan-in cap RAM
pressure from *context*, not model weights — the LLM still loads in RAM.
"""
import os
from pathlib import Path

try:
    from dotenv import load_dotenv
except Exception:
    def load_dotenv():
        pass

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent


def _resolve_data_root() -> Path:
    """Return directory for all persistent bot state (memory, logs, sqlite)."""
    raw = os.getenv("INFJ_DATA_DIR", "").strip()
    if not raw:
        return PROJECT_ROOT
    p = Path(raw).expanduser().resolve()
    p.mkdir(parents=True, exist_ok=True)
    return p


DATA_ROOT = _resolve_data_root()

# --- Vector store & transcript ---
PERSIST_DIRECTORY = DATA_ROOT / "chroma_db"
HISTORY_PATH = DATA_ROOT / "history.jsonl"

# --- Evaluation / audit databases ---
EVALS_DIR = DATA_ROOT / "evals"
EVALS_DIR.mkdir(parents=True, exist_ok=True)
MODE_DISCRIMINATION_DB = EVALS_DIR / "mode_discrimination.db"
CONSISTENCY_EVAL_DB = EVALS_DIR / "consistency_eval.db"
SELF_MODIFY_AUDIT_DB = EVALS_DIR / "self_modify_audit.db"

# --- Core cognitive SQLite files (single portable tree when INFJ_DATA_DIR is set) ---
BEING_DB = DATA_ROOT / "being.db"
EMOTIONAL_FIELD_DB = DATA_ROOT / "emotional_field.db"
SELF_MODIFY_DB = DATA_ROOT / "self_modify.db"
HOMEOSTASIS_DB = DATA_ROOT / "homeostasis.db"
RELIABILITY_DB = DATA_ROOT / "memory_reliability.db"
SHADOW_DB = DATA_ROOT / "shadow.db"
IIT_DB = DATA_ROOT / "iit_consciousness.db"
BODY_DB = DATA_ROOT / "embodiment.db"
INTUITION_DB = DATA_ROOT / "intuition.db"
ARCHITECTURE_DB = DATA_ROOT / "cognitive_architecture.db"
EXPLORER_DB = DATA_ROOT / "explorer.db"
ASPIRATIONS_DB = DATA_ROOT / "aspirations.db"
PREDICTOR_DB = DATA_ROOT / "predictor.db"
METACOGNITION_DB = DATA_ROOT / "metacognition.db"
VALUES_DB = DATA_ROOT / "values.db"
RELATIONSHIP_DB = DATA_ROOT / "relationship.db"
GROWTH_DB = DATA_ROOT / "growth.db"
TEMPORAL_DB = DATA_ROOT / "temporal.db"
SELF_EVAL_DB = DATA_ROOT / "self_eval.db"
PREFS_DB = DATA_ROOT / "preferences.db"
SCHEDULER_DB = DATA_ROOT / "scheduler.db"
GOALS_DB = DATA_ROOT / "goals.db"
HUMANITY_DB = DATA_ROOT / "humanity.db"
WORKSPACE_DB = DATA_ROOT / "workspace.db"
HEALTH_DB = DATA_ROOT / "health.db"
PHYSICS_DB = DATA_ROOT / "physics.db"
COGNITIVE_FACTORY_DB = DATA_ROOT / "cognitive_factory.db"

# --- Tooling / ops paths (large or sensitive logs follow DATA_ROOT) ---
TOOL_AUDIT_PATH = DATA_ROOT / "tool_audit.jsonl"
COLD_STORAGE_DIR = DATA_ROOT / "BLKKNIGHT_RECOVERY"
RECON_DIR = DATA_ROOT / "recon"

# --- Quantified budgets (approximate; reduces context RAM, not weight RAM) ---
# Rough chars-per-token for English; matches prompt_budget.CHARS_PER_TOKEN
CHARS_PER_TOKEN_EST = float(os.getenv("INFJ_CHARS_PER_TOKEN", "4"))
INFJ_MAX_TOTAL_PROMPT_CHARS = int(os.getenv("INFJ_MAX_TOTAL_PROMPT_CHARS", "12000"))
INFJ_MEMORY_SEARCH_TOP_K = int(os.getenv("INFJ_MEMORY_SEARCH_TOP_K", "8"))
INFJ_DOCUMENT_CHUNK_CHARS = int(os.getenv("INFJ_DOCUMENT_CHUNK_CHARS", "800"))
INFJ_DOCUMENT_CHUNK_OVERLAP = int(os.getenv("INFJ_DOCUMENT_CHUNK_OVERLAP", "100"))

API_KEY = os.getenv("API_KEY") or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")

# Anthropic / Claude
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY") or os.getenv("CLAUDE_API_KEY")
ANTHROPIC_ORG_ID = os.getenv("ANTHROPIC_ORG_ID")
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-20250514")

REFLECTION_INTERVAL = int(os.getenv("REFLECTION_INTERVAL", "10"))

INFJ_PRIMARY_MODEL = os.getenv("INFJ_PRIMARY_MODEL", "gemini-2.5-flash")
INFJ_CRITIC_MODEL = os.getenv("INFJ_CRITIC_MODEL", "gemini-2.5-flash")

# Security: comma-separated list of domains the bughunter tools are pre-authorized to scan
_authorized_raw = os.getenv("INFJ_AUTHORIZED_TARGETS", "")
DEFAULT_AUTHORIZED_TARGETS = set(d.strip().lower() for d in _authorized_raw.split(",") if d.strip())

# Local LLM fallback via Ollama
INFJ_LOCAL_MODEL = os.getenv("INFJ_LOCAL_MODEL", "qwen3:4b")
INFJ_USE_LOCAL_FALLBACK = os.getenv("INFJ_USE_LOCAL_FALLBACK", "true").lower() in ("1", "true", "yes", "on")
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
