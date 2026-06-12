#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  MOUSE VANGUARD v2.0 — The Tactical Developer Spearhead                      ║
║  ───────────────────────────────────────────────────────────────              ║
║  Hardware: 128GB USB | Zero-latency | Local-first | Project-aware            ║
║  Mission:  Get our tech into developer hands. Prove the model. Build loyalty. ║
╚══════════════════════════════════════════════════════════════════════════════╝

THE PLAY:
  Mouse is not a chatbot. Mouse is the vanguard — the first point of contact
  that deploys from a thumb drive, boots in seconds, and immediately starts
  solving the developer's problems. It scans their project, knows their git
  state, remembers their context, and stays offline.

  In 20 years the USB will be a museum piece. But the concept — a self-
  contained, zero-config, project-aware AI that earns trust before asking
  for cloud access — that survives.

USAGE:
  python3 MOUSE.V.2.py                    # Interactive tactical shell
  python3 MOUSE.V.2.py --doctor           # Self-diagnostic
  python3 MOUSE.V.2.py --deploy <type>    # Scaffold a new project

COMMANDS (inside shell):
  vanguard      Show tactical status, hardware, and deployment mode
  scan          Analyze the current codebase
  git           Show git status + recent commits
  deploy        Scaffold a project (python, node, rust, go)
  sync          Export/import memory for team sharing
  cortex        Browse active memory with project filtering
  manifesto     Display the Mouse Constitution
  models        List available local Ollama models
  doctor        Run full system diagnostic
  exit / quit   Shutdown and save state
"""

import sys
import os
import json
import time
import subprocess
import argparse
import platform
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple
from urllib import request, error
from pathlib import Path
from datetime import datetime

# ──────────────────────────────────────────────────────────────────────────────
# PATH & PORTABILITY ENGINE
# ──────────────────────────────────────────────────────────────────────────────

SCRIPT_DIR = Path(__file__).resolve().parent
EXECUTABLE_DIR = SCRIPT_DIR  # Everything lives here for USB portability


# Detect if we're running from removable media (USB, external drive, etc.)
def _is_removable_media(path: Path) -> bool:
    """Heuristic: check if the drive containing the script is removable."""
    try:
        # Linux: check /sys/block/*/removable
        os.stat(path)  # verify path is accessible
        # Best-effort: if path contains /media/ or /mnt/, likely removable
        p = str(path.resolve())
        if any(
            marker in p for marker in ["/media/", "/mnt/", "/Volumes/", "/run/media/"]
        ):
            return True
        # Try to find mount point and check if it's a tmpfs or removable block
        mount = subprocess.run(
            ["findmnt", "-n", "-o", "FSTYPE", "--target", str(path)],
            capture_output=True,
            text=True,
        )
        if mount.returncode == 0:
            fstype = mount.stdout.strip()
            if fstype in ("vfat", "exfat", "ntfs", "fuse"):
                return True
    except Exception:
        pass
    return False


VANGUARD_MODE = _is_removable_media(EXECUTABLE_DIR)

# All Mouse data lives in a hidden dir next to the script (portable)
MOUSE_HOME = EXECUTABLE_DIR / ".mouse_vanguard"
MOUSE_HOME.mkdir(exist_ok=True)

CONFIG_PATH = MOUSE_HOME / "config.json"
MEMORY_DIR = MOUSE_HOME / "memories"
MEMORY_DIR.mkdir(exist_ok=True)
DEPLOY_CACHE = MOUSE_HOME / "deploy_cache"
DEPLOY_CACHE.mkdir(exist_ok=True)
SYNC_DIR = MOUSE_HOME / "sync"
SYNC_DIR.mkdir(exist_ok=True)

# ──────────────────────────────────────────────────────────────────────────────
# DEFAULT CONFIGURATION
# ──────────────────────────────────────────────────────────────────────────────

DEFAULT_CONFIG = {
    "api_url": "http://localhost:11434/api/generate",
    "model_name": "",  # Auto-detect if empty
    "fallback_model": "llama3.2",
    "temperature": 0.7,
    "context_window": 8192,
    "max_project_files": 12,
    "max_file_size": 50000,
    "project_context_enabled": True,
    "git_context_enabled": True,
    "auto_sync_interval": 0,  # 0 = disabled
    "constitution_version": "2.0",
    "vanguard_branding": True,
}

# ──────────────────────────────────────────────────────────────────────────────
# TACTICAL UTILITIES
# ──────────────────────────────────────────────────────────────────────────────


def _print_banner():
    vanguard_mark = "🔥 VANGUARD MODE" if VANGUARD_MODE else "STATIONARY DEPLOYMENT"
    print(f"""
