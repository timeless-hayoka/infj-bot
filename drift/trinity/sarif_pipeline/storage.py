"""SQLite and Chroma persistence for enriched SARIF findings."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from drift.trinity.sarif_models import EnrichedFinding


def init_sqlite(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS findings (
            dedup_key TEXT PRIMARY KEY,
            tool TEXT,
            rule_id TEXT,
            normalized_category TEXT,
            cwe TEXT,
            file_path TEXT,
            start_line INTEGER,
            message TEXT,
            cluster_id INTEGER,
            cluster_summary TEXT,
            properties TEXT,
            source_context TEXT,
            created_at TEXT
        )
        """
    )
    conn.commit()
    conn.close()


def persist_sqlite(db_path: Path, enriched: EnrichedFinding) -> None:
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        INSERT OR REPLACE INTO findings
        (dedup_key, tool, rule_id, normalized_category, cwe, file_path,
         start_line, message, cluster_id, cluster_summary, properties,
         source_context, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            enriched.dedup_key,
            enriched.finding.tool,
            enriched.finding.rule_id,
            enriched.normalized.category,
            enriched.normalized.cwe,
            enriched.finding.file_path,
            enriched.finding.start_line,
            enriched.finding.message,
            enriched.cluster_id,
            enriched.cluster_summary,
            json.dumps(enriched.finding.properties or {}, ensure_ascii=True),
            enriched.source_context,
            enriched.processed_at,
        ),
    )
    conn.commit()
    conn.close()


class ChromaFindingStore:
    def __init__(self, persist_directory: Path, collection_name: str = "security_findings") -> None:
        try:
            import chromadb
        except ImportError as exc:  # pragma: no cover - optional runtime
            raise RuntimeError("chromadb is required for ChromaFindingStore") from exc

        self._client = chromadb.PersistentClient(path=str(persist_directory))
        self._collection = self._client.get_or_create_collection(collection_name)

    def upsert(self, enriched: EnrichedFinding) -> None:
        document = (
            f"{enriched.normalized.category}: {enriched.finding.message}\n"
            f"{enriched.cluster_summary}\n"
            f"{enriched.source_context or ''}"
        ).strip()
        metadata: dict[str, Any] = {
            "tool": enriched.finding.tool,
            "category": enriched.normalized.category,
            "cwe": enriched.normalized.cwe or "",
            "file": enriched.finding.file_path,
            "line": enriched.finding.start_line,
            "cluster_id": str(enriched.cluster_id) if enriched.cluster_id is not None else "-1",
        }
        self._collection.upsert(
            ids=[enriched.dedup_key],
            documents=[document],
            metadatas=[metadata],
        )

    def query_similar(self, query: str, *, n_results: int = 5) -> dict[str, Any]:
        return self._collection.query(
            query_texts=[query],
            n_results=n_results,
            include=["documents", "metadatas", "distances"],
        )
