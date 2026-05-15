"""prompt_budget.py — Token-aware prompt budgeting, deduplication, and debug visibility.

Provides per-tier accounting so the prompt builder knows exactly how much
budget each layer consumes, can detect overlapping instructions, and can
dump the final structured prompt for debugging.
"""

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("drift")

# Rough heuristic: ~4 chars per token for English text
CHARS_PER_TOKEN = 4.0


@dataclass
class BudgetTier:
    """A single tier in the prompt budget."""
    name: str
    max_chars: int
    current_chars: int = 0
    sections: List[Dict[str, Any]] = field(default_factory=list)

    def add(self, text: str, label: str = "") -> bool:
        """Add text to this tier. Returns False if it would exceed the budget."""
        chars = len(text)
        if self.current_chars + chars > self.max_chars:
            logger.debug("Tier '%s' overflow: %d + %d > %d", self.name, self.current_chars, chars, self.max_chars)
            return False
        self.current_chars += chars
        self.sections.append({"label": label or f"section-{len(self.sections)}", "text": text, "chars": chars})
        return True

    def trim_to_fit(self, text: str) -> str:
        """Trim text to fit remaining budget. Returns trimmed text."""
        remaining = self.max_chars - self.current_chars
        suffix = "\n...[trimmed]\n"
        if remaining <= 0:
            return ""
        if len(text) + len(suffix) <= remaining:
            return text
        # Trim to last complete sentence or line
        trimmed = text[: max(0, remaining - len(suffix))]
        # Try to end on a newline or sentence boundary
        for delim in ["\n\n", "\n", ". ", "; "]:
            idx = trimmed.rfind(delim)
            if idx > len(trimmed) * 0.7:
                trimmed = trimmed[: idx + len(delim)]
                break
        return trimmed + suffix

    @property
    def tokens(self) -> int:
        return int(self.current_chars / CHARS_PER_TOKEN)

    @property
    def remaining_chars(self) -> int:
        return self.max_chars - self.current_chars

    @property
    def utilization(self) -> float:
        return self.current_chars / self.max_chars if self.max_chars > 0 else 0.0


