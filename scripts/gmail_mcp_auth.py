#!/usr/bin/env python3
"""One-time Gmail OAuth setup for the Gmail MCP proxy.

Usage:
  python scripts/gmail_mcp_auth.py --client-secret ~/Downloads/client_secret.json

Steps to get client_secret.json:
  1. Go to https://console.cloud.google.com/apis/credentials
  2. Create OAuth 2.0 Client ID → Desktop app
  3. Download JSON → rename to client_secret.json
  4. Run this script and sign in via browser
"""

import argparse
import json
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
]

CREDS_DIR = Path.home() / ".config" / "drift"
CREDS_PATH = CREDS_DIR / "gmail_credentials.json"


def main() -> int:
    p = argparse.ArgumentParser(description="Authenticate Gmail for MCP proxy")
    p.add_argument(
        "--client-secret", required=True, help="Path to Google OAuth client_secret.json"
    )
    args = p.parse_args()

    CREDS_DIR.mkdir(parents=True, exist_ok=True)

    # Run OAuth flow
    flow = InstalledAppFlow.from_client_secrets_file(args.client_secret, SCOPES)
    creds = flow.run_local_server(port=0)

    # Save credentials
    creds_data = {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": creds.scopes,
    }
    CREDS_PATH.write_text(json.dumps(creds_data, indent=2))
    print(f"✅ Gmail credentials saved to: {CREDS_PATH}")
    print("   You can now run the Gmail MCP server.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
