"""RCCE-1 scoring must fail closed on unsupported inference provenance."""

import hashlib
from dataclasses import replace

import pytest

from drift.core.rcce_evidence import InferenceReceipt, validate_scored_trial


def receipt():
    text = "Verified answer from provider."
    return InferenceReceipt(
        task_id="held-out-1",
        condition="full",
        model_id="provider/model-version",
        provider_request_id="request-123",
        prompt_sha256="a" * 64,
        response_text=text,
        response_sha256=hashlib.sha256(text.encode()).hexdigest(),
        production_entrypoint="drift.core.brain.DriftBrain.think",
        provider_completed=True,
    )


def test_complete_receipt_is_structurally_admissible_not_proof_of_execution():
    validate_scored_trial(receipt())


@pytest.mark.parametrize(
    "changes",
    [
        {"response_text": ""},
        {"provider_request_id": ""},
        {"provider_completed": False},
        {"used_mock": True},
        {"used_fallback": True},
        {"used_cache": True},
        {"production_entrypoint": "mock.think"},
        {"prompt_sha256": "invalid"},
        {"response_sha256": "0" * 64},
    ],
)
def test_invalid_production_receipts_are_rejected(changes):
    with pytest.raises(ValueError, match="INVALID"):
        validate_scored_trial(replace(receipt(), **changes))
