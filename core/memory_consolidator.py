"""Memory consolidation, conflict resolution, and salience-based pruning."""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Iterable

from drift.core.config import PERSIST_DIRECTORY
from drift.core.unified_memory import Event, MemoryManager

from .memory_schema import MemoryLayer, MemoryModality, MemoryRecord, merge_records

logger = logging.getLogger("drift.memory_consolidator")

DEFAULT_PRUNE_SALIENCE = 0.12
DEFAULT_STALE_DAYS = 30


class MemoryConsolidator:
    """Single write path for unified memory with consolidate / forget cycles."""

    def __init__(
        self,
        manager: MemoryManager | None = None,
        *,
        registry_path: Path | None = None,
        prune_salience_floor: float = DEFAULT_PRUNE_SALIENCE,
        stale_days: int = DEFAULT_STALE_DAYS,
    ):
        self.manager = manager or MemoryManager()
        self.registry_path = registry_path or Path(PERSIST_DIRECTORY) / "memory_registry.jsonl"
        self.registry_path.parent.mkdir(parents=True, exist_ok=True)
        self.prune_salience_floor = prune_salience_floor
        self.stale_days = stale_days
        self._index: dict[str, MemoryRecord] = {}
        self._load_registry()

    def _load_registry(self) -> None:
        if not self.registry_path.exists():
            return
        for line in self.registry_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                record = MemoryRecord.from_dict(json.loads(line))
                self._index[record.unified_id] = record
            except (json.JSONDecodeError, KeyError, ValueError):
                continue

    def _append_registry(self, record: MemoryRecord) -> None:
        with self.registry_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record.to_dict()) + "\n")

    def _find_duplicate(self, record: MemoryRecord) -> MemoryRecord | None:
        for existing in self._index.values():
            if existing.content_hash == record.content_hash:
                return existing
        return None

    async def remember(
        self,
        content: str,
        *,
        layer: MemoryLayer = MemoryLayer.EPISODIC,
        modality: MemoryModality = MemoryModality.TEXT,
        salience: float = 0.5,
        tags: Iterable[str] | None = None,
        metadata: dict | None = None,
    ) -> str:
        record = MemoryRecord(
            unified_id="",
            layer=layer,
            modality=modality,
            content=content,
            salience=salience,
            tags=list(tags or []),
            metadata=dict(metadata or {}),
        )
        duplicate = self._find_duplicate(record)
        if duplicate:
            merged = merge_records(duplicate, record)
            self._index[merged.unified_id] = merged
            self._append_registry(merged)
            return merged.unified_id

        event = Event(type=layer.value, content=content)
        uid = await self.manager.remember(
            event,
            metadata={
                "salience": record.salience,
                "layer": layer.value,
                "modality": modality.value,
                "tags": ",".join(record.tags),
                **(metadata or {}),
            },
        )
        record.unified_id = uid
        self._index[uid] = record
        self._append_registry(record)
        return uid

    def list_records(self) -> list[MemoryRecord]:
        return list(self._index.values())

    async def consolidate(self) -> dict[str, int]:
        """Merge duplicates and archive stale low-salience episodic memories."""
        stats = {"merged": 0, "pruned": 0, "retained": 0}
        by_hash: dict[str, MemoryRecord] = {}
        for record in list(self._index.values()):
            if record.content_hash in by_hash:
                merged = merge_records(by_hash[record.content_hash], record)
                by_hash[record.content_hash] = merged
                self._index[merged.unified_id] = merged
                stats["merged"] += 1
            else:
                by_hash[record.content_hash] = record

        cutoff = datetime.now(timezone.utc) - timedelta(days=self.stale_days)
        for record in list(self._index.values()):
            if record.layer != MemoryLayer.EPISODIC:
                stats["retained"] += 1
                continue
            last = datetime.fromisoformat(record.last_accessed.replace("Z", "+00:00"))
            if last.tzinfo is None:
                last = last.replace(tzinfo=timezone.utc)
            if record.salience < self.prune_salience_floor and last < cutoff:
                await self._prune_record(record.unified_id)
                stats["pruned"] += 1
            else:
                stats["retained"] += 1
        logger.info("[memory_consolidator] consolidate: %s", stats)
        return stats

    async def _prune_record(self, unified_id: str) -> None:
        self._index.pop(unified_id, None)
        try:
            await self.manager.prune(threshold=self.prune_salience_floor)
        except Exception as exc:
            logger.warning("[memory_consolidator] prune fallback: %s", exc)

    async def run_scheduled_maintenance(self) -> dict[str, int]:
        return await self.consolidate()
