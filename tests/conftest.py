"""Shared test fixtures for the INFJ bot test suite."""
import os
import sys
from pathlib import Path

import pytest

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture
def tmp_db_path(tmp_path: Path) -> Path:
    """Return a safe temporary DB path using pytest's tmp_path fixture.

    Cross-platform (Linux/Mac/Windows) and auto-cleans up after test.
    """
    return tmp_path / "test.db"
