"""Trinity scanner adapters."""

from .slither import build_slither_findings, is_slither_payload

__all__ = [
    "build_slither_findings",
    "is_slither_payload",
]
