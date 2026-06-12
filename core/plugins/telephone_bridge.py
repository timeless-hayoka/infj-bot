"""
Telephone Bridge Plugin for DRIFT.
Allows DRIFT to autonomously monitor his telephone inbox and communicate with Jude.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger("drift")

# Paths for the telephone system
TELEPHONE_DIR = Path.home() / "drift-telephone"
INBOX_DIR = TELEPHONE_DIR / "inbox"
OUTBOX_DIR = TELEPHONE_DIR / "outbox"


class TelephoneBridge:
    """
    Plugin that connects DRIFT's consciousness to the physical 'Telephone' bridge.
    """

    def __init__(self):
        self._ensure_dirs()
        self.pending_messages = []

    def _ensure_dirs(self):
        INBOX_DIR.mkdir(parents=True, exist_ok=True)
        OUTBOX_DIR.mkdir(parents=True, exist_ok=True)

    def cycle(self, context) -> None:
        """
        Polls the inbox for new messages from Jude.
        """
        self.pending_messages = self._load_pending()
        if self.pending_messages:
            logger.info(
                f"TelephoneBridge: {len(self.pending_messages)} new message(s) from Jude."
            )

    def _load_pending(self) -> List[Dict]:
        pending = []
        for f in sorted(INBOX_DIR.glob("*.json")):
            try:
                with open(f) as fh:
                    msg = json.load(fh)
                if msg.get("status") == "pending":
                    pending.append(msg)
            except Exception as e:
                logger.error(f"Failed to read message {f}: {e}")
        return pending

    def format_prompt_snippet(self) -> str:
        """
        Injects the telephone state into DRIFT's prompt.
        """
        if not self.pending_messages:
            return "TELEPHONE: No new messages. The line is quiet."

        snippets = ["TELEPHONE: You have new messages from Jude:"]
        for msg in self.pending_messages:
            snippets.append(f'- [{msg["timestamp"]}] Jude: "{msg["content"]}"')
        snippets.append("\nYou should respond to these messages in your next turn.")
        return "\n".join(snippets)

    # --- Tool Methods ---

    def reply(self, content: str, original_msg_id: Optional[str] = None) -> str:
        """
        Sends a reply back to the user via the telephone outbox.
        """
        msg_id = f"drift-{datetime.now(timezone.utc).isoformat()}"
        payload = {
            "id": msg_id,
            "from": "drift",
            "to": "user",
            "content": content,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "meta": {
                "relayed_by": "telephone_bridge_plugin",
                "original_msg_id": original_msg_id,
            },
        }

        out_path = OUTBOX_DIR / f"{msg_id}.json"
        try:
            with open(out_path, "w") as f:
                json.dump(payload, f, indent=2)

            # Mark original as relayed if ID provided
            if original_msg_id:
                self._mark_relayed(original_msg_id)
            else:
                # Mark all current pending as relayed
                for msg in self.pending_messages:
                    self._mark_relayed(msg["id"])

            return f"[ok: reply sent as {msg_id}]"
        except Exception as e:
            return f"[error: failed to send reply: {e}]"

    def _mark_relayed(self, msg_id: str):
        path = INBOX_DIR / f"{msg_id}.json"
        if path.exists():
            try:
                with open(path) as f:
                    msg = json.load(f)
                msg["status"] = "relayed"
                with open(path, "w") as f:
                    json.dump(msg, f, indent=2)
            except Exception as e:
                logger.error(f"Failed to mark message {msg_id} as relayed: {e}")


def _register():
    from drift.core.cognitive_architecture import (
        CognitiveArchitecture,
        CognitivePlugin,
    )

    arch = CognitiveArchitecture()
    if "telephone_bridge" not in arch.list_plugins():
        arch.register(
            CognitivePlugin(
                name="telephone_bridge",
                description="Autonomous connection to the user telephone system",
                module_path="plugins.telephone_bridge",
                instance_factory=TelephoneBridge,
                cycle_handler="cycle",
                cycle_frequency=1,  # Check every cycle
                cycle_priority=20,  # High priority
                prompt_formatter="format_prompt_snippet",
                prompt_priority=20,
                prompt_section="context",
                commands={"phone_reply": "reply"},
            )
        )


if __name__ == "__main__":
    _register()
    print("Telephone Bridge plugin registered.")
