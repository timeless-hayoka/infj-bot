#!/usr/bin/env python3
"""TrinityDatabase - persistent storage for Trinity findings and audits."""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from drift.config_adapter import LOGS_DIR


class TrinityDatabase:
    def __init__(self, db_path: str | Path | None = None):
        default_path = Path(os.getenv("TRINITY_DB_PATH", str(LOGS_DIR / "trinity.db")))
        self.db_path = Path(db_path) if db_path is not None else default_path
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        return sqlite3.connect(self.db_path)

    def _init_db(self) -> None:
        with self._connect() as conn:
            c = conn.cursor()
            c.execute(
                """
                CREATE TABLE IF NOT EXISTS findings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    case_id TEXT,
                    target_path TEXT,
                    swc TEXT,
                    tier TEXT,
                    confidence REAL,
                    historical_score REAL,
                    reproduced INTEGER,
                    evidence_sources TEXT,
                    explanation_trace TEXT,
                    created_at TEXT,
                    metadata TEXT
                )
                """
            )
            c.execute(
                """
                CREATE TABLE IF NOT EXISTS audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT,
                    event_type TEXT,
                    token_prefix TEXT,
                    tool TEXT,
                    details TEXT,
                    severity TEXT
                )
                """
            )
            c.execute(
                """
                CREATE TABLE IF NOT EXISTS benchmark_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT,
                    timestamp TEXT,
                    recall REAL,
                    precision REAL,
                    reproduction_success REAL,
                    total_cases INTEGER,
                    tier_a_count INTEGER,
                    metadata TEXT
                )
                """
            )
            conn.commit()

    def save_finding(self, finding: Dict[str, Any]) -> int:
        with self._connect() as conn:
            c = conn.cursor()
            c.execute(
                """
                INSERT INTO findings (
                    case_id, target_path, swc, tier, confidence, historical_score,
                    reproduced, evidence_sources, explanation_trace, created_at, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    finding.get("case_id"),
                    finding.get("target_path"),
                    finding.get("swc"),
                    finding.get("tier"),
                    finding.get("confidence"),
                    finding.get("historical_score"),
                    int(bool(finding.get("reproduced", False))),
                    json.dumps(finding.get("evidence_sources", [])),
                    finding.get("explanation_trace"),
                    datetime.utcnow().isoformat(),
                    json.dumps(finding.get("metadata", {})),
                ),
            )
            return int(c.lastrowid)

    def get_findings(
        self,
        tier: Optional[str] = None,
        reproduced: Optional[bool] = None,
    ) -> List[Dict[str, Any]]:
        query = "SELECT * FROM findings WHERE 1=1"
        params: List[Any] = []
        if tier:
            query += " AND tier = ?"
            params.append(tier)
        if reproduced is not None:
            query += " AND reproduced = ?"
            params.append(int(bool(reproduced)))

        with self._connect() as conn:
            c = conn.cursor()
            c.execute(query, params)
            rows = c.fetchall()

        findings: List[Dict[str, Any]] = []
        for row in rows:
            findings.append(
                {
                    "id": row[0],
                    "case_id": row[1],
                    "target_path": row[2],
                    "swc": row[3],
                    "tier": row[4],
                    "confidence": row[5],
                    "historical_score": row[6],
                    "reproduced": bool(row[7]),
                    "evidence_sources": json.loads(row[8]) if row[8] else [],
                    "explanation_trace": row[9],
                    "created_at": row[10],
                    "metadata": json.loads(row[11]) if row[11] else {},
                }
            )
        return findings

    def log_audit(self, event: Dict[str, Any]) -> None:
        with self._connect() as conn:
            c = conn.cursor()
            c.execute(
                """
                INSERT INTO audit_log (timestamp, event_type, token_prefix, tool, details, severity)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    event.get("timestamp", datetime.utcnow().isoformat()),
                    event.get("event_type", "unknown"),
                    event.get("token_prefix"),
                    event.get("tool"),
                    json.dumps(event.get("details", {})),
                    event.get("severity", "info"),
                ),
            )
            conn.commit()

    def save_benchmark_run(self, metrics: Dict[str, Any]) -> None:
        with self._connect() as conn:
            c = conn.cursor()
            c.execute(
                """
                INSERT INTO benchmark_runs (
                    run_id, timestamp, recall, precision, reproduction_success,
                    total_cases, tier_a_count, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    metrics.get("run_id", datetime.utcnow().isoformat()),
                    datetime.utcnow().isoformat(),
                    metrics.get("recall"),
                    metrics.get("precision"),
                    metrics.get("reproduction_success"),
                    metrics.get("total_cases"),
                    metrics.get("tier_a_count"),
                    json.dumps(metrics.get("metadata", {})),
                ),
            )
            conn.commit()

    def count_findings(self) -> int:
        with self._connect() as conn:
            c = conn.cursor()
            c.execute("SELECT COUNT(*) FROM findings")
            row = c.fetchone()
        return int(row[0] if row else 0)

    def get_latest_benchmark(self) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            c = conn.cursor()
            c.execute("SELECT * FROM benchmark_runs ORDER BY id DESC LIMIT 1")
            row = c.fetchone()
        if not row:
            return None
        return {
            "id": row[0],
            "run_id": row[1],
            "timestamp": row[2],
            "recall": row[3],
            "precision": row[4],
            "reproduction_success": row[5],
            "total_cases": row[6],
            "tier_a_count": row[7],
            "metadata": json.loads(row[8]) if row[8] else {},
        }

    def get_audit_entries(self, limit: int = 50) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            c = conn.cursor()
            c.execute(
                "SELECT * FROM audit_log ORDER BY id DESC LIMIT ?",
                (max(1, int(limit)),),
            )
            rows = c.fetchall()

        entries: List[Dict[str, Any]] = []
        for row in rows:
            entries.append(
                {
                    "id": row[0],
                    "timestamp": row[1],
                    "event_type": row[2],
                    "token_prefix": row[3],
                    "tool": row[4],
                    "details": json.loads(row[5]) if row[5] else {},
                    "severity": row[6],
                }
            )
        return entries

    def get_benchmark_runs(self, limit: int = 50) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            c = conn.cursor()
            c.execute(
                "SELECT * FROM benchmark_runs ORDER BY id DESC LIMIT ?",
                (max(1, int(limit)),),
            )
            rows = c.fetchall()

        runs: List[Dict[str, Any]] = []
        for row in rows:
            runs.append(
                {
                    "id": row[0],
                    "run_id": row[1],
                    "timestamp": row[2],
                    "recall": row[3],
                    "precision": row[4],
                    "reproduction_success": row[5],
                    "total_cases": row[6],
                    "tier_a_count": row[7],
                    "metadata": json.loads(row[8]) if row[8] else {},
                }
            )
        return runs


# Singleton for easy import.
db = TrinityDatabase()
