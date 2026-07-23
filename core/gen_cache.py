import sqlite3
import time
from pathlib import Path
from typing import Optional


class DiskGenCache:
    def __init__(self, path: Optional[Path] = None, max_entries: int = 1024):
        if path is None:
            path = Path.home() / ".drift" / "drift_gen_cache.sqlite3"
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.max_entries = max_entries
        self._conn = sqlite3.connect(str(self.path), timeout=10)
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS cache (k TEXT PRIMARY KEY, v TEXT, ts INTEGER)"
        )
        self._conn.commit()

    def get(self, key: str) -> Optional[str]:
        cur = self._conn.execute("SELECT v FROM cache WHERE k = ?", (key,))
        row = cur.fetchone()
        if not row:
            return None
        # update timestamp to reflect recent use
        try:
            self._conn.execute(
                "UPDATE cache SET ts = ? WHERE k = ?", (int(time.time()), key)
            )
            self._conn.commit()
        except Exception:
            pass
        return row[0]

    def set(self, key: str, value: str) -> None:
        ts = int(time.time())
        self._conn.execute(
            "INSERT OR REPLACE INTO cache (k, v, ts) VALUES (?, ?, ?)", (key, value, ts)
        )
        self._conn.commit()
        # enforce max entries
        cur = self._conn.execute("SELECT COUNT(1) FROM cache")
        count = cur.fetchone()[0]
        if count > self.max_entries:
            # delete oldest
            to_delete = count - self.max_entries
            self._conn.execute(
                "DELETE FROM cache WHERE k IN (SELECT k FROM cache ORDER BY ts ASC LIMIT ?)",
                (to_delete,),
            )
            self._conn.commit()

    def close(self):
        try:
            self._conn.close()
        except Exception:
            pass
