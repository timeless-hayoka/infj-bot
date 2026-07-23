import os
import sqlite3
import secrets
import hashlib
import time
from pathlib import Path


def main():
    # Resolve configuration
    try:
        from drift.core.config import DATA_DIR

        data_dir = DATA_DIR if DATA_DIR else "."
    except ImportError:
        data_dir = os.getenv("INFJ_DATA_DIR", ".")

    db_path = Path(data_dir) / "gateway_keys.db"
    keys_file_path = Path(data_dir) / "keys.txt"

    # Generate cryptographically secure keys
    # Format: drift_live_<tier>_<random_24_char_hex>
    tiers = ["free", "pro", "admin"]
    new_keys = {}

    for tier in tiers:
        rand_token = secrets.token_hex(12)  # 24 hex characters
        new_keys[tier] = f"drift_live_{tier}_{rand_token}"

    # Open DB and rotate entries
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS keys (
            key_prefix TEXT NOT NULL,
            key_hash TEXT PRIMARY KEY,
            tier TEXT NOT NULL,
            created_at REAL NOT NULL,
            active INTEGER DEFAULT 1
        )
    """)

    cursor.execute("DELETE FROM keys")

    for tier, raw_key in new_keys.items():
        key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
        prefix = raw_key[:15]
        cursor.execute(
            "INSERT INTO keys (key_prefix, key_hash, tier, created_at, active) VALUES (?, ?, ?, ?, 1)",
            (prefix, key_hash, tier, time.time()),
        )
    conn.commit()
    conn.close()

    # Write raw keys to a secure file
    with open(keys_file_path, "w") as f:
        f.write("# ====================================================\n")
        f.write("# 🔑 DRIFT GATEWAY SECURE API KEYS\n")
        f.write("# DO NOT share this file or paste keys in public chat!\n")
        f.write("# ====================================================\n\n")
        for tier, raw_key in new_keys.items():
            f.write(f"{tier.upper()}_KEY={raw_key}\n")

    # Set permissions on the keys file to user-only (read/write)
    try:
        os.chmod(keys_file_path, 0o600)
    except Exception:
        pass

    print("====================================================")
    print("🔐 API KEYS SUCCESSFULLY ROTATED AND HARDENED")
    print(f"Database: {db_path}")
    print(f"Raw keys saved to: {keys_file_path}")
    print("====================================================")
    print("The old default demo keys have been completely revoked.")
    print("Please view the new keys directly from the keys.txt file.")


if __name__ == "__main__":
    main()