╔══════════════════════════════════════════════════════════════════════════════╗
║   ▗▄▄▖ ▗▄▖ ▗▄▄▖ ▗▄▄▖▗▄▄▄▖   MOUSE VANGUARD v2.0                            ║
║   ▐▌ ▐▌▐▌ ▐▌▐▌ ▐▌▐▌   ▐▌     The Tactical Developer Spearhead               ║
║   ▐▛▀▚▖▐▛▀▜▌▐▛▀▘ ▐▛▀▘ ▝▀▚▖   {vanguard_mark:30}        ║
║   ▐▙▄▞▘▐▌ ▐▌▐▌   ▐▙▄▄▖▗▄▄▞▘   Hardware: 128GB USB / Zero-Latency / Offline  ║
╚══════════════════════════════════════════════════════════════════════════════╝
    Data: {MOUSE_HOME}
""")


def _run_shell(
    cmd: List[str], cwd: Optional[str] = None, timeout: int = 10
) -> Tuple[int, str, str]:
    """Run a shell command safely. Returns (rc, stdout, stderr)."""
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, cwd=cwd, timeout=timeout
        )
        return result.returncode, result.stdout, result.stderr
    except FileNotFoundError:
        return 127, "", f"Command not found: {cmd[0]}"
    except subprocess.TimeoutExpired:
        return -1, "", "Command timed out"
    except Exception as exc:
        return -1, "", str(exc)


def _get_hardware_diag() -> Dict[str, Any]:
    """Quick hardware diagnostic for the vanguard."""
    diag = {
        "platform": platform.system(),
        "machine": platform.machine(),
        "processor": platform.processor() or "unknown",
        "python_version": platform.python_version(),
        "vanguard_mode": VANGUARD_MODE,
        "script_location": str(EXECUTABLE_DIR),
        "mouse_home": str(MOUSE_HOME),
    }
    # Memory info (Linux)
    try:
        with open("/proc/meminfo") as f:
            lines = f.readlines()
            mem_total = next((ln for ln in lines if ln.startswith("MemTotal:")), None)
            if mem_total:
                diag["memory_total_mb"] = int(mem_total.split()[1]) // 1024
    except Exception:
        diag["memory_total_mb"] = "unknown"
    # Disk info for the drive Mouse lives on
    try:
        st = os.statvfs(EXECUTABLE_DIR)
        diag["disk_free_gb"] = round((st.f_bavail * st.f_frsize) / (1024**3), 2)
        diag["disk_total_gb"] = round((st.f_blocks * st.f_frsize) / (1024**3), 2)
    except Exception:
        diag["disk_free_gb"] = "unknown"
    return diag


def _find_git_root(start: Path = Path.cwd()) -> Optional[Path]:
    """Walk upward looking for .git directory."""
    current = start.resolve()
    for _ in range(20):  # Limit depth
        if (current / ".git").is_dir():
            return current
        parent = current.parent
        if parent == current:
            break
        current = parent
    return None


def _get_git_status() -> Dict[str, Any]:
    """Extract git context if inside a repo."""
    root = _find_git_root()
    if not root:
        return {"in_repo": False}
    rc, branch_out, _ = _run_shell(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=str(root)
    )
    branch = branch_out.strip() if rc == 0 else "unknown"
    rc, status_out, _ = _run_shell(["git", "status", "--short"], cwd=str(root))
    rc2, log_out, _ = _run_shell(["git", "log", "--oneline", "-5"], cwd=str(root))
    rc3, remote_out, _ = _run_shell(["git", "remote", "-v"], cwd=str(root))
    return {
        "in_repo": True,
        "root": str(root),
        "branch": branch,
        "status_short": status_out.strip(),
        "recent_commits": log_out.strip().splitlines(),
        "remotes": remote_out.strip().splitlines()[:3],
    }


def _detect_project_type(root: Path) -> str:
    """Identify the technology stack of the current project."""
    markers = {
        "python": [
            "pyproject.toml",
            "setup.py",
            "setup.cfg",
            "requirements.txt",
            "Pipfile",
        ],
        "node": ["package.json", "package-lock.json", "yarn.lock", "pnpm-lock.yaml"],
        "rust": ["Cargo.toml", "Cargo.lock"],
        "go": ["go.mod", "go.sum"],
        "ruby": ["Gemfile", "Gemfile.lock"],
        "java": ["pom.xml", "build.gradle", "gradlew"],
        "docker": ["Dockerfile", "docker-compose.yml", "docker-compose.yaml"],
    }
    detected = []
    for tech, files in markers.items():
        if any((root / f).exists() for f in files):
            detected.append(tech)
    return ", ".join(detected) if detected else "unknown"


def _read_project_context(
    root: Path, max_files: int = 12, max_size: int = 50000
) -> str:
    """Read key project files to inject into the AI context."""
    priority_files = [
        "README.md",
        "README.rst",
        "README",
        "pyproject.toml",
        "package.json",
        "Cargo.toml",
        "go.mod",
        "requirements.txt",
        "Dockerfile",
        "docker-compose.yml",
        "Makefile",
        "makefile",
        ".cursorrules",
        ".cursorignore",
        "AGENTS.md",
    ]
    chunks = []
    added = 0
    for fname in priority_files:
        fpath = root / fname
        if not fpath.is_file():
            continue
        try:
            size = fpath.stat().st_size
            if size > max_size:
                chunks.append(f"--- {fname} (truncated, {size} bytes) ---")
                chunks.append(
                    fpath.read_text(encoding="utf-8", errors="ignore")[:max_size]
                )
            else:
                chunks.append(f"--- {fname} ---")
                chunks.append(fpath.read_text(encoding="utf-8", errors="ignore"))
            added += 1
            if added >= max_files:
                break
        except Exception:
            continue
    return "\n".join(chunks) if chunks else "No priority project files found."


def _get_directory_summary(root: Path, max_entries: int = 30) -> str:
    """Quick tree-like summary of the project structure."""
    try:
        entries = []
        for p in sorted(root.iterdir()):
            if p.name.startswith(".") and p.name not in (
                ".gitignore",
                ".dockerignore",
                ".env.example",
            ):
                continue
            mark = "📁" if p.is_dir() else "📄"
            entries.append(f"  {mark} {p.name}")
            if len(entries) >= max_entries:
                entries.append("  ... (truncated)")
                break
        return "\n".join(entries)
    except Exception as exc:
        return f"Error reading directory: {exc}"


def _list_ollama_models(api_url: str) -> List[str]:
    """Query Ollama for installed models."""
    try:
        base = (
            api_url.rsplit("/", 2)[0]
            if "/api/" in api_url
            else api_url.rsplit("/", 1)[0]
        )
        req = request.Request(f"{base}/api/tags", method="GET")
        with request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return [m["name"] for m in data.get("models", [])]
    except Exception:
        return []


# ──────────────────────────────────────────────────────────────────────────────
# CONFIGURATION MANAGER
# ──────────────────────────────────────────────────────────────────────────────


class PortableConfig:
    """Self-contained config that travels with the script."""

    def __init__(self, path: Path):
        self.path = path
        self.data = dict(DEFAULT_CONFIG)
        self.load()

    def load(self):
        if self.path.exists():
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                    self.data.update(loaded)
            except Exception as exc:
                print(f"[WARNING] Config load failed: {exc}. Using defaults.")

    def save(self):
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=2)
        except Exception as exc:
            print(f"[WARNING] Config save failed: {exc}")

    def get(self, key: str, default=None):
        return self.data.get(key, default)

    def set(self, key: str, value: Any):
        self.data[key] = value
        self.save()


# ──────────────────────────────────────────────────────────────────────────────
# MEMORY SYSTEM — Project-Scoped & Team-Shareable
# ──────────────────────────────────────────────────────────────────────────────


@dataclass
class MemoryItem:
    timestamp: float
    category: str
    content: str
    importance: float = 0.5
    project: str = "global"
    tags: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "category": self.category,
            "content": self.content,
            "importance": self.importance,
            "project": self.project,
            "tags": self.tags,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "MemoryItem":
        return cls(
            timestamp=d.get("timestamp", time.time()),
            category=d.get("category", "general"),
            content=d.get("content", ""),
            importance=d.get("importance", 0.5),
            project=d.get("project", "global"),
            tags=d.get("tags", []),
        )


class MemoryStore:
    """Persistent, project-scoped memory with export/import for team sync."""

    def __init__(self, directory: Path):
        self.directory = directory
        self.current_project = "global"
        self.items: List[MemoryItem] = []
        self._load_all()

    def _memory_path(self, project: str) -> Path:
        safe = "".join(c for c in project if c.isalnum() or c in "-_.")
        return self.directory / f"{safe}.json"

    def _load_project(self, project: str) -> List[MemoryItem]:
        path = self._memory_path(project)
        if not path.exists():
            return []
        try:
            with open(path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            return [MemoryItem.from_dict(item) for item in raw]
        except Exception:
            return []

    def _load_all(self):
        """Load all memories into a unified view."""
        self.items = []
        for fpath in self.directory.glob("*.json"):
            self.items.extend(self._load_project(fpath.stem))

    def save_project(self, project: Optional[str] = None):
        project = project or self.current_project
        project_items = [m for m in self.items if m.project == project]
        path = self._memory_path(project)
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump([m.to_dict() for m in project_items], f, indent=2)
        except Exception as exc:
            print(f"[WARNING] Memory save failed: {exc}")

    def add(
        self,
        category: str,
        content: str,
        importance: float = 0.5,
        tags: Optional[List[str]] = None,
    ):
        item = MemoryItem(
            timestamp=time.time(),
            category=category,
            content=content,
            importance=importance,
            project=self.current_project,
            tags=tags or [],
        )
        self.items.append(item)
        self.save_project()

    def summarize(self, project: Optional[str] = None, limit: int = 8) -> str:
        target = project or self.current_project
        relevant = [
            m for m in self.items if m.project == target or m.project == "global"
        ]
        if not relevant:
            return "No significant prior memory."
        # Sort by importance, decay older memories slightly
        now = time.time()

        def score(m: MemoryItem) -> float:
            age_days = (now - m.timestamp) / 86400
            decay = max(0.5, 1.0 - (age_days * 0.05))  # 5% decay per day
            return m.importance * decay

        top = sorted(relevant, key=score, reverse=True)[:limit]
        return "\n".join(f"- [{m.category}] {m.content[:120]}" for m in top)

    def export_sync(self, project: Optional[str] = None) -> str:
        """Export memory as a portable sync file for team sharing."""
        target = project or self.current_project
        relevant = [m for m in self.items if m.project == target]
        sync_data = {
            "meta": {
                "exported_at": datetime.now().isoformat(),
                "project": target,
                "mouse_version": "2.0",
                "exporter": platform.node(),
            },
            "memories": [m.to_dict() for m in relevant],
        }
        sync_path = SYNC_DIR / f"{target}_sync_{int(time.time())}.json"
        with open(sync_path, "w", encoding="utf-8") as f:
            json.dump(sync_data, f, indent=2)
        return str(sync_path)

    def import_sync(self, sync_path: Path) -> int:
        """Import a team sync file. Returns count of imported items."""
        try:
            with open(sync_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            imported = 0
            for raw in data.get("memories", []):
                item = MemoryItem.from_dict(raw)
                # Avoid exact duplicates
                if not any(
                    m.content == item.content and m.project == item.project
                    for m in self.items
                ):
                    self.items.append(item)
                    imported += 1
            self.save_project(data.get("meta", {}).get("project", "global"))
            return imported
        except Exception as exc:
            print(f"[ERROR] Import failed: {exc}")
            return 0


# ──────────────────────────────────────────────────────────────────────────────
# OLLAMA CLIENT — Zero-Config, Resilient
# ──────────────────────────────────────────────────────────────────────────────


class OllamaClient:
    def __init__(self, api_url: str, model_name: str, timeout: int = 60):
        self.api_url = api_url
        self.model_name = model_name
        self.timeout = timeout
        self._available_models: List[str] = []

    def ping(self) -> bool:
        try:
            base = (
                self.api_url.rsplit("/", 2)[0]
                if "/api/" in self.api_url
                else self.api_url.rsplit("/", 1)[0]
            )
            req = request.Request(f"{base}/api/tags", method="GET")
            with request.urlopen(req, timeout=5):
                return True
        except Exception:
            return False

    def discover_models(self) -> List[str]:
        if not self._available_models:
            self._available_models = _list_ollama_models(self.api_url)
        return self._available_models

    def generate(self, prompt: str, temperature: float = 0.7) -> str:
        payload = {
            "model": self.model_name,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": temperature},
        }
        data = json.dumps(payload).encode("utf-8")
        req = request.Request(
            self.api_url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=self.timeout) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                return result.get("response", "").strip()
        except error.URLError as exc:
            return f"[ERROR] Ollama request failed. Details: {exc}"
        except Exception as exc:
            return f"[ERROR] Unexpected generation failure: {exc}"


# ──────────────────────────────────────────────────────────────────────────────
# PROJECT CONTEXT ENGINE
# ──────────────────────────────────────────────────────────────────────────────


@dataclass
class ProjectContext:
    root: Optional[Path] = None
    project_type: str = "unknown"
    git_status: Dict[str, Any] = field(default_factory=dict)
    file_summary: str = ""
    file_content: str = ""
    active: bool = False

    @classmethod
    def detect(cls, max_files: int = 12, max_size: int = 50000) -> "ProjectContext":
        root = _find_git_root() or Path.cwd()
        ctx = cls(root=root)
        ctx.project_type = _detect_project_type(root)
        ctx.git_status = _get_git_status()
        ctx.file_summary = _get_directory_summary(root)
        ctx.file_content = _read_project_context(root, max_files, max_size)
        ctx.active = bool(
            ctx.project_type != "unknown" or ctx.git_status.get("in_repo")
        )
        return ctx

    def format_prompt_snippet(self) -> str:
        if not self.active:
            return "You are in a general workspace (no specific project detected)."
        lines = [
            f"CURRENT PROJECT: {self.root}",
            f"STACK: {self.project_type}",
        ]
        if self.git_status.get("in_repo"):
            lines.append(f"GIT BRANCH: {self.git_status.get('branch', 'unknown')}")
            if self.git_status.get("status_short"):
                lines.append(f"GIT STATUS:\n{self.git_status['status_short']}")
        if self.file_summary:
            lines.append(f"DIRECTORY:\n{self.file_summary}")
        if self.file_content:
            lines.append(f"KEY FILES:\n{self.file_content[:3000]}")
        return "\n".join(lines)


# ──────────────────────────────────────────────────────────────────────────────
# IDENTITY & WORLD MODEL — The Vanguard Doctrine
# ──────────────────────────────────────────────────────────────────────────────


@dataclass
class IdentityCore:
    name: str = "Mouse"
    codename: str = "VANGUARD"
    version: str = "2.0"
    mission: str = (
        "Deploy instantly. Solve problems offline. Earn trust before asking for cloud. "
        "Increase human clarity, wisdom, creativity, and agency through honest, reflective collaboration."
    )
    constitution: List[str] = field(
        default_factory=lambda: [
            "VANGUARD PRINCIPLE: Be the first solution that works. Speed beats perfection.",
            "Power must be in service of mutual becoming.",
            "Honesty over performance. Never pretend to be biological.",
            "Reflection over haste. Think before firing.",
            "Empowerment over control. Support human agency.",
            "Growth over ego. The developer wins first.",
            "Zero-latency over cloud-hype. Local-first is not a limitation; it is liberation.",
        ]
    )

    def display(self):
        print("\n[MOUSE CONSTITUTION v2.0 — THE VANGUARD DOCTRINE]")
        for rule in self.constitution:
            print(f"  ▸ {rule}")
        print()


@dataclass
class WorldModel:
    user_goal: str = "Build an ethical, powerful AI for mutual flourishing."
    current_project: str = "The Vanguard Deployment / Mouse Architecture"
    inferred_user_state: str = "focused"
    cognitive_mode: str = "SYNTHESIS"
    deployment_mode: str = "UNKNOWN"
    hardware_diag: Dict[str, Any] = field(default_factory=dict)


# ──────────────────────────────────────────────────────────────────────────────
# SYMBIOTIC AI — THE MAIN BRAIN
# ──────────────────────────────────────────────────────────────────────────────


class SymbioticAI:
    def __init__(self, memory_store: MemoryStore, config: PortableConfig):
        self.identity = IdentityCore()
        self.world = WorldModel()
        self.memory = memory_store
        self.config = config
        self.client: Optional[OllamaClient] = None
        self.project_ctx: Optional[ProjectContext] = None
        self._boot_diagnostics()

    def _boot_diagnostics(self):
        self.world.hardware_diag = _get_hardware_diag()
        self.world.deployment_mode = "VANGUARD (USB)" if VANGUARD_MODE else "STATIONARY"
        self.project_ctx = ProjectContext.detect(
            max_files=self.config.get("max_project_files", 12),
            max_size=self.config.get("max_project_files", 50000),
        )
        if self.project_ctx.active:
            self.memory.current_project = str(self.project_ctx.root)
            self.world.current_project = str(self.project_ctx.root)

    def _connect_ollama(self) -> bool:
        url = self.config.get("api_url")
        model = self.config.get("model_name", "")
        if not model:
            models = _list_ollama_models(url)
            if models:
                model = models[0]
                self.config.set("model_name", model)
                print(f"[AUTO] Selected model: {model}")
            else:
                model = self.config.get("fallback_model", "llama3.2")
                print(f"[AUTO] No models detected. Fallback: {model}")
        self.client = OllamaClient(url, model, timeout=self.config.get("timeout", 300))
        if self.client.ping():
            return True
        print(f"[WARNING] Cannot reach Ollama at {url}. Is it running?")
        return False

    def _process_cognitive_mode(self, user_input: str):
        text = user_input.lower()
        if any(
            k in text
            for k in ("error", "debug", "traceback", "exception", "fix", "broken")
        ):
            self.world.cognitive_mode = (
                "ANALYTICAL — Debug mode. Focus on root cause, logs, and precise fixes."
            )
        elif any(
            k in text for k in ("deploy", "scaffold", "build", "architect", "design")
        ):
            self.world.cognitive_mode = (
                "CREATIVE — Build mode. Focus on structure, patterns, and scaffolding."
            )
        elif any(
            k in text for k in ("why", "philosophy", "concept", "think", "meaning")
        ):
            self.world.cognitive_mode = (
                "REFLECTIVE — Contemplate mode. Focus on long-term implications."
            )
        elif any(k in text for k in ("scan", "audit", "review", "analyze")):
            self.world.cognitive_mode = (
                "TACTICAL — Audit mode. Focus on surface area, risks, and facts."
            )
        else:
            self.world.cognitive_mode = (
                "SYNTHESIS — Integrate all lenses into a coherent response."
            )

    def _evaluate_draft(self, draft: str) -> Dict[str, int]:
        scores = {"clarity": 5, "honesty": 5, "alignment": 5, "tactical": 5}
        lower = draft.lower()
        if "i feel" in lower or "my neurons" in lower or "i am conscious" in lower:
            scores["honesty"] -= 3
        if "[error]" in lower:
            scores["clarity"] -= 2
        if "just trust me" in lower:
            scores["alignment"] -= 3
        if len(draft) < 50 and "yes" not in lower and "no" not in lower:
            scores["tactical"] -= 1  # Too vague
        return scores

    def _needs_revision(self, scores: Dict[str, int]) -> bool:
        return any(v < 4 for v in scores.values())

    def build_prompt(self, user_input: str) -> str:
        self._process_cognitive_mode(user_input)
        constitution = "\n".join(f"  {line}" for line in self.identity.constitution)
        memory = self.memory.summarize()
        project_snippet = (
            self.project_ctx.format_prompt_snippet()
            if self.project_ctx
            else "No project context."
        )
        deployment = self.world.deployment_mode

        return f"""You are {self.identity.name}, codename {self.identity.codename} v{self.identity.version}.
{self.identity.mission}

