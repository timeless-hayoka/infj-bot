from datetime import datetime
from pathlib import Path

from drift.core.config import HISTORY_PATH
from drift.core.jsonl_logger import HardenedJsonlLogger


class ChatHistory:
    def __init__(self, path=None):
        self.path = Path(path or HISTORY_PATH)
        self._logger = HardenedJsonlLogger(self.path)

    def append(self, user_input, bot_output, mode, emotion, dissonance=None):
        record = {
            "timestamp": datetime.now().isoformat(),
            "mode": mode,
            "emotion": emotion,
            "dissonance": dissonance or {"score": 0.0},
            "user": user_input,
            "bot": bot_output,
        }
        self._logger.append(record)

    def recent(self, limit=20):
        return HardenedJsonlLogger.tail(self.path, n=limit)

    def count(self):
        if not self.path.exists():
            return 0
        return sum(1 for _ in HardenedJsonlLogger.read_any(self.path))

    def clear(self):
        if self.path.exists():
            self.path.write_text("", encoding="utf-8")

    def export_jsonl(self, target_path: str) -> int:
        target = Path(target_path)
        if not self.path.exists():
            target.write_text("", encoding="utf-8")
            return 0
        target.write_text(self.path.read_text(encoding="utf-8"), encoding="utf-8")
        return self.count()

    def import_jsonl(self, source_path: str) -> int:
        source = Path(source_path)
        if not source.exists():
            raise FileNotFoundError(f"History file not found: {source}")
        imported = 0
        for record in HardenedJsonlLogger.read_any(source):
            if "timestamp" in record and "user" in record and "bot" in record:
                self._logger.append(record)
                imported += 1
        return imported
