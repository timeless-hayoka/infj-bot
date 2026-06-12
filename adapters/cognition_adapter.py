"""
Phase 1 Adapter: Cognition (Compatibility Spine)
Routes drift cognition calls to the canonical DRIFT core.
"""

from drift.core import being, homeostasis, cognition, global_workspace


class CognitionAdapter:
    def __init__(self):
        self.being = being
        self.homeostasis = homeostasis
        self.cognition = cognition
        self.workspace = global_workspace

    def get_status(self):
        # Example of a unified status check
        return {
            "being_active": hasattr(self.being, "Being"),
            "homeostasis_active": hasattr(self.homeostasis, "HomeostaticRegulator"),
        }


adapter = CognitionAdapter()
