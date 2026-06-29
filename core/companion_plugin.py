"""Companion / personality module gate — off by default for ANCHOR deployments."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class CompanionConfig:
    enabled: bool
    hive: bool
    shadow: bool
    homeostasis: bool


def companion_enabled() -> bool:
    return os.getenv("DRIFT_COMPANION_ENABLED", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def load_companion_config() -> CompanionConfig:
    enabled = companion_enabled()
    return CompanionConfig(
        enabled=enabled,
        hive=enabled and os.getenv("DRIFT_COMPANION_HIVE", "1") != "0",
        shadow=enabled and os.getenv("DRIFT_COMPANION_SHADOW", "1") != "0",
        homeostasis=enabled and os.getenv("DRIFT_COMPANION_HOMEOSTASIS", "1") != "0",
    )


def require_companion(feature: str) -> None:
    cfg = load_companion_config()
    if not cfg.enabled:
        raise RuntimeError(
            f"Companion feature '{feature}' is disabled. "
            "Set DRIFT_COMPANION_ENABLED=1 for Phase 5 personality modules."
        )
