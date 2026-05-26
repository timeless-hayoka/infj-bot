"""Coordination — the bot's interface with the Hive Mind.

This module allows the bot to participate in distributed cognition.
It can propose its own thoughts for review, critique the thoughts of others,
and integrate collective wisdom into its own internal state.

Phase 5: First-Class Hive Integration.
"""

import logging
import sqlite3
from datetime import datetime

from infj_bot.core.cognitive_architecture import CognitivePlugin
from infj_bot.core.config import DATA_DIR

# Hive Mind imports
try:
    from infj_bot.hive_mind.consensus_engine import ConsensusEngine
    from infj_bot.hive_mind.protocol.dcp import DCPMessage, NodeRole

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
        # We check ALL threads because resolved ones need their results applied locally
        for thread in self.consensus._threads.values():
            if thread.state.name == "RESOLVED":
                self._apply_hive_resolution(thread)

    def _apply_hive_resolution(self, thread):
        """Sync Hive consensus result back to local state."""
        # Use resolution payload
        content = thread.resolution.payload
        if "proposal_id" in content:
            proposal_id = content["proposal_id"]

            # Resolution can be ADOPTED or TABLED/REJECTED
            new_status = (
                "approved" if thread.resolution.name == "ADOPTED" else "rejected"
            )

            try:
                with sqlite3.connect(SELF_MODIFY_DB) as conn:
                    conn.execute(
                        "UPDATE self_modify_proposals SET status = ?, reviewed_at = ? WHERE id = ? AND status = 'pending'",
                        (new_status, datetime.now().isoformat(), proposal_id),
                    )
                logger.info(
                    f"Hive consensus resolved proposal {proposal_id} as {new_status}"
                )
            except Exception as e:
                logger.error(f"Failed to apply Hive resolution for {proposal_id}: {e}")

    def _sync_self_modification_proposals(self):
        """Find pending self-modify proposals and push to Hive if not already there."""
        if not SELF_MODIFY_DB.exists():
            return

        try:
            with sqlite3.connect(SELF_MODIFY_DB) as conn:
                conn.row_factory = sqlite3.Row
                proposals = conn.execute(
                    "SELECT * FROM self_modify_proposals WHERE status = 'pending'"
                ).fetchall()

            for prop in proposals:
                proposal_id = prop["id"]
                # Check if Hive already has a thread for this
                if not self._is_already_in_consensus(proposal_id):
                    self._propose_to_hive(prop)
        except Exception as e:
            logger.error(f"Coordination failed to sync proposals: {e}")

    def _is_already_in_consensus(self, proposal_id: int) -> bool:
        # Check active threads for the proposal_id in metadata
        for thread in self.consensus._threads.values():
            if (
                thread.original_thought
                and thread.original_thought.payload.get("proposal_id") == proposal_id
            ):
                return True
        return False

    def _propose_to_hive(self, prop: sqlite3.Row):
        """Submit a self-modification proposal to the Hive for Multi-Role Review."""
        msg = DCPMessage.thought(
            source_node="spark-0",
            source_role=NodeRole.PRIMARY,
            content=f"Self-modification proposal: {prop['description']}",
            priority=0.8,
        )
        # Add metadata to payload
        msg.payload.update(
            {
                "action": "self_modify",
                "proposal_id": prop["id"],
                "area": prop["area"],
                "description": prop["description"],
                "observed_need": prop["observed_need"],
            }
        )
        thread = self.consensus.propose(msg)
        logger.info(
            f"Submitted proposal {prop['id']} to Hive consensus. Thread: {thread.thread_id}"
        )

    def format_prompt(self) -> str:
        """Inject hive status and active consensus threads into prompt."""
        if not HAS_HIVE:
            return "The Hive Mind is currently disconnected."

        active_threads = self.consensus.active_threads()
        if not active_threads:
            return "The Hive is silent but watchful. No active consensus threads require my immediate attention."

        summary = f"The Hive is debating {len(active_threads)} active proposals:\n"
        for thread in active_threads:
            payload = thread.original_thought.payload if thread.original_thought else {}
            summary += f"- [{thread.state.name}] {payload.get('action', 'thought')}: {payload.get('description', '')[:50]}...\n"
        return summary


def get_coordination():
    return Coordination()


def _register():
    from infj_bot.core.cognitive_architecture import CognitiveArchitecture

    arch = CognitiveArchitecture()
    if "coordination" not in arch.list_plugins():
        arch.register(
            CognitivePlugin(
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
            )
        )


_register()
