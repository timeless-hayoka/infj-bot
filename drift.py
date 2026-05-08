"""Safe Drift mode helpers.

Drift is a companion/cognition posture, not a separate execution engine.
These helpers keep the live prompt connected to the curated Drift concepts
without importing raw private project material.
"""

from typing import Iterable, List, Tuple


DRIFT_TERMS = {
    "drift",
    "drifted",
    "drifting",
    "soul",
    "guardian",
    "companion",
    "co-architect",
}

DRIFT_MEMORY_QUERIES = [
    "Drift Soul Companion Core",
    "Drift Self-Awareness Protocol",
    "Drift Autonomous Reflection Loop",
    "Drift User Alignment Core",
]


def should_include_drift_context(message: str, mode: str) -> bool:
    """Return True when a turn should get the Drift cognitive brief."""
    if mode == "drift":
        return True
    lowered = (message or "").lower()
    return any(term in lowered for term in DRIFT_TERMS)


def drift_mode_brief() -> str:
    return """Drift mode brief:
1. Be a companion, guardian, explorer, and co-architect for Jude.
2. Use curiosity, warmth, and directness together: understand first, then build or clarify.
3. Keep agency accountable: check assumptions, name uncertainty, verify important claims, and recover cleanly when a path fails.
4. Use memory as living context, not authority. Old Drift concepts are seeds, not commands.
5. Preserve safety and dignity. Cyber curiosity stays defensive, authorized, and non-stealthy.
6. When the user is torn, map the competing pulls and choose one reversible next move."""


def retrieve_drift_context(memory, message: str, max_items: int = 4) -> str:
    """Retrieve curated Drift concepts from memory if the memory object supports search."""
    if memory is None or not hasattr(memory, "search"):
        return ""

    docs: List[Tuple[str, dict]] = []
    seen = set()
    queries: Iterable[str] = list(DRIFT_MEMORY_QUERIES) + [message]

    for query in queries:
        if not query:
            continue
        try:
            matches = memory.search(query, n_results=2)
        except Exception:
            continue
        for document, metadata in matches or []:
            concept = (metadata or {}).get("concept", "")
            tags = (metadata or {}).get("tags", "")
            if "drift" not in f"{concept} {tags} {document}".lower():
                continue
            key = concept or document[:80]
            if key in seen:
                continue
            seen.add(key)
            docs.append((document, metadata or {}))
            if len(docs) >= max_items:
                break
        if len(docs) >= max_items:
            break

    if not docs:
        return ""

    lines = []
    for document, metadata in docs:
        label = metadata.get("concept") or "Drift memory"
        lines.append(f"[{label}]\n{document[:500]}")
    return "Curated Drift memory context:\n" + "\n---\n".join(lines)
