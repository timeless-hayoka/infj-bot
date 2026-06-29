"""Trinity scanner adapters."""

from .sarif import build_sarif_findings, is_sarif_payload, parse_sarif_payload, process_sarif_findings
from .slither import build_slither_findings, is_slither_payload

__all__ = [
    "build_sarif_findings",
    "build_slither_findings",
    "is_sarif_payload",
    "is_slither_payload",
    "parse_sarif_payload",
    "process_sarif_findings",
]
