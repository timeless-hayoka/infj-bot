"""
core/unified_audit.py — The singular source of truth for PHI cognitive history.

Aggregates tool calls, architecture changes, security events, and
high-order deliberations into a single hardened JSONL stream.
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from drift.config_adapter import ConfigAdapter
from drift.core.jsonl_logger import HardenedJsonlLogger

logger = logging.getLogger("drift.audit")

# Canonical Path: ~/.drift_os/logs/unified_audit.jsonl
UNIFIED_AUDIT_PATH = Path(ConfigAdapter.get_log_path("unified_audit"))

# Standard Singleton
_AUDIT_LOGGER: Optional[HardenedJsonlLogger] = None

def get_audit_logger() -> HardenedJsonlLogger:
    global _AUDIT_LOGGER
    if _AUDIT_LOGGER is None:
        _AUDIT_LOGGER = HardenedJsonlLogger(UNIFIED_AUDIT_PATH)
    return _AUDIT_LOGGER

def audit_log(event_type: str, source: str, payload: Dict[str, Any]):
    """Append an event to the unified audit stream."""
    record = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "event": event_type,
        "source": source,
        "payload": payload
    }
    get_audit_logger().append(record)
    logger.debug("[audit] %s: %s", event_type, source)

def wire_orchestrator_audit(orchestrator):
    """Wire the orchestrator to log all internal events to the unified audit."""
    
    def audit_handler(event):
        # Flatten for the audit log
        audit_log(
            event_type=f"cognitive_{event['type']}",
            source=event.get("source") or "orchestrator",
            payload=event.get("payload", {})
        )

    # Subscribe to all core event types
    event_types = [
        "emotion_resonated",
        "insight_formed",
        "prediction_made",
        "action_proposed",
        "conflict_detected",
        "state_transition",
        "deliberation_started",
        "deliberation_resolved"
    ]
    
    for et in event_types:
        orchestrator.bus.subscribe(et, audit_handler)
    
    logger.info("[audit] Orchestrator events wired to unified audit.")
