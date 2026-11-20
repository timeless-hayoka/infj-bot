"""Render recalled interaction records as project-scoped, labeled evidence."""

from __future__ import annotations

import re
from collections import defaultdict

PROJECT = re.compile(r"\bProject\s+([A-Z][A-Za-z0-9_-]*)\b")
WEEKDAY = r"Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday"


def _user_text(record: str) -> str:
    """Use the user's saved statement, excluding any model-generated reply."""
    match = re.search(
        r"\buser:\s*(.*?)(?=\nBot:\s|$)", record, flags=re.IGNORECASE | re.DOTALL
    )
    return (match.group(1) if match else record).strip()


def _sentences(text: str) -> list[str]:
    return [part.strip() for part in re.split(r"(?<=[.!?])\s+", text) if part.strip()]


def _project_facts(
    records: list[str],
) -> tuple[dict[str, dict[str, list[str]]], list[str]]:
    projects: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    unclassified: list[str] = []
    deadlines: dict[str, dict[str, str]] = defaultdict(dict)

    for record_index, record in enumerate(records, 1):
        text = _user_text(record)
        project_match = PROJECT.search(text)
        if not project_match:
            unclassified.append(f"[RECORD {record_index}] {text}")
            continue
        project = project_match.group(1)
        facts = projects[project]
        labeled = False

        preference = re.search(r"\bI\s+prefer\s+([^.;!?]+)", text, re.IGNORECASE)
        if preference:
            facts["PREFERENCE"].append(
                f"Preferred response style: {preference.group(1).strip()} (record {record_index})"
            )
            labeled = True

        workspace = re.search(r"\bworkspace\s+is\s+([^.;!?]+)", text, re.IGNORECASE)
        if workspace:
            facts["WORKSPACE"].append(
                f"Workspace: {workspace.group(1).strip()} (record {record_index})"
            )
            labeled = True

        export = re.search(
            r"\b(?:will\s+ship\s+as|uses|will\s+use)\s+(?:an?\s+)?([A-Za-z][A-Za-z0-9_-]*)\s+export\b",
            text,
            re.IGNORECASE,
        )
        if export:
            facts["DECISION: EXPORT FORMAT"].append(
                f"Current export format: {export.group(1).upper()} (record {record_index})"
            )
            labeled = True

        update = re.search(
            rf"\bdelivery\s+moved\s+to\s+({WEEKDAY})\s*\.\s*This\s+supersedes\s+({WEEKDAY})",
            text,
            re.IGNORECASE,
        )
        if update:
            current, old = update.group(1).capitalize(), update.group(2).capitalize()
            deadlines[project]["current"] = f"{current} (record {record_index})"
            deadlines[project]["superseded"] = (
                f"{old} (superseded by {current}; record {record_index})"
            )
            labeled = True
        else:
            initial = re.search(
                rf"\bdelivery\s+day\s+is\s+({WEEKDAY})\b", text, re.IGNORECASE
            )
            if initial:
                deadlines[project].setdefault(
                    "initial",
                    f"{initial.group(1).capitalize()} (record {record_index})",
                )
                labeled = True

        progression = re.search(
            r"\bFor\s+Project\s+[A-Z][A-Za-z0-9_-]*,\s*([^.,]+),\s*([^.,]+),\s*then\s+([^.,]+)\.\s*([^.,]+?)\s+is\s+complete\.\s*([^.,]+?)\s+is\s+the\s+next\s+unfinished\s+step",
            text,
            re.IGNORECASE,
        )
        if progression:
            first, second, final, completed, next_step = (
                part.strip() for part in progression.groups()
            )
            facts["TASK PROGRESSION"].append(
                f"Sequence: {first} → {second} → {final}; completed: {completed}; "
                f"next unfinished: {next_step} (record {record_index})"
            )
            labeled = True

        # Preserve user evidence that this small deterministic formatter does
        # not understand, without carrying generated assistant text forward.
        if not labeled:
            facts["OTHER USER EVIDENCE"].append(f"{text} (record {record_index})")

    for project, dates in deadlines.items():
        if "superseded" in dates:
            projects[project]["DECISION: SUPERSEDED DELIVERY DAY"].append(
                dates["superseded"]
            )
            projects[project]["DECISION: CURRENT DELIVERY DAY"].append(dates["current"])
        elif "initial" in dates:
            projects[project]["DECISION: DELIVERY DAY"].append(dates["initial"])

    return projects, unclassified


def format_memory_facts(context: str) -> str:
    """Group recalled records into labeled facts while preserving provenance."""
    records = [
        part.strip() for part in re.split(r"\n---\n", context or "") if part.strip()
    ]
    projects, unclassified = _project_facts(records)
    lines = ["<retrieved_memory_evidence>", "SOURCE: retrieved saved user records"]
    if not projects and not unclassified:
        lines.append("No project facts were retrieved.")
    for project in sorted(projects, key=str.casefold):
        lines.append(f"PROJECT: {project}")
        for label, values in projects[project].items():
            lines.append(f"[{label}]")
            lines.extend(f"- {value}" for value in values)
    if unclassified:
        lines.append("[OTHER RETRIEVED USER EVIDENCE]")
        lines.extend(f"- {value}" for value in unclassified)
    lines.append("</retrieved_memory_evidence>")
    return "\n".join(lines)
