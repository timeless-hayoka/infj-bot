#!/usr/bin/env python3
"""Gmail MCP HTTP bridge — exposes Google's Gmail MCP as a local HTTP API.

Use this when your AI tools don't support MCP stdio but can POST JSON.

Usage:
  python mcp/gmail_http_bridge.py --port 8766

Then curl it:
  curl http://127.0.0.1:8766/mcp \
    -H 'content-type: application/json' \
    -d '{"method":"tools/list","jsonrpc":"2.0","id":1}'
"""

import argparse
import json
from pathlib import Path

import httpx
import uvicorn
from fastapi import FastAPI, Request
from google.auth.transport.requests import Request as GoogleRequest
from google.oauth2.credentials import Credentials

CREDS_PATH = Path.home() / ".config" / "drift" / "gmail_credentials.json"
GMAIL_MCP_URL = "https://gmailmcp.googleapis.com/mcp/v1"
SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.readonly",
]

app = FastAPI(title="Gmail MCP Bridge")


def _get_access_token() -> str:
    if not CREDS_PATH.exists():
        raise RuntimeError("Run scripts/gmail_mcp_auth.py first")
    creds = Credentials.from_authorized_user_file(str(CREDS_PATH), SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(GoogleRequest())
        data = json.loads(CREDS_PATH.read_text())
        data["token"] = creds.token
        CREDS_PATH.write_text(json.dumps(data, indent=2))
    return creds.token


@app.post("/mcp")
async def mcp_endpoint(req: Request):
    body = await req.json()
    headers = {
        "content-type": "application/json",
        "accept": "application/json, text/event-stream",
    }
    if body.get("method") != "tools/list":
        headers["Authorization"] = f"Bearer {_get_access_token()}"

    r = httpx.post(GMAIL_MCP_URL, headers=headers, json=body, timeout=30)
    r.raise_for_status()
    return r.json()


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8766)
    args = p.parse_args()
    print(f"🚀 Gmail MCP bridge running at http://{args.host}:{args.port}/mcp")
    uvicorn.run(app, host=args.host, port=args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
