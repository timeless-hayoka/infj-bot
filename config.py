"""Central configuration and path resolution for the INFJ bot.

Portable state: set INFJ_DATA_DIR to a directory on a fast external drive (e.g. a
mounted SSD). All SQLite stores, Chroma, chat history, and tool audit logs then
live under that tree. Code and assets stay in PROJECT_ROOT; *learned* state moves
with INFJ_DATA_DIR.

Quantified budgets (tunable via env): prompt size and retrieval fan-in cap RAM
pressure from *context*, not model weights — the LLM still loads in RAM.
"""

import logging
import os
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:

    def load_dotenv():
        pass


load_dotenv()

logger = logging.getLogger("infj_bot.config")

PROJECT_ROOT = Path(__file__).resolve().parent


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


# --- Path security --------------------------------------------------

# Directories we will never allow DATA_ROOT to resolve into.
_FORBIDDEN_ROOTS = {
    "/",
    "/root",
    "/home",
    "/etc",
    "/usr",
    "/bin",
    "/sbin",
    "/lib",
    "/lib64",
    "/var",
    "/tmp",
    "/boot",
    "/dev",
    "/proc",
    "/sys",
}

_MAX_DATA_ROOT_DEPTH = 6  # prevent absurdly deep nesting


def _resolve_data_root() -> Path:
    """Return directory for all persistent bot state (memory, logs, sqlite).

    Security checks:
    - Rejects empty or whitespace-only paths.
    - Rejects paths that resolve to system-critical directories.
    - Rejects paths with excessive depth (possible traversal abuse).
    - Ensures the directory is under the user's home or PROJECT_ROOT.
    """
    raw = os.getenv("INFJ_DATA_DIR", "").strip()
    if not raw:
        return PROJECT_ROOT

    p = Path(raw).expanduser().resolve()

    # Block traversal to forbidden system roots
    try:
        for forbidden in _FORBIDDEN_ROOTS:
            forbidden_path = Path(forbidden).resolve()
            if p == forbidden_path or (
                forbidden_path != Path("/") and p.is_relative_to(forbidden_path)
            ):
                logger.error(
                    f"INFJ_DATA_DIR '{raw}' resolves to forbidden path '{p}'. Falling back to PROJECT_ROOT."
                )
                return PROJECT_ROOT
    except (ValueError, OSError) as exc:
        logger.error(
            f"Path security check failed for '{raw}': {exc}. Falling back to PROJECT_ROOT."
        )
        return PROJECT_ROOT

    # Block excessive depth
    try:
        depth = (
            len(p.relative_to(Path.home()).parts)
            if p.is_relative_to(Path.home())
            else len(p.parts)
        )
    except ValueError:
        depth = len(p.parts)
    if depth > _MAX_DATA_ROOT_DEPTH:
        logger.error(
            f"INFJ_DATA_DIR '{raw}' exceeds max depth ({depth} > {_MAX_DATA_ROOT_DEPTH}). Falling back to PROJECT_ROOT."
        )
        return PROJECT_ROOT

    # Ensure path is either under home, under PROJECT_ROOT, or under /media (removable drives)
    under_home = False
    under_project = False
    under_media = False
    try:
        under_home = p.is_relative_to(Path.home())
    except ValueError:
        pass
    try:
        under_project = p.is_relative_to(PROJECT_ROOT)
    except ValueError:
        pass
    try:
        under_media = p.is_relative_to(Path("/media"))
    except ValueError:
        pass
    if not (under_home or under_project or under_media):
        logger.error(
            f"INFJ_DATA_DIR '{raw}' must be under home, PROJECT_ROOT, or /media. Falling back to PROJECT_ROOT."
        )
        return PROJECT_ROOT

    try:
        p.mkdir(parents=True, exist_ok=True)
    except (PermissionError, OSError) as exc:
        logger.error(
            f"Cannot create INFJ_DATA_DIR '{p}': {exc}. Falling back to PROJECT_ROOT."
        )
        return PROJECT_ROOT

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
INFJ_CRITIC_MODEL = os.getenv("INFJ_CRITIC_MODEL", "gemini-2.5-flash")

# Security: comma-separated list of domains the bughunter tools are pre-authorized to scan
_authorized_raw = os.getenv("INFJ_AUTHORIZED_TARGETS", "")
DEFAULT_AUTHORIZED_TARGETS = set(
    d.strip().lower() for d in _authorized_raw.split(",") if d.strip()
)

# Local LLM fallback via Ollama
INFJ_LOCAL_MODEL = os.getenv("INFJ_LOCAL_MODEL", "qwen3:4b")
INFJ_USE_LOCAL_FALLBACK = os.getenv("INFJ_USE_LOCAL_FALLBACK", "true").lower() in (
    "1",
    "true",
    "yes",
    "on",
)
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
