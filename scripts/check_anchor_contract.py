#!/usr/bin/env python3
"""Check the real ANCHOR consumer boundary without loading model or voice stacks."""

from __future__ import annotations

import argparse
import hashlib
import inspect
import json
import logging
import os
import subprocess
import sys
from datetime import UTC, datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))


def git_revision(root: Path) -> str:
    return subprocess.check_output(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        text=True,
        timeout=10,
    ).strip()


def check(anchor_root: Path) -> dict:
    anchor_root = anchor_root.resolve()
    if not (anchor_root / "knowledge/manifest.json").is_file():
        raise ValueError("ANCHOR knowledge manifest is missing")
    os.environ["ANCHOR_ROOT"] = str(anchor_root)
    from core import anchor_analytics, anchor_context

    if anchor_context.resolve_anchor_repo_root() != anchor_root:
        raise ValueError("knowledge consumer resolved a different ANCHOR checkout")
    if anchor_analytics.resolve_anchor_root() != anchor_root:
        raise ValueError("analytics consumer resolved a different ANCHOR checkout")
    provider = anchor_context.get_anchor_knowledge_provider()
    source = Path(inspect.getfile(type(provider))).resolve()
    if source != anchor_root / "knowledge_provider.py":
        raise ValueError("knowledge provider came from a different checkout")
    topics = anchor_context.list_anchor_repo_knowledge()
    if not topics:
        raise ValueError("ANCHOR topic registry is empty")
    hashes = {}
    for topic in topics:
        doc = anchor_context.get_anchor_repo_knowledge_topic(topic["slug"])
        if doc is None or not doc["content"].strip():
            raise ValueError(f"missing or empty topic: {topic['slug']}")
        hashes[topic["slug"]] = hashlib.sha256(doc["content"].encode()).hexdigest()
    if not anchor_context.search_anchor_repo_knowledge(topics[0]["title"], limit=5):
        raise ValueError("knowledge search returned no matches for a registered title")
    for subsystem in topics[0].get("subsystems", []):
        if not anchor_context.refs_anchor_repo_knowledge(subsystem):
            raise ValueError("knowledge subsystem reference lookup returned no matches")
    analytics = anchor_analytics.build_benchmark_analytics(limit=5, top_n=3)
    if analytics["status"] != "ready":
        raise ValueError("benchmark analytics unavailable")
    for source in analytics["analytics_sources"].values():
        if Path(source).resolve().parent != anchor_root:
            raise ValueError("analytics imported a module from a different checkout")
    if (
        analytics["benchmark_strategy"].get("source")
        != "anchor_strategy.compute_strategy"
    ):
        raise ValueError("unexpected benchmark strategy contract")
    return {
        "status": "PASS",
        "checked_at": datetime.now(UTC).isoformat(),
        "infj_commit": git_revision(PROJECT_ROOT),
        "anchor_commit": git_revision(anchor_root),
        "topic_count": len(topics),
        "topic_sha256": hashes,
        "manifest_sha256": hashlib.sha256(
            (anchor_root / "knowledge/manifest.json").read_bytes()
        ).hexdigest(),
        "coverage": [
            "consumer root resolution",
            "canonical imports",
            "all registered topics",
            "search",
            "subsystem references",
            "canonical trends and strategy",
        ],
        "limitations": [
            "Does not update deployed checkouts or restart MCP processes",
            "Does not load models, voice, ChromaDB, or the full MCP server",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--anchor-root", type=Path, default=PROJECT_ROOT.parent / "ANCHOR"
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        result = check(args.anchor_root)
        code = 0
    except Exception as exc:
        logging.getLogger(__name__).debug(
            "Operation failed; applying fallback", exc_info=True
        )
        result = {"status": "FAIL", "error": f"{type(exc).__name__}: {exc}"}
        code = 1
    text = json.dumps(result, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
    print(text)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
