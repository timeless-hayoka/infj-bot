#!/usr/bin/env python3
"""Demo client to submit an autonomous plan to the INFJ Companion HTTP bridge."""

import json
import sys
from typing import Any, Dict

import requests


def run_plan(host: str, port: int, token: Optional[str], plan: Dict[str, Any]):
    url = f"http://{host}:{port}/autonomy"
    payload = {"plan": plan}
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    r = requests.post(url, json=payload, headers=headers or None, timeout=30)
    r.raise_for_status()
    return r.json()


def main() -> int:
    host = "127.0.0.1"
    port = 8080
    token = None
    # allow token via env var
    import os

    token = os.getenv("MCP_HTTP_TOKEN", token)
    # example plan: small sequence of useful tools
    plan = [
        {
            "tool": "emotional_clarity",
            "args": ["I'm exhausted and uncertain about next steps"],
        },
        {
            "tool": "dissonance_map",
            "args": ["I want to start a business but fear instability"],
        },
        {
            "tool": "todo_add",
            "args": ["Research part-time business ideas"],
            "kwargs": {"priority": "normal"},
        },
        {"tool": "todo_list", "kwargs": {"status": "active"}},
    ]
    try:
        out = run_plan(host, port, token, plan)
        print(json.dumps(out, indent=2, ensure_ascii=False))
        return 0
    except Exception as exc:
        print("Error:", exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
