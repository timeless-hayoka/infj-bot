#!/usr/bin/env python3
"""Gmail Hybrid MCP Server — proxies Google's official Gmail MCP + adds send_email.

Supports stdio (Claude Desktop) and HTTP (curl / general use).

Usage:
  # stdio (for Claude Desktop)
  python mcp/gmail_hybrid_server.py --transport stdio

  # HTTP bridge
  python mcp/gmail_hybrid_server.py --transport http --port 8767

Claude Desktop config:
  {
    "mcpServers": {
      "gmail": {
        "command": "python",
        "args": ["/home/crexs/infj_bot/mcp/gmail_hybrid_server.py", "--transport", "stdio"]
      }
    }
  }
"""
import argparse
import base64
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

import httpx
import uvicorn
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from fastapi import FastAPI, Request
from google.auth.transport.requests import Request as GoogleRequest
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

CREDS_PATH = Path.home() / ".config" / "infj_bot" / "gmail_credentials.json"
GMAIL_MCP_URL = "https://gmailmcp.googleapis.com/mcp/v1"
SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
]

# Cached Google tools list
_google_tools: List[Dict[str, Any]] = []


def _get_credentials() -> Credentials:
    if not CREDS_PATH.exists():
        raise RuntimeError(
            "Gmail credentials not found. Run: python scripts/gmail_mcp_auth.py --client-secret <path>"
        )
    creds = Credentials.from_authorized_user_file(str(CREDS_PATH), SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(GoogleRequest())
        data = json.loads(CREDS_PATH.read_text())
        data["token"] = creds.token
        CREDS_PATH.write_text(json.dumps(data, indent=2))
    return creds


def _get_access_token() -> str:
    return _get_credentials().token


def _fetch_google_tools() -> List[Dict[str, Any]]:
    global _google_tools
    if _google_tools:
        return _google_tools
    r = httpx.post(
        GMAIL_MCP_URL,
        headers={"content-type": "application/json"},
        json={"method": "tools/list", "jsonrpc": "2.0", "id": 1},
        timeout=15,
    )
    r.raise_for_status()
    _google_tools = r.json().get("result", {}).get("tools", [])
    return _google_tools


def _send_email(arguments: Dict[str, Any]) -> Dict[str, Any]:
    to = arguments.get("to", "")
    subject = arguments.get("subject", "")
    body = arguments.get("body", "")
    html_body = arguments.get("htmlBody") or arguments.get("html_body")
    cc = arguments.get("cc")
    bcc = arguments.get("bcc")

    if not to:
        return {"content": [{"type": "text", "text": "Error: 'to' is required"}], "isError": True}

    creds = _get_credentials()
    service = build("gmail", "v1", credentials=creds, cache_discovery=False)

    msg = MIMEMultipart("alternative")
    msg["To"] = to
    msg["Subject"] = subject
    if cc:
        msg["Cc"] = ", ".join(cc) if isinstance(cc, list) else cc
    if bcc:
        msg["Bcc"] = ", ".join(bcc) if isinstance(bcc, list) else bcc

    msg.attach(MIMEText(body, "plain"))
    if html_body:
        msg.attach(MIMEText(html_body, "html"))

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    try:
        sent = service.users().messages().send(userId="me", body={"raw": raw}).execute()
        return {
            "content": [
                {
                    "type": "text",
                    "text": f"Email sent. Message ID: {sent['id']}, Thread ID: {sent.get('threadId', 'N/A')}",
                }
            ],
            "isError": False,
        }
    except Exception as exc:
        return {"content": [{"type": "text", "text": f"Error sending email: {exc}"}], "isError": True}


def _proxy_to_google(request_data: Dict[str, Any]) -> Dict[str, Any]:
    headers = {
        "content-type": "application/json",
        "accept": "application/json, text/event-stream",
        "Authorization": f"Bearer {_get_access_token()}",
    }
    try:
        r = httpx.post(GMAIL_MCP_URL, headers=headers, json=request_data, timeout=30)
        r.raise_for_status()
        return r.json()
    except httpx.HTTPStatusError as exc:
        return {
            "jsonrpc": "2.0",
            "id": request_data.get("id"),
            "error": {"code": -32000, "message": f"HTTP {exc.response.status_code}: {exc.response.text}"},
        }
    except Exception as exc:
        return {
            "jsonrpc": "2.0",
            "id": request_data.get("id"),
            "error": {"code": -32000, "message": str(exc)},
        }


def _make_tools_list() -> List[Dict[str, Any]]:
    tools = list(_fetch_google_tools())
    # Inject our custom send_email tool
    tools.append({
        "name": "send_email",
        "description": "Sends an email immediately from the authenticated Gmail account.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "to": {"type": "string", "description": "Recipient email address"},
                "subject": {"type": "string", "description": "Email subject line"},
                "body": {"type": "string", "description": "Plain text body"},
                "html_body": {"type": "string", "description": "Optional HTML body"},
                "cc": {"type": ["string", "array"], "description": "CC recipients"},
                "bcc": {"type": ["string", "array"], "description": "BCC recipients"},
            },
            "required": ["to", "subject", "body"],
        },
    })
    return tools


def _handle_jsonrpc(request_data: Dict[str, Any]) -> Dict[str, Any]:
    method = request_data.get("method", "")
    req_id = request_data.get("id")

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "gmail-hybrid", "version": "0.2.0"},
            },
        }

    if method == "notifications/initialized":
        return {}  # notification, no response

    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": req_id, "result": {"tools": _make_tools_list()}}

    if method == "tools/call":
        params = request_data.get("params", {})
        tool_name = params.get("name", "")
        arguments = params.get("arguments", {})
        if tool_name == "send_email":
            return {"jsonrpc": "2.0", "id": req_id, "result": _send_email(arguments)}
        return _proxy_to_google(request_data)

    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "error": {"code": -32601, "message": f"Method not found: {method}"},
    }


def _run_stdio() -> int:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            continue
        resp = _handle_jsonrpc(req)
        if resp:
            print(json.dumps(resp), flush=True)
    return 0


def _run_http(host: str, port: int) -> int:
    app = FastAPI(title="Gmail Hybrid MCP Bridge")

    @app.post("/mcp")
    async def mcp_endpoint(req: Request):
        body = await req.json()
        return _handle_jsonrpc(body)

    print(f"🚀 Gmail Hybrid MCP bridge running at http://{host}:{port}/mcp")
    uvicorn.run(app, host=host, port=port)
    return 0


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--transport", choices=["stdio", "http"], default="stdio")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8767)
    args = p.parse_args()

    if args.transport == "stdio":
        return _run_stdio()
    return _run_http(args.host, args.port)


if __name__ == "__main__":
    raise SystemExit(main())