class PromptBudget:
    """Tracks prompt construction across tiers with budget limits."""

    def __init__(
        self,
        max_total_chars: int = 12000,
        core_budget: int = 3000,
        cognitive_budget: int = 4000,
        analysis_budget: int = 2500,
        context_budget: int = 2500,
    ):
        self.max_total_chars = max_total_chars
        self.tiers: Dict[str, BudgetTier] = {
            "core": BudgetTier("core", core_budget),
            "cognitive": BudgetTier("cognitive", cognitive_budget),
            "analysis": BudgetTier("analysis", analysis_budget),
            "context": BudgetTier("context", context_budget),
        }
        self.footer: str = ""
        self.overlaps: List[Dict] = []
        self.debug_path: Optional[Path] = None

    def add(self, tier_name: str, text: str, label: str = "") -> bool:
        """Add text to a named tier."""
        tier = self.tiers.get(tier_name)
        if tier is None:
            logger.warning("Unknown tier '%s', using 'cognitive'", tier_name)
            tier = self.tiers["cognitive"]
        return tier.add(text, label=label)

    def set_footer(self, footer: str):
        self.footer = footer

    def total_chars(self) -> int:
        return sum(t.current_chars for t in self.tiers.values()) + len(self.footer)

    def total_tokens(self) -> int:
        return int(self.total_chars() / CHARS_PER_TOKEN)

    def check_overlaps(self) -> List[Dict]:
        """Detect redundant or overlapping phrases across tiers."""
        self.overlaps = []
        all_phrases: Dict[str, List[Tuple[str, str]]] = {}

        # Extract normalized phrases (3+ word sequences) from each section
        for tier_name, tier in self.tiers.items():
            for section in tier.sections:
                text = section["text"]
                words = re.findall(r"[a-zA-Z']{3,}", text.lower())
                for i in range(len(words) - 2):
                    phrase = " ".join(words[i : i + 3])
                    if phrase not in all_phrases:
                        all_phrases[phrase] = []
                    all_phrases[phrase].append((tier_name, section["label"]))

        # Report phrases that appear in 2+ different tiers
        for phrase, locations in all_phrases.items():
            tiers_seen = set(loc[0] for loc in locations)
            if len(tiers_seen) >= 2:
                self.overlaps.append({
                    "phrase": phrase,
                    "count": len(locations),
                    "tiers": sorted(tiers_seen),
                })

        # Sort by count descending
        self.overlaps.sort(key=lambda x: x["count"], reverse=True)
        return self.overlaps

    def assemble(self) -> str:
        """Build the final prompt string from all tiers."""
        parts = []
        for name in ["core", "cognitive", "analysis", "context"]:
            tier = self.tiers[name]
            for section in tier.sections:
                parts.append(section["text"])
        if self.footer:
            parts.append(self.footer)
        return "\n".join(parts)

    def trim_to_budget(self) -> str:
        """Progressively trim tiers until the total fits within max_total_chars."""
        # First, try trimming context tier (docs, tools, memory)
        while self.total_chars() > self.max_total_chars and self.tiers["context"].sections:
            # Remove last section from context
            removed = self.tiers["context"].sections.pop()
            self.tiers["context"].current_chars -= removed["chars"]

        # Then trim analysis
        while self.total_chars() > self.max_total_chars and self.tiers["analysis"].sections:
            removed = self.tiers["analysis"].sections.pop()
            self.tiers["analysis"].current_chars -= removed["chars"]

        # Then trim cognitive
        while self.total_chars() > self.max_total_chars and self.tiers["cognitive"].sections:
            removed = self.tiers["cognitive"].sections.pop()
            self.tiers["cognitive"].current_chars -= removed["chars"]

        # Last resort: hard truncate entire prompt
        assembled = self.assemble()
        if len(assembled) > self.max_total_chars:
            assembled = assembled[: self.max_total_chars - 100] + "\n...[prompt trimmed]\n" + self.footer

        return assembled

    def report(self) -> str:
        """Return a human-readable budget report."""
        lines = ["=== PROMPT BUDGET ==="]
        for name in ["core", "cognitive", "analysis", "context"]:
            tier = self.tiers[name]
            lines.append(
                f"  {name:10s}: {tier.current_chars:5d} / {tier.max_chars:5d} chars "
                f"({tier.utilization:5.1%})  ~{tier.tokens} tokens"
            )
        lines.append(f"  {'TOTAL':10s}: {self.total_chars():5d} / {self.max_total_chars:5d} chars  ~{self.total_tokens()} tokens")
        if self.overlaps:
            lines.append(f"\n  Overlaps detected: {len(self.overlaps)}")
            for ov in self.overlaps[:5]:
                lines.append(f"    '{ov['phrase']}' in {', '.join(ov['tiers'])} ({ov['count']}x)")
        return "\n".join(lines)

    def dump(self, path: Optional[Path] = None) -> Path:
        """Dump the full prompt structure to a JSON file for debugging."""
        if path is None:
            timestamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
            path = Path("data") / f"prompt_debug_{timestamp}.json"
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)

        payload = {
            "timestamp": datetime.now().isoformat(),
            "budget": {
                "max_total_chars": self.max_total_chars,
                "total_chars": self.total_chars(),
                "total_tokens": self.total_tokens(),
                "tiers": {
                    name: {
                        "max_chars": tier.max_chars,
                        "current_chars": tier.current_chars,
                        "tokens": tier.tokens,
                        "utilization": tier.utilization,
                        "section_count": len(tier.sections),
                    }
                    for name, tier in self.tiers.items()
                },
            },
            "overlaps": self.overlaps[:20],
            "assembled_prompt": self.assemble(),
            "sections": [
                {
                    "tier": name,
                    "label": sec["label"],
                    "chars": sec["chars"],
                    "text": sec["text"],
                }
                for name in ["core", "cognitive", "analysis", "context"]
                for sec in self.tiers[name].sections
            ],
        }
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        logger.info("Prompt debug dump written to %s", path)
        return path
