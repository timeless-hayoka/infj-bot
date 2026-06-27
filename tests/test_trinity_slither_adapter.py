from __future__ import annotations

from drift.trinity.adapters.slither import build_slither_findings, is_slither_payload


def test_slither_adapter_builds_trinity_findings(tmp_path):
    payload = {
        "results": {
            "detectors": [
                {
                    "check": "reentrancy",
                    "impact": "High",
                    "confidence": "High",
                    "description": "possible reentrancy path",
                    "elements": [
                        {
                            "source_mapping": {
                                "filename_relative": "contracts/Vulnerable.sol",
                                "lines": [42],
                            }
                        }
                    ],
                    "reproduction_command": "forge test --match-test test_reentrancy",
                }
            ]
        }
    }

    assert is_slither_payload(payload) is True

    findings = build_slither_findings(payload, tmp_path / "sample_slither.json")
    assert len(findings) == 1

    finding = findings[0]
    assert finding["kind"] == "slither"
    assert finding["id"] == "slither:0"
    assert finding["evidence_ref"] == "slither:0"
    assert finding["title"] == "reentrancy"
    assert "contracts/Vulnerable.sol" in finding["summary"]
    assert finding["reproduction_command"] == "forge test --match-test test_reentrancy"
    assert 0.0 <= finding["confidence"] <= 1.0
    assert 0.0 <= finding["severity"] <= 1.0
