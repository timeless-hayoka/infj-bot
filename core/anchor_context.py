"""ANCHOR vault runtime context for Drift chat, tools, and API paths."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from drift.config_adapter import (
    ANCHOR_KNOWLEDGE_DIR,
    ANCHOR_VAULT_ROOT,
    PERSIST_DIRECTORY,
    get_anchor_knowledge_chroma_dir,
    get_anchor_knowledge_dir,
    get_anchor_vault_root,
)

_knowledge_provider: Any | None = None


def resolve_anchor_repo_root() -> Path | None:
    """Locate the ANCHOR git repo that owns the structured `knowledge/` corpus."""
    env = os.getenv("ANCHOR_ROOT", "").strip()
    candidates: list[Path] = []
    if env:
        candidates.append(Path(env).expanduser())
    infj_root = Path(__file__).resolve().parents[1]
    candidates.append(infj_root.parent / "ANCHOR")
    candidates.append(infj_root / "ANCHOR")
    for path in candidates:
        resolved = path.resolve()
        if (resolved / "knowledge" / "manifest.json").is_file():
            return resolved
    return None


def get_anchor_knowledge_provider():
    """Return a cached KnowledgeProvider for the ANCHOR repo, or None if unavailable."""
    global _knowledge_provider
    root = resolve_anchor_repo_root()
    if root is None:
        return None
    if _knowledge_provider is not None and getattr(_knowledge_provider, "root", None) == (root / "knowledge").resolve():
        return _knowledge_provider

    root_str = str(root)
    if root_str not in sys.path:
        sys.path.insert(0, root_str)
    from knowledge_provider import KnowledgeProvider

    _knowledge_provider = KnowledgeProvider(root / "knowledge")
    return _knowledge_provider


def list_anchor_repo_knowledge() -> list[dict[str, Any]]:
    provider = get_anchor_knowledge_provider()
    if provider is None:
        return []
    return [topic.to_dict() for topic in provider.list_topics()]


def search_anchor_repo_knowledge(query: str, *, limit: int = 5) -> list[dict[str, Any]]:
    provider = get_anchor_knowledge_provider()
    if provider is None or not query.strip():
        return []
    return [hit.to_dict() for hit in provider.search(query.strip(), limit=max(1, min(limit, 20)))]


def get_anchor_repo_knowledge_topic(slug: str) -> dict[str, Any] | None:
    provider = get_anchor_knowledge_provider()
    if provider is None or not slug.strip():
        return None
    try:
        return provider.get(slug.strip())
    except (KeyError, FileNotFoundError):
        return None


def refs_anchor_repo_knowledge(subsystem: str) -> list[dict[str, Any]]:
    provider = get_anchor_knowledge_provider()
    if provider is None or not subsystem.strip():
        return []
    return [topic.to_dict() for topic in provider.refs_for_subsystem(subsystem.strip())]


def format_anchor_repo_knowledge_status() -> str:
    root = resolve_anchor_repo_root()
    provider = get_anchor_knowledge_provider()
    if root is None or provider is None:
        return (
            "ANCHOR structured knowledge corpus not found. "
            "Set ANCHOR_ROOT to the ANCHOR repo or place it beside infj_bot."
        )
    topics = provider.list_topics()
    return (
        f"ANCHOR structured knowledge corpus\n"
        f"- Repo root: {root}\n"
        f"- Knowledge dir: {root / 'knowledge'}\n"
        f"- Registered topics: {len(topics)}"
    )


def get_anchor_runtime() -> dict[str, Any]:
    """Resolved ANCHOR vault paths for the current process."""
    vault = get_anchor_vault_root()
    knowledge = get_anchor_knowledge_dir()
    chroma = get_anchor_knowledge_chroma_dir()
    anchor_data = os.getenv("ANCHOR_DATA_ROOT", "").strip() or None
    return {
        "configured": vault is not None and vault.exists(),
        "anchor_data_root": anchor_data,
        "vault_root": str(vault) if vault else None,
        "knowledge_root": str(knowledge) if knowledge else None,
        "knowledge_chroma_dir": str(chroma) if chroma else str(PERSIST_DIRECTORY),
        "knowledge_source": "anchor_vault" if knowledge and knowledge.is_dir() else "local",
    }


def format_anchor_vault_prompt_block() -> str:
    """Prompt block so Drift knows where ANCHOR vault knowledge lives."""
    runtime = get_anchor_runtime()
    if not runtime["configured"]:
        return (
            "[ANCHOR Vault]\n"
            "No ANCHOR vault is mounted. Set ANCHOR_DATA_ROOT or ANCHOR_VAULT_ROOT "
            "in ~/.drift_os/config/storage.env and restart Drift."
        )

    vault = runtime["vault_root"]
    knowledge = runtime["knowledge_root"]
    chroma = runtime["knowledge_chroma_dir"]
    return (
        "[ANCHOR Vault — authoritative knowledge store]\n"
        f"- Vault root: {vault}\n"
        f"- Knowledge corpus (read/ingest from here): {knowledge}\n"
        f"- Document RAG index (Chroma): {chroma}\n"
        f"- Anchor data root: {runtime['anchor_data_root'] or 'derived from vault'}\n"
        "When the user asks about ANCHOR, Trinity evidence, benchmarks, or stored "
        "research, treat this vault as the source of truth. Prefer structured repo docs "
        "via anchor_knowledge_search / anchor_knowledge_get; use vault_knowledge_search "
        "for mirrored vault files; use document_search after ingest."
    )


def search_vault_knowledge(query: str, n_results: int = 5) -> list[dict[str, str]]:
    """Search vault markdown/text files when Chroma has no hits (ripgrep if available)."""
    knowledge = get_anchor_knowledge_dir()
    if not knowledge or not query.strip():
        return []

    pattern = query.strip()
    limit = max(1, min(n_results, 10))
    hits: list[dict[str, str]] = []

    rg = _rg_search(knowledge, pattern, limit)
    if rg:
        return rg

    # Fallback: filename match + first matching line in small text files
    query_lower = pattern.lower()
    for path in sorted(knowledge.rglob("*")):
        if len(hits) >= limit:
            break
        if not path.is_file():
            continue
        if path.suffix.lower() not in {".md", ".txt", ".csv", ".json", ".py"}:
            continue
        if path.stat().st_size > 500_000:
            continue
        name_hit = query_lower in path.name.lower()
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if not name_hit and query_lower not in text.lower():
            continue
        snippet = _extract_snippet(text, query_lower)
        hits.append(
            {
                "source": str(path),
                "filename": path.name,
                "document": snippet,
            }
        )
    return hits


def _rg_search(knowledge: Path, pattern: str, limit: int) -> list[dict[str, str]]:
    try:
        res = subprocess.run(
            [
                "rg",
                "-i",
                "--no-heading",
                "--max-count",
                "1",
                "-m",
                "1",
                pattern,
                str(knowledge),
            ],
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []

    if res.returncode not in (0, 1) or not res.stdout.strip():
        return []

    hits: list[dict[str, str]] = []
    for line in res.stdout.splitlines():
        if len(hits) >= limit:
            break
        if ":" not in line:
            continue
        path_str, _, excerpt = line.partition(":")
        path = Path(path_str)
        hits.append(
            {
                "source": str(path),
                "filename": path.name,
                "document": excerpt.strip()[:600],
            }
        )
    return hits


def _extract_snippet(text: str, query_lower: str, window: int = 300) -> str:
    idx = text.lower().find(query_lower)
    if idx < 0:
        return text[:window]
    start = max(0, idx - window // 2)
    return text[start : start + window].strip()
