"""Enter the real DRIFT chat CLI with provider and memory observations."""

import importlib.metadata
import json
import os
import sys
import time
from pathlib import Path
from threading import Lock

from provider import install, write_json


def main():
    ledger, turn, output = sys.argv[1:]
    output = Path(output)
    install(Path(ledger), turn, output)
    from drift.core.unified_memory import MemoryManager

    remember = MemoryManager.remember_sync
    recall = MemoryManager.recall_sync
    lock = Lock()

    def trace(event, **fields):
        entry = {"event": event, "pid": os.getpid(), "time_ns": time.time_ns(), **fields}
        with lock, (output / "memory.jsonl").open("a", encoding="utf-8") as file:
            file.write(json.dumps(entry) + "\n")

    def observed_remember(self, event, metadata, vector=None):
        trace("write_started", event_type=event.type, content=event.content)
        try:
            memory_id = remember(self, event, metadata, vector)
        except Exception as exc:
            trace("write_failed", event_type=event.type, error=type(exc).__name__)
            raise
        trace("write_returned", event_type=event.type, id=memory_id)
        return memory_id

    def observed_recall(self, query, *args, **kwargs):
        results = recall(self, query, *args, **kwargs)
        trace("recall_returned", query=query, ids=[record.unified_id for record in results])
        return results

    MemoryManager.remember_sync = observed_remember
    MemoryManager.recall_sync = observed_recall

    import importlib

    chat = importlib.import_module("drift.interfaces.main")
    from drift.interfaces.cli import main as cli

    if chat.brain.sdk != "google.genai":
        raise RuntimeError(f"Unexpected application provider {chat.brain.sdk}")
    write_json(
        output / "runtime.json",
        {
            "pid": os.getpid(),
            "sdk": chat.brain.sdk,
            "model": chat.brain.primary_model_name,
            "embedding": type(chat.memory.unified_manager.embedding_function).__name__,
            "sqlite": chat.memory.unified_manager.db_path,
            "chroma": chat.memory.unified_manager.chroma_path,
            "history": str(chat.history.path),
            "versions": {
                name: importlib.metadata.version(name)
                for name in ("google-genai", "chromadb", "httpx")
            },
        },
    )
    sys.argv = ["drift", "chat"]
    try:
        return cli()
    finally:
        trace("cli_returned")


if __name__ == "__main__":
    sys.exit(main())
