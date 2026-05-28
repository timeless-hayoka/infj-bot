"""SQLite-backed findings database for the Bug Bot.

Tracks vulnerabilities, evidence, reproduction steps, and submission status.
Integrates with DRIFT memory for long-term recall.
"""

import sqlite3
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


DEFAULT_DB_PATH = (
    Path(__file__).resolve().parent.parent.parent / "data" / "bugbot_findings.db"
)


@dataclass
class Finding:
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    program_id: str = ""
    program_name: str = ""
    title: str = ""
    vuln_type: str = ""  # e.g., "Broken Access Control > IDOR"
    severity: str = "P5"  # P1-P5 Bugcrowd scale
    cvss: float = 0.0
    status: str = "new"  # new | triaged | confirmed | false_positive | submitted | accepted | rejected
    asset: str = ""
    description: str = ""
    reproduction: str = ""
    impact: str = ""
    fix: str = ""
    evidence: str = ""  # JSON list of evidence dicts
    confidence: str = "low"  # low | medium | high | confirmed
    notes: str = ""
    bugcrowd_submission_id: str = ""
    created_at: str = field(
        default_factory=lambda: datetime.now().isoformat(timespec="seconds")
    )
    updated_at: str = field(
        default_factory=lambda: datetime.now().isoformat(timespec="seconds")
    )
    submitted_at: str = ""


class FindingsDB:
    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or DEFAULT_DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._conn() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS findings (
                    id TEXT PRIMARY KEY,
                    program_id TEXT,
                    program_name TEXT,
                    title TEXT,
                    vuln_type TEXT,
                    severity TEXT,
                    cvss REAL,
                    status TEXT,
                    asset TEXT,
                    description TEXT,
                    reproduction TEXT,
                    impact TEXT,
                    fix TEXT,
                    evidence TEXT,
                    confidence TEXT,
                    notes TEXT,
                    bugcrowd_submission_id TEXT,
                    created_at TEXT,
                    updated_at TEXT,
                    submitted_at TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS evidence (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    finding_id TEXT,
                    type TEXT,
                    path TEXT,
                    description TEXT,
                    created_at TEXT,
                    FOREIGN KEY (finding_id) REFERENCES findings(id)
                )
                """
            )
            conn.commit()

    def add(self, finding: Finding) -> str:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO findings VALUES (
                    :id, :program_id, :program_name, :title, :vuln_type, :severity,
                    :cvss, :status, :asset, :description, :reproduction, :impact,
                    :fix, :evidence, :confidence, :notes, :bugcrowd_submission_id,
                    :created_at, :updated_at, :submitted_at
                )
                """,
                asdict(finding),
            )
            conn.commit()
        return finding.id

    def get(self, finding_id: str) -> Optional[Finding]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM findings WHERE id = ?", (finding_id,)
            ).fetchone()
        return self._row_to_finding(row) if row else None

    def update(self, finding_id: str, **fields) -> bool:
        fields["updated_at"] = datetime.now().isoformat(timespec="seconds")
        sets = ", ".join(f"{k} = ?" for k in fields)
        values = list(fields.values()) + [finding_id]
        with self._conn() as conn:
            cur = conn.execute(f"UPDATE findings SET {sets} WHERE id = ?", values)
            conn.commit()
        return cur.rowcount > 0

    def delete(self, finding_id: str) -> bool:
        with self._conn() as conn:
            conn.execute("DELETE FROM evidence WHERE finding_id = ?", (finding_id,))
            cur = conn.execute("DELETE FROM findings WHERE id = ?", (finding_id,))
            conn.commit()
        return cur.rowcount > 0

    def list(
        self,
        program_id: Optional[str] = None,
        status: Optional[str] = None,
        severity: Optional[str] = None,
        limit: int = 50,
    ) -> List[Finding]:
        query = "SELECT * FROM findings WHERE 1=1"
        params: List[Any] = []
        if program_id:
            query += " AND program_id = ?"
            params.append(program_id)
        if status:
            query += " AND status = ?"
            params.append(status)
        if severity:
            query += " AND severity = ?"
            params.append(severity)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        with self._conn() as conn:
            rows = conn.execute(query, params).fetchall()
        return [self._row_to_finding(r) for r in rows]

    def add_evidence(
        self, finding_id: str, ev_type: str, path: str, description: str = ""
    ) -> int:
        with self._conn() as conn:
            cur = conn.execute(
                "INSERT INTO evidence (finding_id, type, path, description, created_at) VALUES (?, ?, ?, ?, ?)",
                (
                    finding_id,
                    ev_type,
                    path,
                    description,
                    datetime.now().isoformat(timespec="seconds"),
                ),
            )
            conn.commit()
        return cur.lastrowid

    def exists_by_asset_and_vuln_type(
        self, asset: str, vuln_type: str
    ) -> bool:
        """Check whether a finding with the same asset + vuln_type already exists."""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT 1 FROM findings WHERE asset = ? AND vuln_type = ? LIMIT 1",
                (asset, vuln_type),
            ).fetchone()
        return row is not None

    def get_evidence(self, finding_id: str) -> List[Dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM evidence WHERE finding_id = ? ORDER BY created_at",
                (finding_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def stats(self) -> Dict[str, Any]:
        with self._conn() as conn:
            total = conn.execute("SELECT COUNT(*) FROM findings").fetchone()[0]
            by_status = {
                row[0]: row[1]
                for row in conn.execute(
                    "SELECT status, COUNT(*) FROM findings GROUP BY status"
                ).fetchall()
            }
            by_severity = {
                row[0]: row[1]
                for row in conn.execute(
                    "SELECT severity, COUNT(*) FROM findings GROUP BY severity"
                ).fetchall()
            }
            programs = {
                row[0]: row[1]
                for row in conn.execute(
                    "SELECT program_name, COUNT(*) FROM findings GROUP BY program_name"
                ).fetchall()
            }
        return {
            "total": total,
            "by_status": by_status,
            "by_severity": by_severity,
            "by_program": programs,
        }

    def _row_to_finding(self, row: sqlite3.Row) -> Finding:
        return Finding(**{k: row[k] for k in row.keys()})
