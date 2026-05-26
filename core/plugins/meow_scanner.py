#!/usr/bin/env python3
"""Bug Bot Meow — the chaos gremlin code scanner.

Hunts for TODOs, FIXMEs, BUGs, HACKs, and other suspicious patterns
across the codebase. Integrates with the Bug Bot findings DB.
"""

import glob
import os
import re
from datetime import datetime
from typing import Dict, List, Tuple

MEOW = r"""
 /_/
( o.o )
 > ^ <  Bug Bot Meow v1.0 is here to cause chaos
"""

PATTERNS = {
    "TODO": r"#\s*TODO[:\s]",
    "FIXME": r"#\s*FIXME[:\s]",
    "BUG": r"#\s*BUG[:\s]",
    "HACK": r"#\s*HACK[:\s]",
    "XXX": r"#\s*XXX[:\s]",
    "pass": r"^\s*pass\s*(#.*)?$",
    "print": r"^\s*print\([^)]*\)",
    "bare except": r"except\s*:\s*$",
    "hardcoded secret": r"(api_key|apikey|password|secret|token)\s*=\s*['\"][^'\"]{8,}['\"]",
}

SKIP_DIRS = {
    "venv",
    ".venv",
    "__pycache__",
    "node_modules",
    ".git",
    "chroma_db",
    "dist",
    "build",
}


def meow_banner() -> str:
    return MEOW + "\n🐛✨ **BUG BOT MEOW** has awakened... nyaa~\n"


def scan_codebase(root: str = ".") -> Tuple[List[Dict], Dict[str, int]]:
    """Scan for suspicious patterns and return findings + summary."""
    findings: List[Dict] = []
    summary: Dict[str, int] = {name: 0 for name in PATTERNS}
    files_scanned = 0

    for pattern in glob.glob(os.path.join(root, "**/*.py"), recursive=True):
        if any(skip in pattern for skip in SKIP_DIRS):
            continue
        try:
            with open(pattern, "r", encoding="utf-8") as f:
                lines = f.readlines()
            files_scanned += 1
            rel_path = os.path.relpath(pattern, root)
            for i, line in enumerate(lines, 1):
                for name, regex in PATTERNS.items():
                    if re.search(regex, line, re.IGNORECASE):
                        findings.append(
                            {
                                "file": rel_path,
                                "line": i,
                                "pattern": name,
                                "code": line.strip()[:120],
                            }
                        )
                        summary[name] += 1
        except Exception:
            continue

    return findings, summary


def format_meow_report(findings: List[Dict], summary: Dict[str, int]) -> str:
    lines = [meow_banner()]
    lines.append(
        f"😼 Scanned codebase... found **{len(findings)}** suspicious meows:\n"
    )

    # Group by pattern
    by_pattern: Dict[str, List[Dict]] = {}
    for f in findings:
        by_pattern.setdefault(f["pattern"], []).append(f)

    for pattern_name, items in sorted(by_pattern.items(), key=lambda x: -len(x[1])):
        lines.append(f"\n🔥 **{pattern_name}** ({len(items)} found)")
        for item in items[:5]:
            lines.append(f"   🐾 {item['file']}:{item['line']} → {item['code']}")
        if len(items) > 5:
            lines.append(
                f"   ... and {len(items) - 5} more hiding in the shadows nyaa~"
            )

    lines.append("\n📊 Summary:")
    for name, count in sorted(summary.items(), key=lambda x: -x[1]):
        if count > 0:
            lines.append(f"   {name}: {count}")

    lines.append(f"\n🕒 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("💖 Bug Bot Meow is purring at 3000% chaos capacity")
    return "\n".join(lines)


def meow_hunt(root: str = ".") -> str:
    """Run the full meow scan and return formatted report."""
    findings, summary = scan_codebase(root)
    return format_meow_report(findings, summary)


if __name__ == "__main__":
    print(meow_hunt())
