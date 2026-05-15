import json
from datetime import datetime
from pathlib import Path

from infj_bot.core.config import HISTORY_PATH


class ChatHistory:
    def __init__(self, path=None):
        self.path = Path(path) if path else Path(HISTORY_PATH)

    def append(self, user_input, bot_output, mode, emotion, dissonance=None):
        record = {
            "timestamp": datetime.now().isoformat(),
            "mode": mode,
            "emotion": emotion,
            "dissonance": dissonance or {"score": 0.0},
            "user": user_input,
            "bot": bot_output,
        }
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=True) + "\n")

    def recent(self, limit=20):
        if not self.path.exists():
            return []
        lines = self.path.read_text(encoding="utf-8").splitlines()
        records = []
        for line in lines[-limit:]:
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return records

    def count(self):
        if not self.path.exists():
            return 0
        return sum(1 for _line in self.path.open(encoding="utf-8"))

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
        with self.path.open("a", encoding="utf-8") as out:
            for line in source.read_text(encoding="utf-8").splitlines():
                try:
                    record = json.loads(line)
                    if "timestamp" in record and "user" in record and "bot" in record:
                        out.write(json.dumps(record, ensure_ascii=True) + "\n")
                        imported += 1
                except (json.JSONDecodeError, KeyError):
                    continue
        return imported
