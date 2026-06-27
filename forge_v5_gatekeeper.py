#!/usr/bin/env python3
"""Backward-compatible shim — canonical gatekeeper lives in AI-Forge-Protocol."""

from __future__ import annotations

import sys
from pathlib import Path

from core.forge_gate import _ensure_import_path

_ensure_import_path()

from forge_v5_gatekeeper import (  # noqa: E402
    ForgeValidator,
    generate_scope_hash,
    verify_scope_lock,
)

if __name__ == "__main__":
    import json

    if len(sys.argv) < 2:
        print("Usage: forge_v5_gatekeeper.py <target_directory>")
        sys.exit(1)

    target = sys.argv[1]
    print(f"🔥 INITIALIZING FORGE V5 GATEKEEPER ON: {target}")

    validator = ForgeValidator(target)
    report = validator.run_validation()

    print("\n📊 PARTIAL PASS INTELLIGENCE REPORT:")
    print(json.dumps(report, indent=2))

    if report["failed"] > 0:
        sys.exit(1)
    sys.exit(0)
