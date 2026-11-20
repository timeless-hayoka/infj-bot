"""Fail-closed evidence gate for RCCE-1 production inference trials.

This validator does not execute a model. A receipt is admissible only when
the instrumented production caller supplies provider provenance and a real
returned response; the experiment must independently verify provenance.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class InferenceReceipt:
    task_id: str
    condition: str
    model_id: str
    provider_request_id: str
    prompt_sha256: str
    response_text: str
    response_sha256: str
    production_entrypoint: str
    provider_completed: bool
    used_mock: bool = False
    used_fallback: bool = False
    used_cache: bool = False


def validate_scored_trial(receipt: InferenceReceipt) -> None:
    """Reject missing, simulated, fallback, cached or unattributable output."""
    import hashlib

    fields = (
        receipt.task_id, receipt.condition, receipt.model_id,
        receipt.provider_request_id, receipt.prompt_sha256,
        receipt.response_text, receipt.response_sha256,
        receipt.production_entrypoint,
    )
    if not all(isinstance(v, str) and v.strip() for v in fields):
        raise ValueError("INVALID: missing production inference evidence")
    if receipt.production_entrypoint != "drift.core.brain.DriftBrain.think":
        raise ValueError("INVALID: not the approved production entrypoint")
    if not receipt.provider_completed or receipt.used_mock or receipt.used_fallback or receipt.used_cache:
        raise ValueError("INVALID: production provider response not verified")
    if len(receipt.prompt_sha256) != 64 or any(c not in "0123456789abcdef" for c in receipt.prompt_sha256):
        raise ValueError("INVALID: malformed prompt digest")
    if hashlib.sha256(receipt.response_text.encode("utf-8")).hexdigest() != receipt.response_sha256:
        raise ValueError("INVALID: response capture does not match recorded digest")
