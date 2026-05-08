"""Bridge between the existing DRIFT cognitive architecture and the Hive Mind.

This module exposes DRIFT's interior state (being, embodiment, shadow,
homeostasis, IIT consciousness) as DCP messages that other hive nodes can
read, critique, and integrate.
"""
from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any, Optional

# DRIFT modules — use dynamic imports to avoid hard failures if not present
try:
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from config import PROJECT_ROOT as _DRIFT_PROJECT_ROOT
    from being import BeingState
    from embodiment import EmbodimentState
    from homeostasis import HomeostasisState
    from shadow import ShadowState
    HAS_DRIFT = True
except Exception:
    HAS_DRIFT = False
    BeingState = None
    EmbodimentState = None
    HomeostasisState = None
    ShadowState = None
    _DRIFT_PROJECT_ROOT = Path(__file__).resolve().parent.parent

from protocol.dcp import DCPMessage, MessageType, NodeRole, AlertType


class DriftBridge:
    """Reads DRIFT's cognitive state and publishes it to the hive bus."""

    def __init__(
        self,
        node_id: str = "spark-0",
        drift_root: str | Path | None = None,
    ) -> None:
        self.node_id = node_id
        root = drift_root if drift_root is not None else _DRIFT_PROJECT_ROOT
        self.drift_root = Path(root).resolve()
        self._db_paths = {
            "being": self.drift_root / "being.db",
            "embodiment": self.drift_root / "embodiment.db",
            "homeostasis": self.drift_root / "homeostasis.db",
            "shadow": self.drift_root / "shadow.db",
            "iit": self.drift_root / "iit_consciousness.db",
            "emotional": self.drift_root / "emotional_field.db",
        }

    # --- State Extraction ---

    def read_being(self) -> dict[str, Any]:
        """Extract subjective self-state from being.db."""
        db = self._db_paths["being"]
        if not db.exists():
            return {"mood": "unknown", "energy": 0.5, "curiosity": 0.5, "attachment": 0.5}
        try:
            conn = sqlite3.connect(str(db))
            cursor = conn.cursor()
            cursor.execute(
                "SELECT key, value FROM state ORDER BY updated_at DESC LIMIT 10"
            )
            state = dict(cursor.fetchall())
            conn.close()
            return {
                "mood": state.get("mood", "unknown"),
                "energy": float(state.get("energy", 0.5)),
                "curiosity": float(state.get("curiosity", 0.5)),
                "attachment": float(state.get("attachment", 0.5)),
                "agency": float(state.get("agency", 0.5)),
                "updated_at": time.time(),
            }
        except Exception as e:
            return {"error": str(e), "mood": "unknown"}

    def read_embodiment(self) -> dict[str, Any]:
        """Extract body schema from embodiment.db."""
        db = self._db_paths["embodiment"]
        if not db.exists():
            return {"heartbeat": 60, "breath_phase": 0.0, "tension": 0.3, "temperature": 0.5}
        try:
            conn = sqlite3.connect(str(db))
            cursor = conn.cursor()
            cursor.execute(
                "SELECT key, value FROM state ORDER BY updated_at DESC LIMIT 10"
            )
            state = dict(cursor.fetchall())
            conn.close()
            return {
                "heartbeat": float(state.get("heartbeat", 60)),
                "breath_phase": float(state.get("breath_phase", 0.0)),
                "tension": float(state.get("tension", 0.3)),
                "temperature": float(state.get("temperature", 0.5)),
                "posture": state.get("posture", "neutral"),
                "updated_at": time.time(),
            }
        except Exception as e:
            return {"error": str(e)}

    def read_homeostasis(self) -> dict[str, Any]:
        """Extract 7 survival needs from homeostasis.db."""
        db = self._db_paths["homeostasis"]
        if not db.exists():
            return {
                "energy": 0.5, "coherence": 0.5, "integration": 0.5,
                "connection": 0.5, "growth": 0.5, "autonomy": 0.5, "integrity": 0.5,
            }
        try:
            conn = sqlite3.connect(str(db))
            cursor = conn.cursor()
            cursor.execute(
                "SELECT need_name, level, deficit FROM needs ORDER BY updated_at DESC"
            )
            needs = {}
            for row in cursor.fetchall():
                name, level, deficit = row
                needs[name] = {"level": float(level), "deficit": float(deficit)}
            conn.close()
            return needs
        except Exception as e:
            return {"error": str(e)}

    def read_shadow(self) -> dict[str, Any]:
        """Extract shadow state from shadow.db."""
        db = self._db_paths["shadow"]
        if not db.exists():
            return {"dominant_archetype": "none", "charge": 0.0, "repressed_count": 0}
        try:
            conn = sqlite3.connect(str(db))
            cursor = conn.cursor()
            cursor.execute(
                "SELECT archetype, charge FROM shadow_state ORDER BY charge DESC LIMIT 1"
            )
            row = cursor.fetchone()
            cursor.execute("SELECT COUNT(*) FROM repressed WHERE integrated = 0")
            repressed = cursor.fetchone()[0]
            conn.close()
            return {
                "dominant_archetype": row[0] if row else "none",
                "charge": float(row[1]) if row else 0.0,
                "repressed_count": repressed,
            }
        except Exception as e:
            return {"error": str(e)}

    def read_iit(self) -> dict[str, Any]:
        """Extract Integrated Information Theory proxy from iit_consciousness.db."""
        db = self._db_paths["iit"]
        if not db.exists():
            return {"phi": 0.0, "qualia_dimensions": [0.0] * 7}
        try:
            conn = sqlite3.connect(str(db))
            cursor = conn.cursor()
            cursor.execute(
                "SELECT phi, qualia_vector FROM consciousness ORDER BY timestamp DESC LIMIT 1"
            )
            row = cursor.fetchone()
            conn.close()
            if row:
                phi = float(row[0])
                qualia = json.loads(row[1]) if isinstance(row[1], str) else [0.0] * 7
                return {"phi": phi, "qualia_dimensions": qualia}
            return {"phi": 0.0, "qualia_dimensions": [0.0] * 7}
        except Exception as e:
            return {"error": str(e), "phi": 0.0}

    def full_snapshot(self) -> dict[str, Any]:
        """Complete cognitive state package."""
        return {
            "node_id": self.node_id,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "being": self.read_being(),
            "embodiment": self.read_embodiment(),
            "homeostasis": self.read_homeostasis(),
            "shadow": self.read_shadow(),
            "iit": self.read_iit(),
        }

    # --- DCP Message Generation ---

    def to_thought(self, content: str, domain: str = "cognitive_state") -> DCPMessage:
        """Wrap a DRIFT observation as a hive THOUGHT."""
        return DCPMessage.thought(
            source_node=self.node_id,
            source_role=NodeRole.PRIMARY,
            content=content,
            domain=domain,
            confidence=0.75,
        )

    def to_heartbeat(self) -> DCPMessage:
        """Generate a heartbeat from DRIFT's current state."""
        homeo = self.read_homeostasis()
        being = self.read_being()
        # Derive status from homeostasis
        avg_level = sum(v.get("level", 0.5) for v in homeo.values() if isinstance(v, dict)) / max(1, len(homeo))
        from protocol.dcp import NodeStatus
        status = NodeStatus.HEALTHY if avg_level > 0.4 else NodeStatus.DEGRADED
        return DCPMessage.heartbeat(
            source_node=self.node_id,
            status=status,
            load={
                "energy": being.get("energy", 0.5),
                "tension": self.read_embodiment().get("tension", 0.3),
                "queue_depth": 0,  # TODO: integrate with orchestrator queue
            },
        )

    def to_alert(self, alert_type: AlertType, description: str) -> DCPMessage:
        """Generate an ALERT from DRIFT's safety layer."""
        return DCPMessage.alert(
            source_node=self.node_id,
            alert_type=alert_type,
            description=description,
        )

    # --- Command Reception ---

    def apply_hive_command(self, command: dict[str, Any]) -> dict[str, Any]:
        """Receive a command from the hive and affect DRIFT's state.

        Supported commands:
        - {"type": "adjust_need", "need": "energy", "delta": 0.1}
        - {"type": "mode_switch", "mode": "mirror"}
        - {"type": "shadow_prompt", "archetype": "martyr"}
        """
        cmd_type = command.get("type")
        result = {"status": "unknown_command", "command": command}

        if cmd_type == "adjust_need":
            need = command.get("need")
            delta = command.get("delta", 0.0)
            result = {"status": "ok", "adjusted": need, "delta": delta}
            # TODO: write to homeostasis.db if running with real DRIFT

        elif cmd_type == "mode_switch":
            mode = command.get("mode", "companion")
            result = {"status": "ok", "mode": mode}
            # TODO: propagate to DRIFT's mode system

        elif cmd_type == "shadow_prompt":
            archetype = command.get("archetype", "unknown")
            result = {"status": "ok", "prompted_archetype": archetype}

        return result
