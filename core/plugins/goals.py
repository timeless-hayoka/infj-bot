"""Todo and goal tracker with SQLite backend."""

import sqlite3
import uuid
from datetime import datetime, timedelta
from typing import List, Optional
from pathlib import Path

from infj_bot.core.config import DATA_DIR

DB_PATH = DATA_DIR / "goals.db"


def _get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS goals (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                description TEXT,
                status TEXT DEFAULT 'active' CHECK(status IN ('active', 'done', 'archived')),
                priority INTEGER DEFAULT 1 CHECK(priority IN (0,1,2)),
                created_at TEXT NOT NULL,
                due_at TEXT,
                completed_at TEXT,
                tags TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS reminders (
                id TEXT PRIMARY KEY,
                message TEXT NOT NULL,
                remind_at TEXT NOT NULL,
                status TEXT DEFAULT 'pending' CHECK(status IN ('pending', 'sent', 'dismissed')),
                created_at TEXT NOT NULL
            )
        """)


class Goal:
    def __init__(self, row: sqlite3.Row):
        self.id = row["id"]
        self.title = row["title"]
        self.description = row["description"] or ""
        self.status = row["status"]
        self.priority = row["priority"]
        self.created_at = row["created_at"]
        self.due_at = row["due_at"]
        self.completed_at = row["completed_at"]
        self.tags = row["tags"] or ""

    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "status": self.status,
            "priority": self.priority,
            "created_at": self.created_at,
            "due_at": self.due_at,
            "completed_at": self.completed_at,
            "tags": self.tags,
        }


class GoalsDB:
    def __init__(self, db_path: Optional[str | Path] = None):
        from pathlib import Path
        if db_path is None:
            self.db_path = str(DB_PATH)
        else:
            self.db_path = str(db_path)
        # Ensure parent directory exists
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self.init_db()

    def _get_db(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def init_db(self) -> None:
        with self._get_db() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS goals (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    description TEXT,
                    status TEXT DEFAULT 'active' CHECK(status IN ('active', 'done', 'archived')),
                    priority INTEGER DEFAULT 1 CHECK(priority IN (0,1,2)),
                    created_at TEXT NOT NULL,
                    due_at TEXT,
                    completed_at TEXT,
                    tags TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS reminders (
                    id TEXT PRIMARY KEY,
                    message TEXT NOT NULL,
                    remind_at TEXT NOT NULL,
                    status TEXT DEFAULT 'pending' CHECK(status IN ('pending', 'sent', 'dismissed')),
                    created_at TEXT NOT NULL
                )
            """)

    # ------------------------------------------------------------------
    # Goals
    # ------------------------------------------------------------------
    def add_goal(
        self,
        title: str,
        description: str = "",
        priority: int = 1,
        due_at: Optional[str] = None,
        tags: str = "",
    ) -> str:
        gid = str(uuid.uuid4())[:8]
        with self._get_db() as conn:
            conn.execute(
                """INSERT INTO goals (id, title, description, priority, created_at, due_at, tags)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    gid,
                    title,
                    description,
                    priority,
                    datetime.now().isoformat(),
                    due_at,
                    tags,
                ),
            )
        return gid

    def list_goals(self, status: str = "active", limit: int = 20) -> List[Goal]:
        with self._get_db() as conn:
            rows = conn.execute(
                "SELECT * FROM goals WHERE status = ? ORDER BY priority DESC, created_at DESC LIMIT ?",
                (status, limit),
            ).fetchall()
        return [Goal(r) for r in rows]

    def complete_goal(self, gid: str) -> bool:
        with self._get_db() as conn:
            cur = conn.execute(
                "UPDATE goals SET status = 'done', completed_at = ? WHERE id = ? AND status = 'active'",
                (datetime.now().isoformat(), gid),
            )
            return cur.rowcount > 0

    def delete_goal(self, gid: str) -> bool:
        with self._get_db() as conn:
            cur = conn.execute("DELETE FROM goals WHERE id = ?", (gid,))
            return cur.rowcount > 0

    def get_goal(self, gid: str) -> Optional[Goal]:
        with self._get_db() as conn:
            row = conn.execute("SELECT * FROM goals WHERE id = ?", (gid,)).fetchone()
        return Goal(row) if row else None

    def active_summary(self) -> str:
        goals = self.list_goals(status="active", limit=10)
        if not goals:
            return "No active goals."
        lines = []
        for g in goals:
            flag = "!" if g.priority == 2 else ""
            due = f" (due {g.due_at})" if g.due_at else ""
            lines.append(f"{flag}[{g.id}] {g.title}{due}")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Reminders
    # ------------------------------------------------------------------
    def add_reminder(self, message: str, remind_at: str) -> str:
        rid = str(uuid.uuid4())[:8]
        with self._get_db() as conn:
            conn.execute(
                "INSERT INTO reminders (id, message, remind_at, created_at) VALUES (?, ?, ?, ?)",
                (rid, message, remind_at, datetime.now().isoformat()),
            )
        return rid

    def pending_reminders(self, within_minutes: int = 60) -> List[sqlite3.Row]:
        cutoff = (datetime.now() + timedelta(minutes=within_minutes)).isoformat()
        now = datetime.now().isoformat()
        with self._get_db() as conn:
            rows = conn.execute(
                "SELECT * FROM reminders WHERE status = 'pending' AND remind_at <= ? AND remind_at >= ? ORDER BY remind_at",
                (cutoff, now),
            ).fetchall()
        return rows

    def dismiss_reminder(self, rid: str) -> bool:
        with self._get_db() as conn:
            cur = conn.execute(
                "UPDATE reminders SET status = 'dismissed' WHERE id = ?", (rid,)
            )
            return cur.rowcount > 0

    def all_reminders(self, limit: int = 20) -> List[sqlite3.Row]:
        with self._get_db() as conn:
            return conn.execute(
                "SELECT * FROM reminders ORDER BY remind_at DESC LIMIT ?", (limit,)
            ).fetchall()


if __name__ == "__main__":
    db = GoalsDB()
    gid = db.add_goal("Build the DRIFT agent layer", priority=2, tags="dev")
    print(f"Added goal {gid}")
    print(db.active_summary())

