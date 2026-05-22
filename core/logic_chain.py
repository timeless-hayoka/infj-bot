"""Logic Chain — Reasoning trace and backtracking memory for DRIFT.

Tracks attempted solution paths so the bot doesn't retry failed approaches.
Design:
- Each ChainNode = one reasoning step (approach + result + status)
- LogicChain = a tree of nodes for a specific problem/query fingerprint
- ChainMemory = persists chains to DriftMemory (survives across sessions)
- ChainNavigator = main API: find chains, suggest next moves, avoid repeats

Usage:
    navigator = ChainNavigator(memory)
    chain = navigator.find_or_create("how do I fix this auth bug?")
    tried = chain.list_tried_approaches()
    # ... after generating a response ...
    chain.add_step(approach="check JWT expiry", result="token was valid", status="failure")
    navigator.save(chain)
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Set, Tuple


# ── Helpers ─────────────────────────────────────────────────────────

def _fingerprint_query(query: str) -> str:
    """Create a stable fingerprint for a query so similar queries match the same chain."""
    # Lowercase, strip punctuation, sort words, hash first 60 chars
    cleaned = re.sub(r"[^a-z0-9\s]", "", query.lower()).strip()
    words = sorted(set(cleaned.split()))
    signature = " ".join(words[:12])  # top 12 unique words
    return hashlib.sha256(signature.encode()).hexdigest()[:16]


def _extract_approach(text: str) -> str:
    """Heuristic: extract the approach/strategy from a response snippet."""
    # Look for lead sentences that suggest a strategy
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    for line in lines[:5]:
        lowered = line.lower()
        if any(k in lowered for k in ("try", "check", "look at", "inspect", "verify", "test", "examine", "consider", "first", "start by", "maybe")):
            return line[:200]
    return lines[0][:200] if lines else "unknown approach"


# ── Data classes ────────────────────────────────────────────────────

@dataclass
class ChainNode:
    """A single step in a reasoning chain."""
    approach: str           # What strategy was attempted
    result: str = ""        # What happened (outcome, observation)
    status: str = "unknown"  # "success" | "failure" | "partial" | "unknown"
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    iteration: int = 0      # Which attempt number this was
    notes: str = ""         # Freeform context

    def to_dict(self) -> Dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict) -> "ChainNode":
        return cls(**d)


@dataclass
class LogicChain:
    """A reasoning chain for a specific problem."""
    chain_id: str
    fingerprint: str        # Hash of the query signature
    query: str              # Original query that started this chain
    nodes: List[ChainNode] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    status: str = "open"    # "open" | "resolved" | "abandoned"
    tags: List[str] = field(default_factory=list)

    def add_step(self, approach: str, result: str = "", status: str = "unknown", notes: str = "") -> ChainNode:
        node = ChainNode(
            approach=approach,
            result=result,
            status=status,
            iteration=len(self.nodes) + 1,
            notes=notes,
        )
        self.nodes.append(node)
        self.updated_at = datetime.now().isoformat(timespec="seconds")
        if status == "success":
            self.status = "resolved"
        return node

    def list_tried_approaches(self, status_filter: Optional[Set[str]] = None) -> List[ChainNode]:
        """Return approaches already attempted, optionally filtered by status."""
        if status_filter is None:
            return list(self.nodes)
        return [n for n in self.nodes if n.status in status_filter]

    def list_failed_approaches(self) -> List[ChainNode]:
        return self.list_tried_approaches({"failure", "partial"})

    def list_successful_approaches(self) -> List[ChainNode]:
        return self.list_tried_approaches({"success"})

    def has_tried(self, approach_text: str) -> bool:
        """Check if a semantically similar approach was already tried."""
        cleaned = approach_text.lower().strip()
        for node in self.nodes:
            existing = node.approach.lower().strip()
            # Simple overlap heuristic — shared significant words
            existing_words = set(re.findall(r"\b\w{4,}\b", existing))
            new_words = set(re.findall(r"\b\w{4,}\b", cleaned))
            if existing_words and new_words:
                overlap = len(existing_words & new_words) / max(len(existing_words), len(new_words))
                if overlap > 0.6:
                    return True
            # Direct substring
            if cleaned in existing or existing in cleaned:
                return True
        return False

    def format_prompt_block(self, max_nodes: int = 5) -> str:
        """Format chain history for injection into an LLM prompt."""
        if not self.nodes:
            return ""
        lines = ["[REASONING CHAIN — previously tried approaches:]"]
        for node in self.nodes[-max_nodes:]:
            icon = {"success": "✓", "failure": "✗", "partial": "~", "unknown": "?"}.get(node.status, "?")
            lines.append(f"  {icon} Step {node.iteration}: {node.approach[:100]}")
            if node.result:
                lines.append(f"      → {node.result[:120]}")
        lines.append("[Do NOT repeat failed approaches. Try something different.]")
        return "\n".join(lines)

    def to_dict(self) -> Dict:
        return {
            "chain_id": self.chain_id,
            "fingerprint": self.fingerprint,
            "query": self.query,
            "nodes": [n.to_dict() for n in self.nodes],
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "status": self.status,
            "tags": self.tags,
        }

    @classmethod
    def from_dict(cls, d: Dict) -> "LogicChain":
        chain = cls(
            chain_id=d["chain_id"],
            fingerprint=d["fingerprint"],
            query=d["query"],
            created_at=d.get("created_at", ""),
            updated_at=d.get("updated_at", ""),
            status=d.get("status", "open"),
            tags=d.get("tags", []),
        )
        chain.nodes = [ChainNode.from_dict(n) for n in d.get("nodes", [])]
        return chain


# ── Chain Memory ────────────────────────────────────────────────────

class ChainMemory:
    """Persists LogicChains to DriftMemory using tagged concepts."""

    def __init__(self, drift_memory):
        self.memory = drift_memory

    def _make_concept_name(self, chain: LogicChain) -> str:
        return f"logic_chain:{chain.chain_id}"

    def save(self, chain: LogicChain):
        """Persist a chain to long-term memory."""
        if not self.memory:
            return
        payload = json.dumps(chain.to_dict())
        self.memory.learn_concept(
            concept_name=self._make_concept_name(chain),
            description=payload,
            tags=["logic_chain", "reasoning", "backtracking"] + chain.tags,
            importance=0.85,
        )

    def load(self, chain_id: str) -> Optional[LogicChain]:
        """Load a chain by ID from memory."""
        if not self.memory:
            return None
        try:
            # Try semantic recall first
            results = self.memory.retrieve_context(
                f"logic_chain:{chain_id}", n_results=3, include_metadata=True
            )
            if isinstance(results, list):
                for content, meta in results:
                    if chain_id in content:
                        # Extract JSON from concept description
                        if "Concept:" in content and "Description:" in content:
                            desc = content.split("Description:", 1)[1].strip()
                        else:
                            desc = content
                        data = json.loads(desc)
                        return LogicChain.from_dict(data)
            elif isinstance(results, str):
                # Fallback to raw string parsing
                if chain_id in results:
                    data = json.loads(results.split("Description:", 1)[1].strip())
                    return LogicChain.from_dict(data)
        except Exception:
            pass
        return None

    def find_by_fingerprint(self, fingerprint: str) -> List[LogicChain]:
        """Find all chains matching a query fingerprint."""
        if not self.memory:
            return []
        chains = []
        try:
            # Use memory retrieve with a query that targets logic chains
            results = self.memory.retrieve_context(
                "logic_chain reasoning backtracking", n_results=10, include_metadata=True
            )
            if isinstance(results, list):
                for content, meta in results:
                    try:
                        if "logic_chain:" in content:
                            desc = content.split("Description:", 1)[1].strip() if "Description:" in content else content
                            data = json.loads(desc)
                            if data.get("fingerprint") == fingerprint:
                                chains.append(LogicChain.from_dict(data))
                    except Exception:
                        continue
        except Exception:
            pass
        return chains


# ── Chain Navigator ─────────────────────────────────────────────────

class ChainNavigator:
    """Main interface for managing reasoning chains."""

    def __init__(self, drift_memory=None):
        self.chain_mem = ChainMemory(drift_memory) if drift_memory else None
        self._active_chains: Dict[str, LogicChain] = {}  # in-session cache

    def find_or_create(self, query: str) -> LogicChain:
        """Find an existing chain for this query, or create a new one."""
        fp = _fingerprint_query(query)

        # Check session cache
        for chain in self._active_chains.values():
            if chain.fingerprint == fp:
                return chain

        # Try loading from memory
        if self.chain_mem:
            matches = self.chain_mem.find_by_fingerprint(fp)
            if matches:
                best = sorted(matches, key=lambda c: len(c.nodes), reverse=True)[0]
                self._active_chains[best.chain_id] = best
                return best

        # Create new
        chain_id = f"chain_{fp}_{datetime.now().strftime('%H%M%S')}"
        chain = LogicChain(
            chain_id=chain_id,
            fingerprint=fp,
            query=query,
            tags=["auto"],
        )
        self._active_chains[chain_id] = chain
        return chain

    def record_step(self, query: str, approach: str, result: str = "", status: str = "unknown", notes: str = ""):
        """Record a reasoning step for the given query."""
        chain = self.find_or_create(query)
        chain.add_step(approach=approach, result=result, status=status, notes=notes)
        if self.chain_mem:
            self.chain_mem.save(chain)
        return chain

    def get_prompt_block(self, query: str) -> str:
        """Get formatted chain history for prompt injection."""
        chain = self.find_or_create(query)
        return chain.format_prompt_block()

    def should_avoid(self, query: str, proposed_approach: str) -> Tuple[bool, Optional[str]]:
        """Check if a proposed approach was already tried and failed."""
        chain = self.find_or_create(query)
        if chain.has_tried(proposed_approach):
            failed = chain.list_failed_approaches()
            for node in failed:
                if node.approach.lower() in proposed_approach.lower() or proposed_approach.lower() in node.approach.lower():
                    return True, f"Already tried ({node.status}): {node.approach} → {node.result[:80]}"
            # It was tried but maybe succeeded or unknown
            return True, "This approach has already been attempted."
        return False, None

    def list_active(self) -> List[Dict]:
        """List all active in-session chains."""
        return [
            {
                "chain_id": c.chain_id,
                "query": c.query[:60],
                "steps": len(c.nodes),
                "status": c.status,
            }
            for c in self._active_chains.values()
        ]

    def get_chain(self, chain_id: str) -> Optional[LogicChain]:
        if chain_id in self._active_chains:
            return self._active_chains[chain_id]
        if self.chain_mem:
            return self.chain_mem.load(chain_id)
        return None

    def mark_resolved(self, query: str, success_approach: str = ""):
        """Mark a chain as resolved."""
        chain = self.find_or_create(query)
        chain.status = "resolved"
        if success_approach:
            chain.add_step(approach=success_approach, result="resolved", status="success")
        if self.chain_mem:
            self.chain_mem.save(chain)

    def abandon(self, query: str, reason: str = ""):
        chain = self.find_or_create(query)
        chain.status = "abandoned"
        if reason:
            chain.add_step(approach="abandoned", result=reason, status="failure")
        if self.chain_mem:
            self.chain_mem.save(chain)


# ── Singleton ───────────────────────────────────────────────────────

_navigator: Optional[ChainNavigator] = None


def get_chain_navigator(drift_memory=None) -> ChainNavigator:
    global _navigator
    if _navigator is None:
        _navigator = ChainNavigator(drift_memory)
    elif drift_memory is not None and _navigator.chain_mem is None:
        _navigator.chain_mem = ChainMemory(drift_memory)
    return _navigator
