"""Lightweight cognitive-dissonance heuristics (lexical tension markers)."""

from __future__ import annotations

import re
from typing import Any, Dict, List


def detect_dissonance(text: str) -> Dict[str, Any]:
    """Score inner tension from contrast markers (e.g. want vs need, 'but', split self)."""
    t = text.lower()
    score = 0.0
    markers: List[str] = []

    if re.search(r"\bbut\b", t):
        score += 0.35
        markers.append("but")

    if re.search(r"\b(yet|however|although)\b", t):
        score += 0.18
        if "contradiction" not in markers:
            markers.append("contradiction")

    if "want" in t and "but" in t:
        score += 0.2

    if "quit" in t and "need" in t:
        score += 0.15

    if "part of me" in t or "on the one hand" in t or "on the other hand" in t:
        score += 0.22
        markers.append("split")

    score = min(score, 1.0)

    values: List[str] = []
    if "quit" in t and ("money" in t or "need" in t):
        values.append("autonomy")

    # De-duplicate markers
    seen: set[str] = set()
    uniq = []
    for m in markers:
        if m not in seen:
            seen.add(m)
            uniq.append(m)

    return {"score": score, "markers": uniq, "values": values}


def dissonance_prompt_hint(dissonance: Dict[str, Any]) -> str:
    s = float(dissonance.get("score", 0.0))
    if s < 0.2:
        return "No strong tension detected; respond with open curiosity."
    vals = dissonance.get("values") or []
    extra = f" Values in tension: {', '.join(vals)}." if vals else ""
    return f"Cognitive dissonance: elevated tension ({s:.2f}). Acknowledge both pulls.{extra}"


def map_dissonance(text: str) -> str:
    d = detect_dissonance(text)
    lines = [
        "Cognitive dissonance map",
        f"— score: {d['score']:.2f}",
        f"— markers: {', '.join(d['markers']) or 'none'}",
    ]
    return "\n".join(lines)
