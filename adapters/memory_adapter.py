"""
Phase 1 Adapter: Memory (Compatibility Spine)
Provides a unified interface for infj_bot, core, and hive memory.
"""
from infj_bot import memory as infj_memory
from infj_bot.core import memory as core_memory
from infj_bot.hive_mind import shared_memory as hive_memory

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
            "shared": "Not implemented"
        }

adapter = MemoryAdapter()
