"""
svalbard_vault.py — Core Identity Persistence Module
DRIFT Cognitive Architecture | Immutable Episodic Memory Ledger (V2.2)
"""

import json
import os
import sys
import hashlib
import hmac
from datetime import datetime
from dataclasses import dataclass, asdict

# ==========================================
# CONFIGURATION & ENVIRONMENT
# ==========================================
try:
    from drift.core.config import DATA_ROOT

    DEFAULT_VAULT_PATH = str(DATA_ROOT / "svalbard_ledger.jsonl")
except ImportError:
    DEFAULT_VAULT_PATH = os.path.expanduser("~/.drift_os/svalbard_ledger.jsonl")

VAULT_PATH = os.environ.get("DRIFT_VAULT_PATH", DEFAULT_VAULT_PATH)
SIG_PATH = f"{VAULT_PATH}.sig"
VAULT_SECRET = os.environ.get(
    "DRIFT_VAULT_SECRET", "default_dev_secret_do_not_use_in_prod"
)


def self_check_diagnostics():
    if VAULT_SECRET == "default_dev_secret_do_not_use_in_prod":
        print(
            "[⚠️ WARNING] DRIFT_VAULT_SECRET is using insecure default.", file=sys.stderr
        )
    vault_dir = os.path.dirname(VAULT_PATH)
    if vault_dir and not os.path.exists(vault_dir):
        os.makedirs(vault_dir, exist_ok=True)


@dataclass
class EmotionalAnchor:
    coherence: float
    tension: float
    resonance: float
    shadow_depth: float


@dataclass
class IdentityBlock:
    timestamp: str
    event_summary: str
    user_quote: str
    system_quote: str
    emotional_state: EmotionalAnchor
    prior_hash: str
    quarantined: bool = False
    version: str = "2.0"
    provenance: str = "user_explicit"
    source_reliability: float = 1.0
    block_hash: str = ""

    def calculate_hash(self) -> str:
        payload = {
            "version": self.version,
            "timestamp": self.timestamp,
            "event": self.event_summary,
            "user": self.user_quote,
            "sys": self.system_quote,
            "coherence": self.emotional_state.coherence,
            "tension": self.emotional_state.tension,
            "resonance": self.emotional_state.resonance,
            "shadow": self.emotional_state.shadow_depth,
            "quarantined": self.quarantined,
            "prior": self.prior_hash,
            "provenance": self.provenance,
            "source_reliability": self.source_reliability,
        }
        block_string = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(block_string.encode("utf-8")).hexdigest()


class SvalbardVault:
    def __init__(self):
        self_check_diagnostics()
        self.latest_hash = self._get_latest_hash_from_disk()

    def _get_latest_hash_from_disk(self) -> str:
        if not os.path.exists(VAULT_PATH) or os.path.getsize(VAULT_PATH) == 0:
            return "0" * 64
        try:
            with open(VAULT_PATH, "rb") as f:
                f.seek(0, os.SEEK_END)
                file_size = f.tell()
                if file_size == 0:
                    return "0" * 64

                chunk_size = 8192
                f.seek(max(0, file_size - chunk_size))
                chunk = f.read()
                lines = chunk.split(b"\n")
                last_line_bytes = (
                    lines[-1]
                    if lines[-1].strip()
                    else lines[-2]
                    if len(lines) > 1
                    else lines[-1]
                )

                if not last_line_bytes.strip():
                    f.seek(max(0, file_size - chunk_size * 2))
                    chunk = f.read()
                    lines = chunk.split(b"\n")
                    last_line_bytes = lines[-1] if lines[-1].strip() else lines[-2]

                last_line = last_line_bytes.decode("utf-8").strip()
                if not last_line:
                    return "0" * 64
                return json.loads(last_line).get("block_hash", "0" * 64)
        except Exception as e:
            print(f"[CRITICAL ERROR] Failed to read latest vault hash: {e}")
            return "0" * 64

    def _sign_root_hash(self, root_hash: str):
        signature = hmac.new(
            VAULT_SECRET.encode("utf-8"), root_hash.encode("utf-8"), hashlib.sha256
        ).hexdigest()
        with open(SIG_PATH, "w") as f:
            f.write(signature)
            f.flush()
            # TODO OPTIMIZATION: os.fsync can freeze the main thread.
            # In production/high-throughput systems, push writes to an async queue.
            os.fsync(f.fileno())

    def verify_identity_integrity(self, full_chain: bool = False) -> bool:
        if os.path.exists(SIG_PATH):
            with open(SIG_PATH, "r") as f:
                saved_sig = f.read().strip()
            expected_sig = hmac.new(
                VAULT_SECRET.encode("utf-8"),
                self.latest_hash.encode("utf-8"),
                hashlib.sha256,
            ).hexdigest()
            if saved_sig != expected_sig:
                print(
                    "[CRITICAL SECURITY FAILURE] Signature mismatch — ledger tampered!"
                )
                return False
        if not full_chain or not os.path.exists(VAULT_PATH):
            return True

        current_prior = "0" * 64
        with open(VAULT_PATH, "r") as f:
            for line_num, line in enumerate(f):
                line = line.strip()
                if not line:
                    continue
                block = json.loads(line)
                if block["prior_hash"] != current_prior:
                    return False

                anchor = EmotionalAnchor(**block["emotional_state"])
                test_block = IdentityBlock(
                    timestamp=block["timestamp"],
                    event_summary=block["event_summary"],
                    user_quote=block["user_quote"],
                    system_quote=block["system_quote"],
                    emotional_state=anchor,
                    prior_hash=block["prior_hash"],
                    quarantined=block.get("quarantined", False),
                    version=block.get("version", "2.0"),
                    provenance=block.get("provenance", "user_explicit"),
                    source_reliability=float(block.get("source_reliability", 1.0)),
                )
                if test_block.calculate_hash() != block["block_hash"]:
                    return False
                current_prior = block["block_hash"]
        return True

    def deposit_core_memory(
        self,
        event: str,
        user_q: str,
        sys_q: str,
        current_state: dict,
        quarantined: bool = False,
        provenance: str = "user_explicit",
        source_reliability: float = 1.0,
    ):
        anchor = EmotionalAnchor(
            coherence=current_state.get("coherence", 0.5),
            tension=current_state.get("tension", 0.0),
            resonance=current_state.get("resonance", 0.5),
            shadow_depth=current_state.get("shadow_depth", 0.0),
        )
        new_block = IdentityBlock(
            timestamp=datetime.utcnow().isoformat(),
            event_summary=event,
            user_quote=user_q,
            system_quote=sys_q,
            emotional_state=anchor,
            prior_hash=self.latest_hash,
            quarantined=quarantined,
            provenance=provenance,
            source_reliability=source_reliability,
        )
        new_block.block_hash = new_block.calculate_hash()

        from drift.core.jsonl_logger import HardenedJsonlLogger

        HardenedJsonlLogger(VAULT_PATH).append(asdict(new_block))

        self.latest_hash = new_block.block_hash
        self._sign_root_hash(self.latest_hash)
        prefix = "[QUARANTINED VAULT]" if quarantined else "[VAULT]"
        print(f"{prefix} Core memory sealed. Hash: {new_block.block_hash[:12]}...")
