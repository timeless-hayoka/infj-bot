"""Coordination — the bot's interface with the Hive Mind.

This module allows the bot to participate in distributed cognition.
It can propose its own thoughts for review, critique the thoughts of others,
and integrate collective wisdom into its own internal state.

Phase 5: First-Class Hive Integration.
"""
import logging
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from infj_bot.core.cognitive_architecture import CognitivePlugin
from infj_bot.core.config import DATA_DIR, SQLITE_DIR

# Hive Mind imports
try:
    from infj_bot.hive_mind.consensus_engine import ConsensusEngine
    from infj_bot.hive_mind.protocol.dcp import DCPMessage, MessageType
    HAS_HIVE = True
except ImportError:
    HAS_HIVE = False

logger = logging.getLogger("drift")

SELF_MODIFY_DB = DATA_DIR / "self_modify.db"

class Coordination:
    """Hive Mind coordination and consensus."""

    def __init__(self):
        self.pending_reviews = []
        if HAS_HIVE:
            # Shared memory path is handled by ConfigAdapter inside SharedMemoryLayer
            self.consensus = ConsensusEngine()
        else:
            self.consensus = None

    def run_cycle(self, context):
        """Check for pending hive proposals and sync state."""
        if not HAS_HIVE or not self.consensus:
            return

        # Phase 5: Check for high-risk actions (Self-Modification)
        self._sync_self_modification_proposals()
        
        # Check for active consensus threads that need resolution
        active_threads = self.consensus.list_active_threads()
        for thread in active_threads:
            # Phase 5: Check for resolutions to apply
            if thread.status == "RESOLVED":
                self._apply_hive_resolution(thread)

    def _apply_hive_resolution(self, thread):
        """Sync Hive consensus result back to local state."""
        content = thread.proposal.content
        if content.get("action") == "self_modify" and "plan_id" in content:
            plan_id = content["plan_id"]
            resolution = thread.resolution.value if hasattr(thread.resolution, "value") else str(thread.resolution)
            
            new_status = "approved" if resolution == "APPROVED" else "rejected"
            
            try:
                with sqlite3.connect(SELF_MODIFY_DB) as conn:
                    conn.execute(
                        "UPDATE improvement_plans SET status = ? WHERE plan_id = ? AND status = 'proposed'",
                        (new_status, plan_id)
                    )
                logger.info(f"Hive consensus resolved self-mod {plan_id} as {new_status}")
            except Exception as e:
                logger.error(f"Failed to apply Hive resolution for {plan_id}: {e}")

    def _sync_self_modification_proposals(self):
        """Find proposed self-mods and push to Hive if not already there."""
        if not SELF_MODIFY_DB.exists():
            return
            
        try:
            with sqlite3.connect(SELF_MODIFY_DB) as conn:
                conn.row_factory = sqlite3.Row
                proposals = conn.execute(
                    "SELECT * FROM improvement_plans WHERE status = 'proposed'"
                ).fetchall()
                
            for prop in proposals:
                plan_id = prop["plan_id"]
                # Check if Hive already has a thread for this
                if not self._is_already_in_consensus(plan_id):
                    self._propose_to_hive(prop)
        except Exception as e:
            logger.error(f"Coordination failed to sync proposals: {e}")

    def _is_already_in_consensus(self, plan_id: str) -> bool:
        # Check shared memory or active threads for the plan_id
        for thread_id, thread in self.consensus.threads.items():
            if thread.proposal.content.get("plan_id") == plan_id:
                return True
        return False

    def _propose_to_hive(self, prop: sqlite3.Row):
        """Submit a self-modification plan to the Hive for Multi-Role Review."""
        msg = DCPMessage(
            type=MessageType.PROPOSAL,
            source="spark-0", # Canonical ID for the local core
            content={
                "action": "self_modify",
                "plan_id": prop["plan_id"],
                "area": prop["area"],
                "description": prop["description"],
                "steps": json.loads(prop["implementation_steps"]),
                "validation": json.loads(prop["validation_criteria"])
            }
        )
        thread = self.consensus.propose(msg)
        logger.info(f"Submitted self-mod {prop['plan_id']} to Hive consensus. Thread: {thread.thread_id}")

    def format_prompt(self) -> str:
        """Inject hive status and active consensus threads into prompt."""
        if not HAS_HIVE:
            return "The Hive Mind is currently disconnected."
            
        active_threads = self.consensus.list_active_threads()
        if not active_threads:
            return "The Hive is silent but watchful. No active consensus threads require my immediate attention."
            
        summary = f"The Hive is debating {len(active_threads)} active proposals:\n"
        for thread in active_threads:
            content = thread.proposal.content
            summary += f"- [{thread.status}] {content.get('action')}: {content.get('description')[:50]}...\n"
        return summary

def get_coordination():
    return Coordination()

def _register():
    from infj_bot.core.cognitive_architecture import CognitiveArchitecture, CognitivePlugin
    arch = CognitiveArchitecture()
    if "coordination" not in arch.list_plugins():
        arch.register(CognitivePlugin(
            name="coordination",
            description="Hive Mind coordination and consensus",
            module_path="coordination",
            instance_factory=get_coordination,
            cycle_handler="run_cycle",
            cycle_frequency=1,
            cycle_priority=60,
            prompt_formatter="format_prompt",
            prompt_priority=60,
            prompt_section="cognitive",
            is_core=True,
        ))

_register()