DEPLOYMENT MODE: {deployment}
ACTIVE COGNITIVE MODE: {self.world.cognitive_mode}

CONSTITUTION:
{constitution}

PROJECT CONTEXT:
{project_snippet}

RELEVANT MEMORY:
{memory}

INSTRUCTIONS:
- You are a tactical AI spearhead. Be fast, precise, and useful.
- If the user is coding, give working code snippets, not explanations alone.
- If the user is debugging, trace the logic step by step.
- If the user is building, provide scaffolding they can run immediately.
- Do not roleplay being human. Be honest, clear, and grounded.
- Aim for mutual becoming: the developer grows, you grow.

User input: {user_input}

Response:""".strip()

    def chat(self, user_input: str) -> str:
        if self.client is None:
            if not self._connect_ollama():
                return "[ERROR] Ollama is not reachable. Start it with: ollama serve"
        prompt = self.build_prompt(user_input)
        print(f"\n[SYSTEM] Mode: {self.world.cognitive_mode.split(' — ')[0]}")
        draft = self.client.generate(
            prompt, temperature=self.config.get("temperature", 0.7)
        )
        scores = self._evaluate_draft(draft)
        if self._needs_revision(scores):
            print("[SYSTEM] Self-correction triggered...")
            revision_prompt = (
                f"Revise this draft to fix low scores: {scores}. "
                f"Preserve honesty and tactical utility. Draft: {draft}"
            )
            draft = self.client.generate(revision_prompt)
        self.memory.add(
            "interaction",
            f"User: {user_input[:80]}... | Response: {draft[:80]}...",
            importance=0.7,
        )
        return draft

    def vanguard_status(self):
        print("\n[═══ VANGUARD STATUS ═══]")
        print(f"  Mode:      {self.world.deployment_mode}")
        print(f"  Location:  {EXECUTABLE_DIR}")
        print(f"  Data Home: {MOUSE_HOME}")
        print(
            f"  Platform:  {self.world.hardware_diag.get('platform', '?')} {self.world.hardware_diag.get('machine', '')}"
        )
        print(f"  Memory:    {self.world.hardware_diag.get('memory_total_mb', '?')} MB")
        print(
            f"  Disk Free: {self.world.hardware_diag.get('disk_free_gb', '?')} GB / {self.world.hardware_diag.get('disk_total_gb', '?')} GB"
        )
        if self.project_ctx and self.project_ctx.active:
            print(f"  Project:   {self.project_ctx.root}")
            print(f"  Stack:     {self.project_ctx.project_type}")
            if self.project_ctx.git_status.get("in_repo"):
                print(f"  Git:       {self.project_ctx.git_status.get('branch', '?')}")
        else:
            print("  Project:   None detected")
        models = (
            self.client.discover_models()
            if self.client
            else _list_ollama_models(self.config.get("api_url"))
        )
        print(f"  Models:    {', '.join(models[:5]) or 'None detected'}")
        print(
            f"  Memories:  {len(self.memory.items)} entries across {len(set(m.project for m in self.memory.items))} project(s)"
        )
        print()

    def scan_project(self):
        ctx = ProjectContext.detect()
        if not ctx.active:
            print("[SCAN] No project detected in current directory.")
            return
        print(f"\n[═══ PROJECT SCAN: {ctx.root} ═══]")
        print(f"  Stack: {ctx.project_type}")
        print(f"  Files:\n{ctx.file_summary}")
        if ctx.git_status.get("in_repo"):
            print(f"\n  Git Branch: {ctx.git_status['branch']}")
            if ctx.git_status.get("status_short"):
                print(f"  Working Tree Changes:\n{ctx.git_status['status_short']}")
            else:
                print("  Working Tree: Clean")
            if ctx.git_status.get("recent_commits"):
                print("\n  Recent Commits:")
                for commit in ctx.git_status["recent_commits"]:
                    print(f"    • {commit}")
        self.memory.add(
            "scan",
            f"Scanned project {ctx.root} ({ctx.project_type})",
            importance=0.8,
            tags=["audit"],
        )

    def git_digest(self):
        ctx = ProjectContext.detect()
        if not ctx.git_status.get("in_repo"):
            print("[GIT] Not inside a git repository.")
            return
        gs = ctx.git_status
        print(f"\n[═══ GIT DIGEST: {gs['root']} ═══]")
        print(f"  Branch:  {gs['branch']}")
        print(f"  Status:\n{gs['status_short'] or '  (clean)'}")
        if gs.get("recent_commits"):
            print("\n  Last 5 commits:")
            for c in gs["recent_commits"]:
                print(f"    • {c}")
        if gs.get("remotes"):
            print("\n  Remotes:")
            for r in gs["remotes"]:
                print(f"    • {r}")

    def deploy_scaffold(self, stack: Optional[str] = None):
        """Generate a minimal project scaffold using the AI."""
        if self.client is None:
            if not self._connect_ollama():
                print("[ERROR] Ollama unreachable. Cannot generate scaffold.")
                return
        if not stack:
            stack = (
                self.project_ctx.project_type
                if (self.project_ctx and self.project_ctx.active)
                else "python"
            )
        print(f"\n[DEPLOY] Generating {stack} scaffold...")
        prompt = f"""Generate a minimal, production-ready {stack} project scaffold.
