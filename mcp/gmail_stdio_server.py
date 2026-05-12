#!/usr/bin/env python3
"""Gmail MCP stdio proxy server.

Reads JSON-RPC from stdin, forwards to Google's Gmail MCP endpoint,
and writes responses to stdout. Works with Claude Desktop and any
MCP client that speaks stdio.

Usage (Claude Desktop config):
  {
    "mcpServers": {
      "gmail": {
        "command": "python",
        "args": ["/home/crexs/infj_bot/mcp/gmail_stdio_server.py"]
      }
    }
  }
"""

import json
import sys
from pathlib import Path

import httpx
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

CREDS_PATH = Path.home() / ".config" / "infj_bot" / "gmail_credentials.json"
GMAIL_MCP_URL = "https://gmailmcp.googleapis.com/mcp/v1"
SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.readonly",
]


def _get_access_token() -> str:
    if not CREDS_PATH.exists():
        raise RuntimeError(
            "Gmail credentials not found. Run: python scripts/gmail_mcp_auth.py --client-secret <path>"
        )
    creds = Credentials.from_authorized_user_file(str(CREDS_PATH), SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        # Persist refreshed token
        data = json.loads(CREDS_PATH.read_text())
        data["token"] = creds.token
        CREDS_PATH.write_text(json.dumps(data, indent=2))
    return creds.token


def _proxy(request_data: dict) -> dict:
    headers = {
        "content-type": "application/json",
        "accept": "application/json, text/event-stream",
    }
    method = request_data.get("method", "")
    # tools/list works without auth; everything else needs a Bearer token
    if method != "tools/list":
        headers["Authorization"] = f"Bearer {_get_access_token()}"

    try:
        resp = httpx.post(GMAIL_MCP_URL, headers=headers, json=request_data, timeout=30)
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPStatusError as exc:
        return {
            "jsonrpc": "2.0",
            "id": request_data.get("id"),
            "error": {
                "code": -32000,
                "message": f"HTTP {exc.response.status_code}: {exc.response.text}",
            },
        }
    except Exception as exc:
        return {
            "jsonrpc": "2.0",
            "id": request_data.get("id"),
            "error": {"code": -32000, "message": str(exc)},
        }


def main() -> int:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            continue
        resp = _proxy(req)
        print(json.dumps(resp), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
