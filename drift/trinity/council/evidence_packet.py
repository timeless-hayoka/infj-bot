"""Evidence packet helpers for Trinity council rounds.

The packet is the user-facing artifact Trinity should leave behind:
claim state, evidence refs, reasoning summary, rejected hypotheses, and
an exportable markdown report.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from .forge_council_schema import ClaimRecord, ClaimStatus, utc_stamp


@dataclass
class TrinityEvidencePacket:
    claim: Dict[str, Any]
    messages: List[Dict[str, Any]]
    board: Dict[str, Any]
    rejected_hypotheses: List[Dict[str, Any]] = field(default_factory=list)
    reasoning_summary: str = ""
    reproduction_command: Optional[str] = None
    created_at: str = field(default_factory=utc_stamp)

    def status(self) -> str:
        claim_status = str(self.claim.get("status", "")).lower()
        reproduction_status = str(self.claim.get("reproduction_status", "")).lower()
        evidence_refs = self.claim.get("evidence_refs", []) or []

        if claim_status == ClaimStatus.ACCEPTED.value and reproduction_status in {
            "confirmed",
            "reproduced",
        }:
            return "REPRODUCED_REAL"
        if claim_status == ClaimStatus.REJECTED.value:
            return "REJECTED"
        if evidence_refs or claim_status in {
            ClaimStatus.CHALLENGED.value,
            ClaimStatus.EVIDENCE_REQUESTED.value,
            ClaimStatus.REPRO_ATTEMPTED.value,
            ClaimStatus.ACCEPTED.value,
        }:
            return "NEEDS_HUMAN_REVIEW"
        return "INSUFFICIENT_EVIDENCE"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "claim": self.claim,
            "messages": self.messages,
            "board": self.board,
            "status": self.status(),
            "reasoning_summary": self.reasoning_summary,
            "rejected_hypotheses": self.rejected_hypotheses,
            "reproduction_command": self.reproduction_command,
            "created_at": self.created_at,
        }

    def render_markdown(self) -> str:
        lines = [
            "# Trinity Evidence Packet",
            "",
            f"- Claim ID: `{self.claim.get('id', '')}`",
            f"- Status: `{self.status()}`",
            f"- Claim confidence: `{self.claim.get('confidence', 0.0)}`",
            f"- Reproduction status: `{self.claim.get('reproduction_status', 'unattempted')}`",
            f"- Evidence refs: {', ' .join(self.claim.get('evidence_refs', []) or ['none'])}",
            "",
            "## Reasoning Summary",
            self.reasoning_summary or "No summary available.",
            "",
            "## Rejected Hypotheses",
        ]

        if self.rejected_hypotheses:
            for entry in self.rejected_hypotheses:
                lines.append(
                    f"- `{entry.get('message_type', 'unknown')}` from `{entry.get('sender', 'unknown')}`: "
                    f"{entry.get('reason', 'no reason provided')}"
                )
        else:
            lines.append("- None")

        lines.extend(
            [
                "",
                "## Board Summary",
                json.dumps(self.board, indent=2, ensure_ascii=True),
                "",
            ]
        )
        if self.reproduction_command:
            lines.extend(
                [
                    "## Reproduction Command",
                    f"`{self.reproduction_command}`",
                    "",
                ]
            )
        return "\n".join(lines)

    def write_bundle(self, root_dir: str | Path) -> Dict[str, str]:
        root = Path(root_dir)
        evidence_root = root / "evidence"
        tool_outputs = evidence_root / "tool_outputs"
        execution_logs = evidence_root / "execution_logs"
        reproduction = evidence_root / "reproduction"

        for path in (root, evidence_root, tool_outputs, execution_logs, reproduction):
            path.mkdir(parents=True, exist_ok=True)

        files = {
            "claim.json": root / "claim.json",
            "packet.json": root / "packet.json",
            "manifest.json": root / "manifest.json",
            "rejected_hypotheses.json": root / "rejected_hypotheses.json",
            "reasoning_summary.md": root / "reasoning_summary.md",
            "export_report.md": root / "export_report.md",
        }

        files["claim.json"].write_text(
            json.dumps(self.claim, indent=2, ensure_ascii=True) + "\n",
            encoding="utf-8",
        )
        files["rejected_hypotheses.json"].write_text(
            json.dumps(self.rejected_hypotheses, indent=2, ensure_ascii=True) + "\n",
            encoding="utf-8",
        )
        packet_payload = self.to_dict()
        packet_payload["bundle_dir"] = str(root)
        packet_payload["files"] = {name: str(path) for name, path in files.items()}
        files["packet.json"].write_text(
            json.dumps(packet_payload, indent=2, ensure_ascii=True) + "\n",
            encoding="utf-8",
        )
        files["manifest.json"].write_text(
            json.dumps(
                {
                    "bundle_dir": str(root),
                    "claim_id": self.claim.get("id", ""),
                    "status": self.status(),
                    "created_at": self.created_at,
                    "files": {name: str(path) for name, path in files.items()},
                },
                indent=2,
                ensure_ascii=True,
            )
            + "\n",
            encoding="utf-8",
        )
        files["reasoning_summary.md"].write_text(
            self.reasoning_summary.strip() + "\n",
            encoding="utf-8",
        )
        files["export_report.md"].write_text(self.render_markdown() + "\n", encoding="utf-8")

        return {key: str(path) for key, path in files.items()}


def build_reasoning_summary(
    claim: ClaimRecord,
    messages: Iterable[Dict[str, Any]],
    board: Dict[str, Any],
) -> str:
    message_list = list(messages)
    decision_notes = []
    for message in message_list:
        message_type = message.get("message_type", "unknown")
        sender = message.get("sender", "unknown")
        if message_type in {"challenge", "evidence_request", "reject"}:
            reason = message.get("content", {}).get("reason") or message.get("content", {}).get(
                "attack_mode"
            ) or message.get("content", {}).get("request") or "needs review"
            decision_notes.append(f"- {sender} issued `{message_type}`: {reason}")
        elif message_type == "accept":
            reason = message.get("content", {}).get("reason", "accepted after evidence review")
            decision_notes.append(f"- {sender} accepted the claim: {reason}")

    board_claims = board.get("claims", 0)
    board_messages = board.get("messages", 0)
    summary_lines = [
        f"Claim `{claim.id}` passed through `{len(message_list)}` council messages.",
        f"The board currently tracks `{board_claims}` claims and `{board_messages}` messages.",
        f"Claim status ended as `{claim.status.value}` with reproduction status `{claim.reproduction_status}`.",
    ]

    if decision_notes:
        summary_lines.append("Key decision notes:")
        summary_lines.extend(decision_notes)
    else:
        summary_lines.append("No challenge or acceptance notes were recorded in this round.")

    return "\n".join(summary_lines)
