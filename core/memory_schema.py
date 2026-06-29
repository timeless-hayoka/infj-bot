"""Unified memory schema — single contract for episodic, semantic, and procedural layers."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Any
import hashlib
import json


class MemoryLayer(str, Enum):
    EPISODIC = "episodic"
    SEMANTIC = "semantic"
    PROCEDURAL = "procedural"


class MemoryModality(str, Enum):
    TEXT = "text"
    CODE = "code"
    STRUCTURED = "structured"
    MULTIMODAL = "multimodal"


@dataclass
class MemoryRecord:
    """Canonical memory unit stored by the unified spine."""

    unified_id: str
    layer: MemoryLayer
    modality: MemoryModality
    content: str
    salience: float = 0.5
    confidence: float = 0.5
    tags: list[str] = field(default_factory=list)
    source: str = "user"
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    last_accessed: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    access_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)
    content_hash: str = ""

    def __post_init__(self) -> None:
        self.salience = max(0.0, min(1.0, float(self.salience)))
        self.confidence = max(0.0, min(1.0, float(self.confidence)))
        if not self.content_hash:
            self.content_hash = self.compute_hash(self.content)

    @staticmethod
    def compute_hash(content: str) -> str:
        return hashlib.sha256(content.encode("utf-8", errors="ignore")).hexdigest()[:32]

    def touch(self) -> None:
        self.access_count += 1
        self.last_accessed = datetime.now(timezone.utc).isoformat()

    def reinforce(self, delta: float = 0.05) -> None:
        self.salience = max(0.0, min(1.0, self.salience + delta))
        self.touch()

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["layer"] = self.layer.value
        payload["modality"] = self.modality.value
        return payload

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MemoryRecord":
        layer = data.get("layer", MemoryLayer.EPISODIC.value)
        modality = data.get("modality", MemoryModality.TEXT.value)
        if isinstance(layer, MemoryLayer):
            layer_val = layer
        else:
            layer_val = MemoryLayer(str(layer))
        if isinstance(modality, MemoryModality):
            modality_val = modality
        else:
            modality_val = MemoryModality(str(modality))
        return cls(
            unified_id=str(data["unified_id"]),
            layer=layer_val,
            modality=modality_val,
            content=str(data.get("content", "")),
            salience=float(data.get("salience", 0.5)),
            confidence=float(data.get("confidence", 0.5)),
            tags=list(data.get("tags") or []),
            source=str(data.get("source", "user")),
            created_at=str(data.get("created_at", datetime.now(timezone.utc).isoformat())),
            last_accessed=str(data.get("last_accessed", datetime.now(timezone.utc).isoformat())),
            access_count=int(data.get("access_count", 0)),
            metadata=dict(data.get("metadata") or {}),
            content_hash=str(data.get("content_hash", "")),
        )


def merge_records(existing: MemoryRecord, incoming: MemoryRecord) -> MemoryRecord:
    """Conflict resolution: keep higher salience, merge tags, boost access."""
    winner = existing if existing.salience >= incoming.salience else incoming
    loser = incoming if winner is existing else existing
    merged_tags = sorted(set(winner.tags + loser.tags + incoming.tags))
    winner.tags = merged_tags
    winner.salience = max(existing.salience, incoming.salience)
    winner.confidence = max(existing.confidence, incoming.confidence)
    winner.access_count = existing.access_count + incoming.access_count
    winner.metadata = {**loser.metadata, **winner.metadata, "merged_from": loser.unified_id}
    winner.touch()
    return winner
