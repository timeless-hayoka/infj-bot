import json
import urllib.error
import urllib.request
from datetime import datetime


BUG_SCOPE_TEMPLATE = """Bug bounty scope card
Program:
Authorized assets:
Out-of-scope assets:
Allowed test types:
Disallowed test types:
Rate limits:
Data handling:
Proof standard:
Stop conditions:
Notes:
"""


BUG_CHECKLIST = """Bug bot checklist
1. Confirm the target is in scope and write down the exact asset.
2. Identify the user role, account type, and permission level being tested.
3. Map normal behavior before looking for broken behavior.
4. Capture request, response, timestamp, account, and environment notes.
5. Prefer low-impact proof with synthetic data.
6. Stop if testing risks service disruption, privacy exposure, or out-of-scope access.
7. Convert every finding into: impact, evidence, reproduction, fix, and confidence.
"""


BUG_REPORT_TEMPLATE = """# Title
Clear vulnerability type in one affected asset.

## Summary
What is broken, where it is broken, and why it matters.

## Scope
- Program:
- Asset:
- Account/role:
- Authorization notes:

## Impact
Explain the realistic security consequence without exaggerating.

## Steps To Reproduce
1. 
2. 
3. 

## Evidence
- Request/response IDs:
- Screenshots or Burp items:
- Timestamps:

## Expected Result
What should happen.

## Actual Result
What happened instead.

## Suggested Fix
Practical remediation or hardening idea.

## Notes
Limits, assumptions, and anything intentionally not tested.
"""


def bridge_status(url="http://localhost:11434"):
    started = datetime.now().isoformat(timespec="seconds")
    try:
        with urllib.request.urlopen(url, timeout=2) as response:
            body = response.read(160).decode("utf-8", errors="replace").strip()
            return (
                "Local AI bridge\n"
                f"- url: {url}\n"
                f"- status: reachable ({response.status})\n"
                f"- checked_at: {started}\n"
                f"- preview: {body or 'no body'}"
            )
    except urllib.error.URLError as exc:
        return (
            "Local AI bridge\n"
            f"- url: {url}\n"
            "- status: offline or unreachable\n"
            f"- checked_at: {started}\n"
            f"- detail: {exc.reason}"
        )
    except Exception as exc:
        return (
            "Local AI bridge\n"
            f"- url: {url}\n"
            "- status: check failed\n"
            f"- checked_at: {started}\n"
            f"- detail: {type(exc).__name__}: {exc}"
        )


def format_mission(target, goal, status="active", notes=""):
    target = target.strip()
    goal = goal.strip()
    status = status.strip() or "active"
    notes = notes.strip()
    return {
        "target": target,
        "goal": goal,
        "status": status,
        "notes": notes,
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }


def render_mission(mission):
    return (
        "Bug mission\n"
        f"- target: {mission.get('target', '')}\n"
        f"- goal: {mission.get('goal', '')}\n"
        f"- status: {mission.get('status', '')}\n"
        f"- created_at: {mission.get('created_at', '')}\n"
        f"- notes: {mission.get('notes', '') or 'none'}"
    )


def parse_mission_args(args):
    target, sep, rest = args.partition("|")
    goal, sep2, notes = rest.partition("|")
    if not sep or not target.strip() or not goal.strip():
        raise ValueError("Use: /bug mission <target> | <goal> | [notes]")
    return format_mission(target, goal, notes=notes if sep2 else "")


def parse_note_args(args):
    target, sep, note = args.partition("|")
    if not sep or not target.strip() or not note.strip():
        raise ValueError("Use: /bug note <target> | <note>")
    return target.strip(), note.strip()


def mission_to_document(mission):
    return (
        f"Bug Mission: {mission['target']}\n"
        f"Goal: {mission['goal']}\n"
        f"Status: {mission['status']}\n"
        f"Notes: {mission['notes'] or 'none'}\n"
        f"Created: {mission['created_at']}"
    )


def note_to_document(target, note):
    return (
        f"Bug Note: {target}\n"
        f"Note: {note}\n"
        f"Created: {datetime.now().isoformat(timespec='seconds')}"
    )


def metadata_json(payload):
    return json.dumps(payload, sort_keys=True)
