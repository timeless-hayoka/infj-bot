"""Resolve Forge V5 gatekeeper from AI-Forge-Protocol (canonical) with local fallback."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _afp_src() -> Path | None:
    env_root = os.environ.get("AFP_ROOT", "").strip()
    if env_root:
        src = Path(env_root) / "src"
        if src.is_dir():
            return src
    sibling = Path(__file__).resolve().parents[2] / "AI-Forge-Protocol" / "src"
    if sibling.is_dir():
        return sibling
    return None


def _ensure_import_path() -> None:
    src = _afp_src()
    if src and str(src) not in sys.path:
        sys.path.insert(0, str(src))


def gatekeeper_cli() -> Path:
    env_root = os.environ.get("AFP_ROOT", "").strip()
    if env_root:
        script = Path(env_root) / "scripts" / "forge_v5_gatekeeper.py"
        if script.is_file():
            return script
    sibling = Path(__file__).resolve().parents[2] / "AI-Forge-Protocol" / "scripts" / "forge_v5_gatekeeper.py"
    if sibling.is_file():
        return sibling
    return Path(__file__).resolve().parents[1] / "forge_v5_gatekeeper.py"


def load_forge_validator():
    _ensure_import_path()
    from forge_v5_gatekeeper import ForgeValidator

    return ForgeValidator