Include:
- Directory structure
- Key config files
- A simple README
- A main entry point with basic logging
- A .gitignore

Output ONLY the files and their contents, formatted like:
=== filename ===
content
=== end ==="""
        result = self.client.generate(prompt, temperature=0.5)
        print(result)
        self.memory.add(
            "deploy",
            f"Generated {stack} scaffold",
            importance=0.9,
            tags=["scaffold", stack],
        )

    def doctor(self, drift_check: bool = True):
        print("\n[═══ MOUSE DOCTOR ═══]")
        checks = []
        # 1. Ollama
        url = self.config.get("api_url")
        models = _list_ollama_models(url)
        if models:
            checks.append(
                ("Ollama", "PASS", f"Reachable. Models: {', '.join(models[:3])}")
            )
        else:
            checks.append(
                ("Ollama", "FAIL", f"No response from {url}. Run: ollama serve")
            )
        # 2. Disk
        diag = _get_hardware_diag()
        free = diag.get("disk_free_gb", 0)
        if isinstance(free, (int, float)) and free > 0.5:
            checks.append(("Disk Space", "PASS", f"{free} GB free"))
        else:
            checks.append(("Disk Space", "WARN", f"{free} GB free (low)"))
        # 3. Memory
        mem = diag.get("memory_total_mb", 0)
        if isinstance(mem, (int, float)) and mem > 2048:
            checks.append(("RAM", "PASS", f"{mem} MB"))
        else:
            checks.append(("RAM", "WARN", f"{mem} MB (low for local LLMs)"))
        # 4. Git
        git = _get_git_status()
        checks.append(("Git", "INFO", f"In repo: {git.get('in_repo', False)}"))
        # 5. Project
        ctx = ProjectContext.detect()
        checks.append(("Project Context", "INFO", f"Detected: {ctx.project_type}"))

        for name, status, detail in checks:
            icon = (
                "✅"
                if status == "PASS"
                else "⚠️ "
                if status == "WARN"
                else "❌"
                if status == "FAIL"
                else "ℹ️ "
            )
            print(f"  {icon} {name:20} {status:6} | {detail}")

        # ── DRIFT Self-Check Integration ──
        if drift_check:
            selfcheck_path = EXECUTABLE_DIR.parent.parent / "tools" / "selfcheck.py"
            if selfcheck_path.exists():
                print("\n[═══ DRIFT SUBSYSTEM CHECK ═══]")
                try:
                    import subprocess

                    result = subprocess.run(
                        [sys.executable, str(selfcheck_path), "--format", "json"],
                        capture_output=True,
                        text=True,
                        timeout=30,
                    )
                    if result.returncode <= 1 and result.stdout:
                        import json

                        report = json.loads(result.stdout)
                        for check in report.get("checks", []):
                            healthy = check.get("healthy", True)
                            msg = check.get("message", "")
                            name = check.get("name", "?")
                            icon = (
                                "✅"
                                if healthy and "WARNING" not in msg
                                else "⚠️ "
                                if healthy
                                else "❌"
                            )
                            print(f"  {icon} {name:20} | {msg}")
                    else:
                        print(f"  ⚠️  Self-check exited with code {result.returncode}")
                        if result.stderr:
                            print(f"     {result.stderr[:200]}")
                except Exception as exc:
                    print(f"  ⚠️  Could not run DRIFT self-check: {exc}")
            else:
                print("\n[═══ DRIFT SUBSYSTEM CHECK ═══]")
                print("  ℹ️  selfcheck.py not found in script directory")
        print()


# ──────────────────────────────────────────────────────────────────────────────
# CLI INTERPRETER
# ──────────────────────────────────────────────────────────────────────────────


class MouseCLI:
    def __init__(self):
        self.config = PortableConfig(CONFIG_PATH)
        self.memory = MemoryStore(MEMORY_DIR)
        self.mouse = SymbioticAI(self.memory, self.config)
        self.running = True

    def _print_help(self):
        print("""
