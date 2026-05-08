"""Lightweight task scheduler for reminders and background jobs.

Stores tasks in SQLite and exposes a simple API for the proactive loop
and slash commands to use.
"""
import json
import sqlite3
import threading
import time
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional

from config import SCHEDULER_DB


@dataclass
class ScheduledTask:
    id: str
    title: str
    task_type: str  # reminder, shell, reflect, recon
    payload: str
    run_at: datetime
    recurring: str  # empty = one-shot, else "daily", "weekly", "hourly"
    created_at: datetime
    status: str  # pending, done, cancelled


class TaskScheduler:
    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = str(db_path or SCHEDULER_DB)
        self._lock = threading.Lock()
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    task_type TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    run_at TEXT NOT NULL,
                    recurring TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending'
                )
                """
            )
            conn.commit()

    def add_task(
        self,
        title: str,
        task_type: str,
        payload: str,
        run_at: datetime,
        recurring: str = "",
    ) -> str:
        tid = str(uuid.uuid4())[:8]
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO tasks (id, title, task_type, payload, run_at, recurring, created_at, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    tid,
                    title,
                    task_type,
                    payload,
                    run_at.isoformat(),
                    recurring,
                    datetime.now().isoformat(),
                    "pending",
                ),
            )
            conn.commit()
        return tid

    def list_pending(self, limit: int = 20) -> List[ScheduledTask]:
        now = datetime.now().isoformat()
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM tasks WHERE status = 'pending' ORDER BY run_at ASC LIMIT ?",
                (limit,),
            ).fetchall()
        return self._rows_to_tasks(rows)

    def list_due(self) -> List[ScheduledTask]:
        now = datetime.now().isoformat()
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM tasks WHERE status = 'pending' AND run_at <= ? ORDER BY run_at ASC",
                (now,),
            ).fetchall()
        return self._rows_to_tasks(rows)

    def get_task(self, tid: str) -> Optional[ScheduledTask]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM tasks WHERE id = ?", (tid,)).fetchone()
        return self._row_to_task(row) if row else None

    def cancel_task(self, tid: str) -> bool:
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.execute("UPDATE tasks SET status = 'cancelled' WHERE id = ? AND status = 'pending'", (tid,))
            conn.commit()
            return cur.rowcount > 0

    def mark_done(self, tid: str) -> bool:
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.execute("UPDATE tasks SET status = 'done' WHERE id = ?", (tid,))
            conn.commit()
            return cur.rowcount > 0

    def reschedule_recurring(self, task: ScheduledTask) -> Optional[str]:
        """If a task is recurring, create the next instance and return its id."""
        if not task.recurring:
            return None
        delta = {"hourly": timedelta(hours=1), "daily": timedelta(days=1), "weekly": timedelta(weeks=1)}.get(
            task.recurring
        )
        if delta is None:
            return None
        next_run = task.run_at + delta
        return self.add_task(
            title=task.title,
            task_type=task.task_type,
            payload=task.payload,
            run_at=next_run,
            recurring=task.recurring,
        )

    def clear_old(self, max_age_days: int = 30) -> int:
        cutoff = (datetime.now() - timedelta(days=max_age_days)).isoformat()
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.execute("DELETE FROM tasks WHERE status IN ('done', 'cancelled') AND run_at < ?", (cutoff,))
            conn.commit()
            return cur.rowcount

    def _rows_to_tasks(self, rows) -> List[ScheduledTask]:
        return [self._row_to_task(r) for r in rows]

    def _row_to_task(self, row) -> ScheduledTask:
        return ScheduledTask(
            id=row["id"],
            title=row["title"],
            task_type=row["task_type"],
            payload=row["payload"],
            run_at=datetime.fromisoformat(row["run_at"]),
            recurring=row["recurring"],
            created_at=datetime.fromisoformat(row["created_at"]),
            status=row["status"],
        )


def parse_duration(text: str) -> Optional[timedelta]:
    """Parse strings like '30m', '2h', '1d', '1w' into a timedelta."""
    text = text.strip().lower()
    if not text:
        return None
    # Handle pure numbers as minutes
    if text.isdigit():
        return timedelta(minutes=int(text))
    units = {
        "m": timedelta(minutes=1),
        "min": timedelta(minutes=1),
        "mins": timedelta(minutes=1),
        "minute": timedelta(minutes=1),
        "minutes": timedelta(minutes=1),
        "h": timedelta(hours=1),
        "hr": timedelta(hours=1),
        "hrs": timedelta(hours=1),
        "hour": timedelta(hours=1),
        "hours": timedelta(hours=1),
        "d": timedelta(days=1),
        "day": timedelta(days=1),
        "days": timedelta(days=1),
        "w": timedelta(weeks=1),
        "week": timedelta(weeks=1),
        "weeks": timedelta(weeks=1),
    }
    # Try to parse patterns like "30m", "2 hours", "1.5h"
    import re
    match = re.match(r"^(\d+(?:\.\d+)?)\s*([a-z]+)$", text)
    if match:
        num, unit = float(match.group(1)), match.group(2)
        delta = units.get(unit)
        if delta:
            # Scale the base unit by the number
            total_seconds = delta.total_seconds() * num
            return timedelta(seconds=total_seconds)
    return None
