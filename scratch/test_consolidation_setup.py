import sqlite3
import shutil
import sys
import os
from pathlib import Path
from datetime import datetime, timedelta

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Force load config
from infj_bot.core.config import DATA_DIR
from infj_bot.core.being import get_being

BEING_DB = DATA_DIR / "being.db"
NEXUS_DB = DATA_DIR / "nexus.db"
ARCHIVE_DB = DATA_DIR / "archive.db"

def backup_db():
    print("[*] Backing up being.db...")
    shutil.copyfile(BEING_DB, BEING_DB.with_suffix(".db.pre_test"))

def populate_mock_data():
    print("[*] Populating mock thoughts...")
    conn = sqlite3.connect(BEING_DB)
    # Ensure thoughts table exists
    conn.execute("""
        CREATE TABLE IF NOT EXISTS thoughts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            content TEXT NOT NULL,
            category TEXT DEFAULT 'general',
            shared INTEGER DEFAULT 0,
            energy_cost REAL DEFAULT 0.1,
            volitional INTEGER DEFAULT 0
        )
    """)
    
    # Insert some stale thoughts older than 48 hours
    stale_time = (datetime.now() - timedelta(hours=50)).isoformat()
    mock_thoughts = [
        (stale_time, "The user prefers a clean dark mode UI with Outfit typography and vibrant accents.", "preference"),
        (stale_time, "The user frequently runs terminal command queries after midnight.", "behavioral_pattern"),
        (stale_time, "System rule: Never use generic placeholders; always create assets dynamically.", "system_rule"),
        (stale_time, "The user expressed frustration when API responses took longer than 5 seconds.", "emotional_signal")
    ]
    conn.executemany("""
        INSERT INTO thoughts (timestamp, content, category)
        VALUES (?, ?, ?)
    """, mock_thoughts)
    conn.commit()
    conn.close()
    print("[+] Successfully inserted 4 mock thoughts into being.db.")

def get_being_telemetry():
    being = get_being()
    return being.state.to_dict() if hasattr(being, "state") else {}

if __name__ == "__main__":
    # Log state before
    backup_db()
    state_before = get_being_telemetry()
    print("[*] Drift state BEFORE test:", state_before)
    
    populate_mock_data()
    
    # Run the memory consolidator
    print("[*] Running MemoryConsolidator...")
    from scripts.memory_consolidation import MemoryConsolidator
    consolidator = MemoryConsolidator(cutoff_hours=0)
    consolidator.run()
    
    # Log state after
    state_after = get_being_telemetry()
    print("[*] Drift state AFTER test:", state_after)
    
    # Verification checks
    print("\n--- VERIFICATION CHECKS ---")
    if ARCHIVE_DB.exists():
        print("[+] SUCCESS: archive.db created.")
        conn = sqlite3.connect(ARCHIVE_DB)
        rows = conn.execute("SELECT COUNT(*) FROM cold_storage_thoughts").fetchone()
        print(f"    - Cold storage count: {rows[0]}")
        conn.close()
    else:
        print("[-] FAILED: archive.db was not created.")

    if NEXUS_DB.exists():
        print("[+] SUCCESS: nexus.db created.")
        conn = sqlite3.connect(NEXUS_DB)
        rows = conn.execute("SELECT * FROM durable_knowledge").fetchall()
        print(f"    - Durable knowledge entries count: {len(rows)}")
        for r in rows:
            print(f"      - Category: {r[1]}, Content: {r[2]}, Confidence: {r[3]}")
        conn.close()
    else:
        print("[-] FAILED: nexus.db was not created.")

    conn = sqlite3.connect(BEING_DB)
    remaining_thoughts = conn.execute("SELECT COUNT(*) FROM thoughts").fetchone()[0]
    conn.close()
    print(f"[+] Remaining thoughts in active memory: {remaining_thoughts}")
