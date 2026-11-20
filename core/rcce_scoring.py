"""Deterministic task oracles. Correctness and format compliance are separate."""
from __future__ import annotations

import json
import re


def score_response(answer: str, expected: str, format_kind: str) -> dict[str, bool]:
    if format_kind == "integer":
        valid = re.fullmatch(r"-?\d+", answer) is not None
        tokens = re.findall(r"(?<![\w.])-?\d+(?![\w.])", answer)
        correct = bool(tokens) and tokens[-1] == expected
    elif format_kind == "token":
        valid = answer == expected
        correct = answer.strip() == expected
    elif format_kind == "json_integer":
        try:
            parsed = json.loads(answer)
        except (ValueError, TypeError):
            parsed = None
        correct = isinstance(parsed, dict) and str(parsed.get("answer")) == expected
        valid = (
            isinstance(parsed, dict)
            and set(parsed) == {"answer"}
            and type(parsed["answer"]) is int
        )
    else:
        raise ValueError("unsupported format oracle")
    return {"correct": bool(correct), "format_compliant": bool(valid)}


def summarize_pairs(rows: list[dict]) -> dict:
    pairs: dict[tuple[str, int], dict[str, dict]] = {}
    for row in rows:
        key = (row["task_id"], row["repeat"])
        condition = row["condition"]
        if condition not in {"enabled", "disabled"} or condition in pairs.setdefault(key, {}):
            raise ValueError("invalid or duplicate trial condition")
        pairs[key][condition] = row
    complete = [p for p in pairs.values() if set(p) == {"enabled", "disabled"}]
    result = {"paired_trials": len(complete), "incomplete_pairs": len(pairs) - len(complete)}
    for condition in ("enabled", "disabled"):
        result[condition] = {
            "correct": sum(int(p[condition]["correct"]) for p in complete),
            "format_compliant": sum(int(p[condition]["format_compliant"]) for p in complete),
            "total": len(complete),
        }
    return result