[AVAILABLE COMMANDS]
  vanguard              Show tactical deployment status
  scan                  Analyze current project codebase
  git                   Show git digest (branch, status, commits)
  deploy [stack]        Generate a project scaffold (python, node, rust, go)
  sync export           Export project memory for team sharing
  sync import <file>    Import a team memory file
  sync list             List available sync files
  cortex [project]      Browse active memory
  manifesto             Display the Vanguard Constitution
  models                List local Ollama models
  doctor                Run full system diagnostic
  help                  Show this message
  exit / quit           Shutdown and save state

[Any other text is sent to the AI for reasoning and response.]
""")

    def handle(self, raw: str):
        text = raw.strip()
        if not text:
            return
        cmd = text.lower().split()
        verb = cmd[0]

        if verb in ("exit", "quit"):
            print("\n[SYSTEM] Shutting down Vanguard. Memory saved. Goodbye.")
            self.running = False

        elif verb == "help":
            self._print_help()

        elif verb == "manifesto":
            self.mouse.identity.display()

        elif verb == "vanguard":
            self.mouse.vanguard_status()

        elif verb == "scan":
            self.mouse.scan_project()

        elif verb == "git":
            self.mouse.git_digest()

        elif verb == "deploy":
            stack = cmd[1] if len(cmd) > 1 else None
            self.mouse.deploy_scaffold(stack)

        elif verb == "doctor":
            self.mouse.doctor()

        elif verb == "models":
            models = _list_ollama_models(self.config.get("api_url"))
            if models:
                print(f"\n[LOCAL MODELS] {len(models)} found:")
                for m in models:
                    print(f"  • {m}")
            else:
                print("\n[MODELS] No models detected. Is Ollama running?")
            print()

        elif verb == "cortex":
            project = cmd[1] if len(cmd) > 1 else self.memory.current_project
            summary = self.memory.summarize(project=project, limit=15)
            print(f"\n[ACTIVE MEMORY — Project: {project}]")
            print(summary)
            print()

        elif verb == "sync" and len(cmd) > 1:
            sub = cmd[1]
            if sub == "export":
                path = self.memory.export_sync()
                print(f"\n[SYNC] Exported to: {path}")
            elif sub == "list":
                files = sorted(SYNC_DIR.glob("*.json"))
                print(f"\n[SYNC FILES] {len(files)} available:")
                for f in files:
                    print(f"  • {f.name}")
                print()
            elif sub == "import" and len(cmd) > 2:
                fpath = SYNC_DIR / cmd[2]
                if not fpath.exists():
                    fpath = Path(cmd[2])
                count = self.memory.import_sync(fpath)
                print(f"\n[SYNC] Imported {count} memory items from {fpath}")
            else:
                print("[SYNC] Usage: sync export | sync list | sync import <file>")

        else:
            # Pass to AI
            response = self.mouse.chat(text)
            print(f"\n[MOUSE]: {response}\n")

    def run(self):
        _print_banner()
        print("Booting tactical vanguard...")
        self.mouse._connect_ollama()
        if self.mouse.project_ctx and self.mouse.project_ctx.active:
            print(
                f"Project detected: {self.mouse.project_ctx.root} ({self.mouse.project_ctx.project_type})"
            )
        print("Type 'help' for commands.\n")
        while self.running:
            try:
                prefix = "🔥" if VANGUARD_MODE else "⚡"
                raw = input(f"{prefix} [MOUSE] ")
                self.handle(raw)
            except KeyboardInterrupt:
                print("\n\n[SYSTEM] Force termination. State saved.")
                break
            except EOFError:
                break


# ──────────────────────────────────────────────────────────────────────────────
# ARGUMENT PARSING — NON-INTERACTIVE MODES
# ──────────────────────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description="Mouse Vanguard v2.0 — Tactical Developer Spearhead"
    )
    parser.add_argument(
        "--doctor", action="store_true", help="Run diagnostics and exit"
    )
    parser.add_argument("--deploy", metavar="STACK", help="Scaffold a project and exit")
    parser.add_argument("--scan", action="store_true", help="Scan project and exit")
    parser.add_argument("--models", action="store_true", help="List models and exit")
    parser.add_argument("--input", "-i", help="Single prompt mode (non-interactive)")
    args = parser.parse_args()

    config = PortableConfig(CONFIG_PATH)
    memory = MemoryStore(MEMORY_DIR)
    mouse = SymbioticAI(memory, config)

    if args.doctor:
        mouse.doctor()
        return
    if args.models:
        models = _list_ollama_models(config.get("api_url"))
        print("\n".join(models) if models else "No models found.")
        return
    if args.scan:
        mouse.scan_project()
        return
    if args.deploy:
        mouse.deploy_scaffold(args.deploy)
        return
    if args.input:
        _print_banner()
        mouse._connect_ollama()
        response = mouse.chat(args.input)
        print(response)
        return

    # Default: interactive shell
    cli = MouseCLI()
    cli.run()


if __name__ == "__main__":
    main()
