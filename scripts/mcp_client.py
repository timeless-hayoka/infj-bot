#!/usr/bin/env python3
"""Simple HTTP client for the INFJ Companion HTTP bridge.

Usage examples:
  python scripts/mcp_client.py --tool emotional_clarity --data "I'm stressed"
  python scripts/mcp_client.py --run-all
"""

import argparse
import json
import sys
from typing import Any, Dict

import requests


def invoke(
    host: str, port: int, tool: str, args=None, kwargs=None, token: str | None = None
) -> Dict[str, Any]:
    url = f"http://{host}:{port}/invoke/{tool}"
    payload = {"args": args or [], "kwargs": kwargs or {}}
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    r = requests.post(url, json=payload, headers=headers or None, timeout=15)
    r.raise_for_status()
    return r.json()


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8080)
    p.add_argument("--tool", help="Tool name to invoke")
    p.add_argument("--data", help="Simple data string for common tools")
    p.add_argument(
        "--run-all", action="store_true", help="Run a set of demo invocations"
    )
    args = p.parse_args()

    try:
        token = os.getenv("MCP_HTTP_TOKEN")
        if args.run_all:
            demos = [
                ("emotional_clarity", {"args": ["I'm feeling overwhelmed and tired."]}),
                (
                    "dissonance_map",
                    {
                        "args": [
                            "I want to change careers but I'm afraid of losing stability."
                        ]
                    },
                ),
                ("memory_search", {"args": ["vacation"], "kwargs": {"n_results": 3}}),
                ("document_search", {"args": ["resume"], "kwargs": {"n_results": 3}}),
                ("todo_list", {"kwargs": {"status": "active"}}),
                ("companion_think", {"args": ["How can I get unstuck this week?"]}),
            ]
            for tool, payload in demos:
                print(f"-> {tool}")
                out = invoke(
                    args.host,
                    args.port,
                    tool,
                    payload.get("args"),
                    payload.get("kwargs"),
                    token=token,
                )
                print(json.dumps(out, indent=2, ensure_ascii=False))
            return 0

        if not args.tool:
            p.print_help()
            return 2

        payload_args = [args.data] if args.data is not None else []
        token = os.getenv("MCP_HTTP_TOKEN")
        resp = invoke(args.host, args.port, args.tool, payload_args, token=token)
        print(json.dumps(resp, indent=2, ensure_ascii=False))
        return 0
    except Exception as exc:
        print("Error:", exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
