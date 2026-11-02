from __future__ import annotations

import atexit
import os
import sys
import tempfile
from pathlib import Path

import pytest

# Choose the canonical state root before importing any application modules.
# Tests must never use a developer's persistent companion state.
_test_state = tempfile.TemporaryDirectory(prefix="drift-pytest-")
os.environ["DRIFT_OS_ROOT"] = _test_state.name
atexit.register(_test_state.cleanup)
os.environ.setdefault("DRIFT_USE_LOCAL_EMBEDDINGS", "true")


def pytest_collection_modifyitems(items):
    if os.environ.get("DRIFT_RUN_ENV_TESTS") == "1":
        return
    for item in items:
        if item.get_closest_marker("env"):
            item.add_marker(pytest.mark.skip(reason="requires DRIFT_RUN_ENV_TESTS=1"))


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Prefer project venv site-packages over system dist-packages (avoids attrs/jsonschema conflicts).
_venv_site = (
    ROOT
    / ".venv"
    / "lib"
    / f"python{sys.version_info.major}.{sys.version_info.minor}"
    / "site-packages"
)
if _venv_site.is_dir():
    site_str = str(_venv_site)
    if site_str not in sys.path:
        sys.path.insert(0, site_str)

# Register drift.evals / drift.metrics when running pytest without reinstall quirks.
import types

for _sub, _folder in (("evals", "evals"), ("metrics", "metrics")):
    _full = f"drift.{_sub}"
    _path = ROOT / _folder
    if _path.is_dir() and _full not in sys.modules:
        _mod = types.ModuleType(_full)
        _mod.__path__ = [str(_path)]  # type: ignore[attr-defined]
        sys.modules[_full] = _mod
