"""Compatibility shim that maps ``drift.core`` to the real top-level ``core`` package.

This lets the historical import style keep working while the actual package
layout remains rooted at ``core/``.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

_CORE_DIR = Path(__file__).resolve().parents[2] / "core"
__path__ = [str(_CORE_DIR)]

_model_types = importlib.import_module("core.model_types")
sys.modules.setdefault("drift.core.types", _model_types)
