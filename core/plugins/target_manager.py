"""Target scope manager for Bug Bounty programs.

Tracks in-scope and out-of-scope assets, syncs with Bugcrowd,
and enforces authorization boundaries for recon tools.
"""

import json
import sqlite3
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set


DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "bugbot_targets.db"


@dataclass
class Target:
    id: int = 0
    program_id: str = ""
    program_name: str = ""
    asset: str = ""  # domain, URL, IP, CIDR, wildcard
    asset_type: str = "domain"  # domain | url | ip | cidr | wildcard | api | mobile | other
    scope: str = "in"  # in | out | pending
    priority: str = "normal"  # normal | high
    notes: str = ""
    created_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))


class TargetManager:
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
                CREATE TABLE IF NOT EXISTS targets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    program_id TEXT,
                    program_name TEXT,
                    asset TEXT,
                    asset_type TEXT,
                    scope TEXT,
                    priority TEXT,
                    notes TEXT,
                    created_at TEXT
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_asset ON targets(asset)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_program ON targets(program_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_scope ON targets(scope)")
            conn.commit()

    def add(self, target: Target) -> int:
        with self._conn() as conn:
            cur = conn.execute(
                """
                INSERT INTO targets (program_id, program_name, asset, asset_type, scope, priority, notes, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    target.program_id,
                    target.program_name,
                    target.asset.lower().strip(),
                    target.asset_type,
                    target.scope,
                    target.priority,
                    target.notes,
                    target.created_at,
                ),
            )
            conn.commit()
        return cur.lastrowid

    def bulk_add(self, program_id: str, program_name: str, assets: List[Dict[str, Any]], scope: str = "in"):
        """Add multiple assets from a Bugcrowd scope sync."""
        for asset in assets:
            self.add(
                Target(
                    program_id=program_id,
                    program_name=program_name,
                    asset=asset.get("uri") or asset.get("name", ""),
                    asset_type=self._guess_type(asset.get("uri") or asset.get("name", "")),
                    scope=scope,
                    priority=asset.get("priority", "normal"),
                )
            )

    def is_authorized(self, asset: str) -> bool:
        """Check if an asset is explicitly in-scope."""
        hostname = asset.lower().strip().replace("https://", "").replace("http://", "").split("/")[0]
        with self._conn() as conn:
            # Exact match
            row = conn.execute(
                "SELECT scope FROM targets WHERE asset = ?", (hostname,)
            ).fetchone()
            if row:
                return row["scope"] == "in"
            # Wildcard match
            rows = conn.execute("SELECT asset, scope FROM targets WHERE asset LIKE '*.%'").fetchall()
            for r in rows:
                wildcard = r["asset"].replace("*.", "")
                if hostname.endswith(wildcard):
                    return r["scope"] == "in"
        return False

    def is_out_of_scope(self, asset: str) -> bool:
        hostname = asset.lower().strip().replace("https://", "").replace("http://", "").split("/")[0]
        with self._conn() as conn:
            row = conn.execute(
                "SELECT scope FROM targets WHERE asset = ? AND scope = 'out'", (hostname,)
            ).fetchone()
            if row:
                return True
            rows = conn.execute("SELECT asset FROM targets WHERE asset LIKE '*.%' AND scope = 'out'").fetchall()
            for r in rows:
                wildcard = r["asset"].replace("*.", "")
                if hostname.endswith(wildcard):
                    return True
        return False

    def list_targets(
        self,
        program_id: Optional[str] = None,
        scope: Optional[str] = None,
        asset_type: Optional[str] = None,
    ) -> List[Target]:
        query = "SELECT * FROM targets WHERE 1=1"
        params: List[Any] = []
        if program_id:
            query += " AND program_id = ?"
            params.append(program_id)
        if scope:
            query += " AND scope = ?"
            params.append(scope)
        if asset_type:
            query += " AND asset_type = ?"
            params.append(asset_type)
        query += " ORDER BY priority DESC, created_at DESC"
        with self._conn() as conn:
            rows = conn.execute(query, params).fetchall()
        return [Target(**{k: r[k] for k in r.keys()}) for r in rows]

    def get_authorized_targets(self) -> Set[str]:
        """Return all in-scope assets for quick set checks."""
        with self._conn() as conn:
            rows = conn.execute("SELECT asset FROM targets WHERE scope = 'in'").fetchall()
        return {r["asset"] for r in rows}

    def delete_program(self, program_id: str) -> int:
        with self._conn() as conn:
            cur = conn.execute("DELETE FROM targets WHERE program_id = ?", (program_id,))
            conn.commit()
        return cur.rowcount

    def count(self, program_id: Optional[str] = None, scope: Optional[str] = None) -> int:
        query = "SELECT COUNT(*) FROM targets WHERE 1=1"
        params: List[Any] = []
        if program_id:
            query += " AND program_id = ?"
            params.append(program_id)
        if scope:
            query += " AND scope = ?"
            params.append(scope)
        with self._conn() as conn:
            return conn.execute(query, params).fetchone()[0]

    def _guess_type(self, asset: str) -> str:
        a = asset.lower().strip()
        if "/" in a and (a.startswith("http://") or a.startswith("https://")):
            return "url"
        if "/" in a:
            return "cidr"
        if a.startswith("*."):
            return "wildcard"
        try:
            parts = a.split(".")
            if len(parts) == 4 and all(p.isdigit() and 0 <= int(p) <= 255 for p in parts):
                return "ip"
        except Exception:
            pass
        return "domain"
