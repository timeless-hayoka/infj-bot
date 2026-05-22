"""
run_logger.py
DRIFT Experimental Run Logger
-------------------------------
Thread-safe SQLite logger for ablation runs and baseline sessions.
Uses WAL mode, batched commits, and _flush_unsafe() pattern to prevent deadlocks.

Usage:
    logger = RunLogger.get_instance()
    logger.log_run_start(run_id, config, git_hash)
    logger.log_event(run_id, turn, "state_snapshot", {...})
    logger.flush()
    logger.close()
"""

import sqlite3
import json
import time
import threading
import warnings


class RunLogger:
    _instance = None
    _instance_lock = threading.Lock()
    COMMIT_BATCH_SIZE = 10

    # ------------------------------------------------------------------ #
    #  Singleton                                                           #
    # ------------------------------------------------------------------ #

    @staticmethod
    def get_instance(db_path="experiment_log.db"):
        with RunLogger._instance_lock:
            if RunLogger._instance is None:
                RunLogger._instance = RunLogger(db_path)
        return RunLogger._instance

    # ------------------------------------------------------------------ #
    #  Init                                                                #
    # ------------------------------------------------------------------ #

    def __init__(self, db_path: str):
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self._write_lock = threading.Lock()
        self._pending_commits = 0
        self._create_tables()

    def _create_tables(self):
        with self._write_lock:
            # WAL mode: reduces write blocking, plays nicer with concurrent
            # reads from ChromaDB + other DRIFT db handles on the same CPU.
            self.conn.execute("PRAGMA journal_mode=WAL;")
            self.conn.execute("PRAGMA synchronous=NORMAL;")
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS runs (
                    run_id    TEXT PRIMARY KEY,
                    config    TEXT,
                    git_hash  TEXT,
                    start_time REAL
                )
            """)
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS events (
                    run_id     TEXT,
                    turn       INTEGER,
                    event_type TEXT,
                    payload    TEXT,
                    timestamp  REAL
                )
            """)
            self.conn.commit()

    # ------------------------------------------------------------------ #
    #  Internal flush (no lock — caller must hold _write_lock)             #
    # ------------------------------------------------------------------ #

    def _flush_unsafe(self):
        """
        INTERNAL USE ONLY. Call only when _write_lock is already held.
        Exists to prevent the deadlock:
            log_event() holds _write_lock → calls flush() → flush() tries
            to acquire _write_lock → deadlock.
        """
        try:
            self.conn.commit()
            self._pending_commits = 0
        except sqlite3.Error as e:
            # Do NOT reset _pending_commits — next flush will retry.
            warnings.warn(f"RunLogger flush failed: {e}. Data may be at risk.")

    # ------------------------------------------------------------------ #
    #  Public API                                                          #
    # ------------------------------------------------------------------ #

    def flush(self):
        """Public flush — acquires lock then calls unsafe version."""
        with self._write_lock:
            self._flush_unsafe()

    def log_run_start(self, run_id: str, config: dict, git_hash: str):
        with self._write_lock:
            self.conn.execute(
                "INSERT OR REPLACE INTO runs VALUES (?, ?, ?, ?)",
                (run_id, json.dumps(config), git_hash, time.time())
            )
            self.conn.commit()

    def log_event(self, run_id: str, turn: int, event_type: str, payload: dict):
        if not run_id:
            return
        with self._write_lock:
            self.conn.execute(
                "INSERT INTO events VALUES (?, ?, ?, ?, ?)",
                (run_id, turn, event_type, json.dumps(payload), time.time())
            )
            self._pending_commits += 1
            if self._pending_commits >= self.COMMIT_BATCH_SIZE:
                self._flush_unsafe()  # lock already held — no deadlock

    def log_run_end(self, run_id: str):
        """
        Log a clean run_end event and flush immediately.
        Intentional redundant flush: guarantees run_end is persisted
        regardless of current batch state.
        """
        self.log_event(run_id, -1, "run_end", {
            "run_id": run_id,
            "timestamp": time.time(),
            "clean": True
        })
        self.flush()  # intentional — ensures run_end is committed now

    def close(self):
        """Flush remaining events, close connection, allow re-init."""
        self.flush()
        self.conn.close()
        RunLogger._instance = None
