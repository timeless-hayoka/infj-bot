"""Shared test utilities for the INFJ bot test suite."""
import os
import stat
from pathlib import Path

import pytest


def assert_db_cleaned_up(db_path: Path) -> None:
    """Assert that a SQLite DB and its WAL sidecars no longer exist."""
    for candidate in (
        db_path,
        Path(f"{db_path}-wal"),
        Path(f"{db_path}-shm"),
    ):
        assert not candidate.exists(), f"DB file not cleaned up: {candidate}"


def make_readonly_dir(path: Path) -> None:
    """Make a directory read-only for failure-mode tests."""
    path.mkdir(parents=True, exist_ok=True)
    path.chmod(stat.S_IRUSR | stat.S_IXUSR)


def restore_writable(path: Path) -> None:
    """Restore write permissions so pytest tmp_path can clean up."""
    if path.exists():
        path.chmod(stat.S_IRWXU)
