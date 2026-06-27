#!/usr/bin/env python3
"""OWASP Top 10 BugHunter Plugin for DRIFT.

Scans for the most critical security vulnerabilities:
1. SQL Injection (A03:2021-Injection)
2. Command Injection
3. XSS (Cross-Site Scripting)
4. Hardcoded Secrets (A07:2021-Identification and Authentication Failures)
5. Insecure Deserialization (A08:2021-Software and Data Integrity Failures)
"""

import glob
import os
import re
from typing import Dict, List, Tuple

OWASP_PATTERNS = {
    "SQL Injection (A03)": r"(SELECT\s+.*FROM\s+.*WHERE\s+.*%.*|execute\(\s*f[\"'].*\{.*\})",
    "Command Injection": r"(os\.system|subprocess\.Popen|subprocess\.call|eval|exec|os\.popen)\(",
    "Hardcoded Secret (A07)": r"(api_key|apikey|password|secret|token)\s*=\s*['\"][a-zA-Z0-9_\-]{8,}['\"]",
    "Insecure Deserialization (A08)": r"(pickle\.loads|yaml\.load)\(",
    "Weak Crypto": r"(md5|md4|sha1)\(",
    "Path Traversal": r"open\(.*(?:\+|%s).*\)",
    "XSS Vulnerability": r"(innerHTML|document\.write)\s*=\s*.*"
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

def scan_owasp(root: str = ".") -> Tuple[List[Dict], Dict[str, int]]:
    findings: List[Dict] = []
    summary: Dict[str, int] = {name: 0 for name in OWASP_PATTERNS}
    files_scanned = 0

    for pattern in glob.glob(os.path.join(root, "**/*.py"), recursive=True) + glob.glob(os.path.join(root, "**/*.js"), recursive=True):
        if any(skip in pattern for skip in SKIP_DIRS):
            continue
        try:
            with open(pattern, "r", encoding="utf-8") as f:
                lines = f.readlines()
            files_scanned += 1
            rel_path = os.path.relpath(pattern, root)
            for i, line in enumerate(lines, 1):
                for name, regex in OWASP_PATTERNS.items():
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

def format_owasp_report(findings: List[Dict], summary: Dict[str, int]) -> str:
    lines = ["\n🛡️ **DRIFT OWASP BUG HUNTER SCAN** 🛡️\n"]
    if not findings:
        lines.append("✅ No critical OWASP vulnerabilities found.")
        return "\n".join(lines)

    lines.append(f"⚠️ Found **{len(findings)}** potential vulnerabilities:\n")
    
    by_pattern: Dict[str, List[Dict]] = {}
    for f in findings:
        by_pattern.setdefault(f["pattern"], []).append(f)

    for pattern_name, items in sorted(by_pattern.items(), key=lambda x: -len(x[1])):
        lines.append(f"🚨 **{pattern_name}** ({len(items)} found)")
        for item in items[:5]:
            lines.append(f"   [!] {item['file']}:{item['line']} → {item['code']}")
        if len(items) > 5:
            lines.append(f"   ... and {len(items) - 5} more.")

    lines.append("\n📊 Summary:")
    for name, count in sorted(summary.items(), key=lambda x: -x[1]):
        if count > 0:
            lines.append(f"   {name}: {count}")

    return "\n".join(lines)

def run_owasp_scan(root: str = ".") -> str:
    findings, summary = scan_owasp(root)
    return format_owasp_report(findings, summary)

if __name__ == "__main__":
    print(run_owasp_scan())
