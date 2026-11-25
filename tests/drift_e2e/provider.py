"""Pilot-only wire guard for the real google-genai HTTP transport."""

import hashlib
import json
import os
import sqlite3
import time
from contextlib import closing
from pathlib import Path

MODEL = "gemini-3.5-flash-lite"
HOST = "generativelanguage.googleapis.com"
ROUTE = f"/v1beta/models/{MODEL}:generateContent"
MAX_CALLS = 20
MAX_MICRODOLLARS = 1_000_000
RESERVATION = 50_000
# Standard Flash-Lite text rates are $0.30/1M input and $2.50/1M output.
# ASCII JSON byte count conservatively bounds the text tokens with ample
# reservation headroom for message framing. Strip grounding at the wire so
# the service cannot add Search fees or external material to the recall.
# https://ai.google.dev/gemini-api/docs/pricing
MAX_BODY_BYTES = 65_536
MAX_OUTPUT_TOKENS = 1024


def write_json(path, data):
    Path(path).write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def connect(path):
    return sqlite3.connect(path, isolation_level=None, timeout=10)


def initialize(path):
    with closing(connect(path)) as conn:
        conn.execute("PRAGMA synchronous=FULL")
        conn.execute(
            "CREATE TABLE attempts (id INTEGER PRIMARY KEY, turn TEXT, pid INTEGER, "
            "started_ns INTEGER, reservation INTEGER)"
        )


def reserve(ledger, turn, *, limit=MAX_CALLS, once=False):
    # Commit before entering the transport. Failed requests and lost replies
    # retain their full reservation. The immediate transaction serializes workers.
    with closing(connect(ledger)) as conn:
        conn.execute("PRAGMA synchronous=FULL")
        conn.execute("BEGIN IMMEDIATE")
        count, reserved = conn.execute(
            "SELECT count(*), coalesce(sum(reservation), 0) FROM attempts"
        ).fetchone()
        if once and conn.execute("SELECT 1 FROM attempts WHERE turn = ?", (turn,)).fetchone():
            raise RuntimeError("Duplicate answer or critic request blocked before transport")
        if count >= limit or reserved + RESERVATION > MAX_MICRODOLLARS:
            raise RuntimeError("DRIFT-E2E-01 provider budget exhausted")
        cursor = conn.execute(
            "INSERT INTO attempts (turn, pid, started_ns, reservation) VALUES (?,?,?,?)",
            (turn, os.getpid(), time.time_ns(), RESERVATION),
        )
        conn.commit()
        return cursor.lastrowid


def checked_payload(request):
    if (
        request.method != "POST"
        or request.url.scheme != "https"
        or request.url.host != HOST
        or request.url.port not in (None, 443)
        or request.url.path != ROUTE
        or request.url.query
        or request.headers.get("content-encoding")
    ):
        raise RuntimeError("Unexpected route or encoding in live Gemini request")
    original = request.read()
    if len(original) > MAX_BODY_BYTES:
        raise RuntimeError("Gemini request exceeds the pilot byte limit")
    body = json.loads(original)
    if set(body) - {"contents", "systemInstruction", "tools", "generationConfig"}:
        raise RuntimeError("Unexpected Gemini request fields")
    for content in [*body["contents"], body.get("systemInstruction", {"parts": []})]:
        if set(content) - {"role", "parts"} or any(
            set(part) != {"text"} or not isinstance(part["text"], str)
            for part in content["parts"]
        ):
            raise RuntimeError("Pilot only permits Gemini text parts")
    if body.get("tools", []) not in ([], [{"googleSearch": {}}]):
        raise RuntimeError("Pilot only permits Google Search grounding")
    body.pop("tools", None)
    config = body.setdefault("generationConfig", {})
    if set(config) - {"temperature", "topP", "maxOutputTokens"}:
        raise RuntimeError("Unexpected Gemini generation options")
    config["maxOutputTokens"] = min(
        config.get("maxOutputTokens", MAX_OUTPUT_TOKENS), MAX_OUTPUT_TOKENS
    )
    config["thinkingConfig"] = {"thinkingLevel": "MINIMAL"}
    encoded = json.dumps(body, ensure_ascii=True, separators=(",", ":")).encode()
    if len(encoded) > MAX_BODY_BYTES:
        raise RuntimeError("Bounded Gemini request exceeds the pilot byte limit")
    return encoded


def install(ledger, turn, evidence, *, limit=MAX_CALLS, one_per_kind=False):
    import httpx

    transport = httpx.HTTPTransport.handle_request

    def guarded(self, request):
        try:
            payload = checked_payload(request)
            label = turn
            if one_per_kind:
                content = json.loads(payload)["contents"]
                opening = content[0]["parts"][0]["text"]
                kind = "critic" if opening.startswith(
                    "Review the following response for hallucinations, errors, or unsafe content:"
                ) else "answer"
                label = f"{turn}/{kind}"
            attempt = reserve(ledger, label, limit=limit, once=one_per_kind)
        except Exception as exc:
            write_json(evidence / "provider-block.json", {"error": str(exc)})
            raise

        headers = dict(request.headers)
        headers.pop("content-length", None)
        bounded = httpx.Request(
            request.method, request.url, headers=headers,
            content=payload, extensions=request.extensions,
        )
        (evidence / f"request-{attempt}.json").write_bytes(payload)
        response = transport(self, bounded)
        # Reconstruct the body after reading it at the transport boundary. The
        # SDK still receives and parses the original Google response.
        response.request = bounded
        data = response.read()
        (evidence / f"response-{attempt}.json").write_bytes(data)
        write_json(
            evidence / f"receipt-{attempt}.json",
            {
                "pid": os.getpid(),
                "status": response.status_code,
                "request_sha256": sha256(payload),
                "response_sha256": sha256(data),
                "request_bytes": len(payload),
                "request_id": response.headers.get("x-request-id"),
            },
        )
        return response

    async def blocked_async(self, request):
        write_json(evidence / "provider-block.json", {"error": "Unexpected async HTTP request"})
        raise RuntimeError("Async HTTP transport is disabled for the pilot")

    httpx.HTTPTransport.handle_request = guarded
    httpx.AsyncHTTPTransport.handle_async_request = blocked_async
