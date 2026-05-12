"""Simple email sender for INFJ bot.

Supports SMTP (Gmail, SendGrid, etc.) via environment variables,
and falls back to the Gmail MCP hybrid server when credentials exist.

Env vars:
  SMTP_HOST (default: smtp.gmail.com)
  SMTP_PORT (default: 587)
  SMTP_USER
  SMTP_PASS
  SMTP_FROM (default: SMTP_USER)
"""
from __future__ import annotations

import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any


CREDS_PATH = Path.home() / ".config" / "infj_bot" / "gmail_credentials.json"


def _smtp_send(
    to: str,
    subject: str,
    body: str,
    html_body: str | None = None,
    cc: str | None = None,
    bcc: str | None = None,
) -> dict[str, Any]:
    host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    port = int(os.getenv("SMTP_PORT", "587"))
    user = os.getenv("SMTP_USER", "")
    password = os.getenv("SMTP_PASS", "")
    from_addr = os.getenv("SMTP_FROM", user)

    if not user or not password:
        return {
            "ok": False,
            "error": "SMTP_USER and SMTP_PASS must be set in environment or .env",
        }

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to
    if cc:
        msg["Cc"] = cc
    if bcc:
        msg["Bcc"] = bcc

    msg.attach(MIMEText(body, "plain"))
    if html_body:
        msg.attach(MIMEText(html_body, "html"))

    try:
        with smtplib.SMTP(host, port, timeout=30) as server:
            server.starttls()
            server.login(user, password)
            server.send_message(msg)
        return {"ok": True, "error": None}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def send_email(
    to: str,
    subject: str,
    body: str,
    html_body: str | None = None,
    cc: str | None = None,
    bcc: str | None = None,
) -> dict[str, Any]:
    """Send an email using SMTP or Gmail MCP."""
    # Prefer SMTP if configured
    if os.getenv("SMTP_USER") and os.getenv("SMTP_PASS"):
        return _smtp_send(to, subject, body, html_body, cc, bcc)

    # Check for Gmail MCP credentials
    if CREDS_PATH.exists():
        try:
            return _gmail_mcp_send(to, subject, body, html_body, cc, bcc)
        except Exception as exc:
            return {"ok": False, "error": f"Gmail MCP failed: {exc}"}

    return {
        "ok": False,
        "error": (
            "No email provider configured.\n"
            "Option 1: Set SMTP_USER + SMTP_PASS in .env (any provider)\n"
            "Option 2: Run: python scripts/gmail_mcp_auth.py --client-secret <path>"
        ),
    }


def _gmail_mcp_send(
    to: str,
    subject: str,
    body: str,
    html_body: str | None = None,
    cc: str | None = None,
    bcc: str | None = None,
) -> dict[str, Any]:
    import base64
    import json

    from google.auth.transport.requests import Request as GoogleRequest
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    SCOPES = [
        "https://www.googleapis.com/auth/gmail.modify",
        "https://www.googleapis.com/auth/gmail.readonly",
        "https://www.googleapis.com/auth/gmail.send",
    ]

    creds = Credentials.from_authorized_user_file(str(CREDS_PATH), SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(GoogleRequest())
        data = json.loads(CREDS_PATH.read_text())
        data["token"] = creds.token
        CREDS_PATH.write_text(json.dumps(data, indent=2))

    service = build("gmail", "v1", credentials=creds, cache_discovery=False)

    msg = MIMEMultipart("alternative")
    msg["To"] = to
    msg["Subject"] = subject
    if cc:
        msg["Cc"] = cc
    if bcc:
        msg["Bcc"] = bcc

    msg.attach(MIMEText(body, "plain"))
    if html_body:
        msg.attach(MIMEText(html_body, "html"))

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    sent = service.users().messages().send(userId="me", body={"raw": raw}).execute()
    return {"ok": True, "error": None, "message_id": sent["id"]}
