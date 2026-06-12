"""
Phase 1 Adapter: Memory (Compatibility Spine)
Provides a unified interface for drift, core, and hive memory.
"""

from drift import memory as infj_memory
from drift.core import memory as core_memory
from drift.hive_mind import shared_memory as hive_memory


class MemoryAdapter:
    def __init__(self):
        self.working = infj_memory
        self.semantic = core_memory
        self.shared = hive_memory

    def query_all(self, text: str):
        # Placeholder for unified search across layers
        return {
            "working": "Not implemented",
            "semantic": "Not implemented",
            "shared": "Not implemented",
        }


adapter = MemoryAdapter()
