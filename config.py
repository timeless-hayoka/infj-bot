"""Central configuration and path resolution for the INFJ bot."""
import os
from pathlib import Path

try:
    from dotenv import load_dotenv
except Exception:
    def load_dotenv():
        pass

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent
PERSIST_DIRECTORY = PROJECT_ROOT / "chroma_db"
HISTORY_PATH = PROJECT_ROOT / "history.jsonl"

API_KEY = os.getenv("API_KEY") or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
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
