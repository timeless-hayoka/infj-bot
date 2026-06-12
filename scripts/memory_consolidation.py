import sqlite3
import json
import logging
from datetime import datetime, timedelta

# Adjust imports to match your architecture
from infj_bot.core.config import DATA_DIR
from infj_bot.core.local_llm import OllamaBridge

logging.basicConfig(level=logging.INFO, format='[*] %(message)s')

BEING_DB = DATA_DIR / "being.db"
NEXUS_DB = DATA_DIR / "nexus.db"
ARCHIVE_DB = DATA_DIR / "archive.db"

class MemoryConsolidator:
    def __init__(self, cutoff_hours: int = 48):
        self.cutoff_hours = cutoff_hours
        self.cutoff_time = datetime.now() - timedelta(hours=cutoff_hours)
        self.llm = OllamaBridge() # Prefer local model to save API costs
        self._init_dbs()

    def _init_dbs(self):
        """Ensure schemas exist for Durable Knowledge and Cold Storage."""
        # Active Durable Knowledge
        with sqlite3.connect(NEXUS_DB) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS durable_knowledge (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    category TEXT NOT NULL,
                    content TEXT NOT NULL UNIQUE,
                    confidence REAL NOT NULL,
                    frequency_count INTEGER DEFAULT 1,
                    last_reinforced TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)
        # Cold Storage Archive
        with sqlite3.connect(ARCHIVE_DB) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS cold_storage_thoughts (
                    id INTEGER PRIMARY KEY,
                    original_id INTEGER,
                    timestamp TEXT,
                    content TEXT,
                    category TEXT,
                    archived_at TEXT
                )
            """)

    def fetch_stale_logs(self) -> list:
        """Pull raw thoughts older than the cutoff time."""
        with sqlite3.connect(BEING_DB) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM thoughts WHERE timestamp < ?", 
                (self.cutoff_time.isoformat(),)
            ).fetchall()
        return [dict(r) for r in rows]

    def classify_logs(self, raw_logs: list) -> list:
        """Feed logs to LLM to extract structured durable knowledge."""
        if not raw_logs:
            return []

        log_text = "\n".join([f"[{r['timestamp']}] {r['content']}" for r in raw_logs])
        
        prompt = f"""
You are a cognitive consolidation script. Analyze the following raw conversation logs and extract enduring, generalized knowledge.
DO NOT summarize the conversation. Extract specific traits, preferences, rules, or patterns.

Categories allowed: 'preference', 'behavioral_pattern', 'system_rule', 'emotional_signal'.

Raw Logs:
{log_text}

Output strictly as a JSON array of objects with the following keys:
- category: (one of the allowed categories)
- content: (the generalized fact/rule)
- confidence: (float between 0.0 and 1.0)

JSON Output:"""

        try:
            response = self.llm.generate(
                system="You are a data extraction tool. Output strictly valid JSON arrays.",
                prompt=prompt
            )
            cleaned = response.strip().replace("```json", "").replace("```", "")
            return json.loads(cleaned)
        except Exception as e:
            logging.error(f"LLM Classification failed: {e}")
            return []

    def commit_and_archive(self, raw_logs: list, new_knowledge: list):
        """Save schemas, move raw data to cold storage, and delete from active memory."""
        now = datetime.now().isoformat()
        
        # 1. Upsert Durable Knowledge
        with sqlite3.connect(NEXUS_DB) as conn:
            for item in new_knowledge:
                try:
                    conn.execute("""
                        INSERT INTO durable_knowledge (category, content, confidence, frequency_count, last_reinforced, created_at)
                        VALUES (?, ?, ?, 1, ?, ?)
                    """, (item['category'], item['content'], item['confidence'], now, now))
                    logging.info(f"[+] New Schema: [{item['category']}] {item['content']}")
                except sqlite3.IntegrityError:
                    conn.execute("""
                        UPDATE durable_knowledge 
                        SET frequency_count = frequency_count + 1,
                            confidence = MIN(1.0, confidence + 0.1),
                            last_reinforced = ?
                        WHERE content = ?
                    """, (now, item['content']))
                    logging.info(f"[*] Reinforced: {item['content']}")

        # 2. Move to Cold Storage
        with sqlite3.connect(ARCHIVE_DB) as conn:
            for log in raw_logs:
                conn.execute("""
                    INSERT INTO cold_storage_thoughts (original_id, timestamp, content, category, archived_at)
                    VALUES (?, ?, ?, ?, ?)
                """, (log['id'], log['timestamp'], log['content'], log['category'], now))

        # 3. Purge from Active Memory
        ids_to_delete = [log['id'] for log in raw_logs]
        with sqlite3.connect(BEING_DB) as conn:
            conn.execute(
                f"DELETE FROM thoughts WHERE id IN ({','.join('?' * len(ids_to_delete))})", 
                ids_to_delete
            )
        
        logging.info(f"[+] Consolidated and archived {len(raw_logs)} raw thoughts.")

    def run(self):
        logging.info("Starting Memory Consolidation...")
        logs = self.fetch_stale_logs()
        if not logs:
            logging.info("No stale logs found. Sleep cycle optimal.")
            return

        logging.info(f"Found {len(logs)} stale logs. Analyzing...")
        knowledge = self.classify_logs(logs)
        
        if knowledge:
            self.commit_and_archive(logs, knowledge)
        else:
            logging.warning("No durable knowledge extracted. Logs retained for next cycle.")

if __name__ == "__main__":
    # Initialize with cutoff_hours=0 for the initial test run to capture all recent baseline logs
    consolidator = MemoryConsolidator(cutoff_hours=0)
    consolidator.run()
