"""
Hardened append-only JSONL logger.

Design constraints (from operator feedback):
  1. O_APPEND + trailing newline + flush — POSIX-atomic for small lines.
  2. threading.Lock for thread-safety inside one process; O_APPEND for
     cross-process safety on the same host.
  3. Log rotation so a droplet disk can't fill from an unbounded log.
  4. Disk-quota guard: refuse new lines when total log footprint
     exceeds a budget (default 200 MB).
  5. Per-line fault-tolerant read: a crash mid-line corrupts one line,
     not the whole file.

This replaces every ad-hoc ``open(path, "a")`` JSONL write in the repo.
"""

import gzip
import json
import os
import shutil
import threading
from pathlib import Path
from typing import Any, Iterator, Optional


class HardenedJsonlLogger:
    """
    Thread-safe, rotated, quota-guarded JSONL logger.

    Parameters
    ----------
    path : Path
        Target file. Parent dirs are created on first write.
    max_bytes : int
        Rotate when the current file exceeds this size (default 50 MB).
    max_backups : int
        Keep this many rotated backups (default 3).
    disk_quota_bytes : int | None
        Hard cap on the sum of *all* ``.jsonl*`` files in the same
        directory. Writes are silently dropped when exceeded.
        Default 200 MB.
    """

    def __init__(
        self,
        path: Path,
        max_bytes: int = 50_000_000,
        max_backups: int = 3,
        disk_quota_bytes: Optional[int] = 200_000_000,
    ):
        self.path = Path(path)
        self.max_bytes = max_bytes
        self.max_backups = max_backups
        self.disk_quota_bytes = disk_quota_bytes
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ #
    #  Write path                                                          #
    # ------------------------------------------------------------------ #

    def append(self, record: dict) -> bool:
        """Serialize *record* to one JSONL line and append atomically.

        Returns ``True`` on success, ``False`` if the write was skipped
        (quota exceeded, I/O error, etc.). Never raises.
        """
        try:
            line = json.dumps(record, default=str, ensure_ascii=False) + "\n"
            payload = line.encode("utf-8")
        except Exception:
            return False

        with self._lock:
            if not self._check_quota():
                return False
            self._rotate_if_needed()
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                # "ab" => O_APPEND on POSIX. For small lines (< PIPE_BUF,
                # typically 4 kB) the write is atomic even across processes.
                with open(self.path, "ab") as fh:
                    fh.write(payload)
                    fh.flush()
                    os.fsync(fh.fileno())
                return True
            except Exception:
                return False

    def _check_quota(self) -> bool:
        """Return False if total ``.jsonl*`` footprint exceeds quota."""
        if self.disk_quota_bytes is None:
            return True
        try:
            total = sum(
                f.stat().st_size
                for f in self.path.parent.iterdir()
                if f.name.startswith(self.path.stem) and "jsonl" in f.suffixes
            )
            return total < self.disk_quota_bytes
        except Exception:
            return True

    def _rotate_if_needed(self) -> None:
        if not self.path.exists():
            return
        try:
            if self.path.stat().st_size < self.max_bytes:
                return
        except Exception:
            return

        # Shift backups: .jsonl.2 -> .jsonl.3, .jsonl.1 -> .jsonl.2
        for i in range(self.max_backups - 1, 0, -1):
            src = self._backup_path(i)
            dst = self._backup_path(i + 1)
            if src.exists():
                shutil.move(str(src), str(dst))

        # Move current -> .jsonl.1
        shutil.move(str(self.path), str(self._backup_path(1)))

        # Compress the oldest backup if it exists
        oldest = self._backup_path(self.max_backups)
        if oldest.exists():
            try:
                gz_path = Path(str(oldest) + ".gz")
                with open(oldest, "rb") as f_in, gzip.open(gz_path, "wb") as f_out:
                    shutil.copyfileobj(f_in, f_out)
                oldest.unlink()
            except Exception:
                pass

    def _backup_path(self, n: int) -> Path:
        return self.path.with_suffix(f".jsonl.{n}")

    # ------------------------------------------------------------------ #
    #  Read path — fault-tolerant, line-by-line                            #
    # ------------------------------------------------------------------ #

    def read_lines(
        self,
        include_backups: bool = False,
        since: Optional[str] = None,
    ) -> Iterator[dict]:
        """Yield decoded JSON objects one at a time.

        Corrupt lines are skipped silently. If *since* is a timestamp
        string, only records whose ``timestamp`` field is >= *since*
        are yielded.
        """
        sources = [self.path]
        if include_backups:
            for i in range(1, self.max_backups + 1):
                bp = self._backup_path(i)
                if bp.exists():
                    sources.append(bp)

        for src in sources:
            if not src.exists():
                continue
            try:
                with open(src, "r", encoding="utf-8", errors="replace") as fh:
                    for line in fh:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            obj = json.loads(line)
                        except Exception:
                            continue
                        if since is not None:
                            ts = obj.get("timestamp") or obj.get("ts") or ""
                            if isinstance(ts, str) and ts < since:
                                continue
                        yield obj
            except Exception:
                continue

    def write_raw(self, line: str) -> bool:
        """Append a raw text line (for non-JSONL plain-text logs).

        The line is UTF-8 encoded and a trailing ``\n`` is added if absent.
        Returns ``True`` on success, ``False`` on failure.
        """
        if not line.endswith("\n"):
            line += "\n"
        payload = line.encode("utf-8")
        with self._lock:
            if not self._check_quota():
                return False
            self._rotate_if_needed()
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                with open(self.path, "ab") as fh:
                    fh.write(payload)
                    fh.flush()
                    os.fsync(fh.fileno())
                return True
            except Exception:
                return False

    @staticmethod
    def read_any(path: Path, limit: Optional[int] = None) -> Iterator[dict]:
        """Standalone helper: read *any* JSONL file with per-line fault tolerance.

        Does NOT rotate or check quotas — pure read-only safety.
        """
        if not path.exists():
            return
        count = 0
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            for raw in fh:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    yield json.loads(raw)
                except Exception:
                    continue
                count += 1
                if limit is not None and count >= limit:
                    return

    @staticmethod
    def tail(path: Path, n: int = 10) -> list[dict]:
        """Return the last *n* valid JSON lines from *path*."""
        if not path.exists():
            return []
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as fh:
                lines = fh.readlines()
        except Exception:
            return []
        results: list[dict] = []
        for line in reversed(lines):
            line = line.strip()
            if not line:
                continue
            try:
                results.append(json.loads(line))
            except Exception:
                continue
            if len(results) >= n:
                break
        return list(reversed(results))


# ---------------------------------------------------------------------- #
#  Convenience: module-level singletons for the existing logs              #
# ---------------------------------------------------------------------- #

def _logger_for(path: Path) -> HardenedJsonlLogger:
    return HardenedJsonlLogger(path)
