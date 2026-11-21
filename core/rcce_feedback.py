"""Resolve explicit, verified feedback for partner-specific decisions."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Feedback:
    review: int
    profile: str
    context: str
    scope: str
    preference: str | None = None
    retracts: int | None = None
    verified: bool = True


def relevant_feedback(records, profile, context, scope):
    """Return verified feedback and corrections that apply to this query, newest first."""
    return sorted(
        (
            row
            for row in records
            if row.verified
            and (row.profile, row.context) == (profile, context)
            and row.scope in {"default", scope}
        ),
        key=lambda row: row.review,
        reverse=True,
    )


def resolve_feedback(records, profile, context, scope):
    """Select an active exception or fall back to the latest active default."""
    relevant = relevant_feedback(records, profile, context, scope)
    retracted = {row.retracts for row in relevant if row.retracts is not None}
    active = [
        row
        for row in relevant
        if row.preference is not None and row.review not in retracted
    ]
    return next(
        (row for row in active if row.scope == scope),
        next((row for row in active if row.scope == "default"), None),
    )


def load_pilot_preference(path, profile, context, scope):
    """Read an operator-supplied feedback file and return bounded prompt guidance."""
    import json

    with path.open("rb") as source:
        raw = source.read(128_001)
    if len(raw) > 128_000:
        raise ValueError("feedback file exceeds 128 kB")
    entries = json.loads(raw)
    if not isinstance(entries, list):
        raise ValueError("feedback must be a JSON array of records")

    records = {}
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("feedback entries must be JSON objects")
        try:
            row = Feedback(**entry)
        except TypeError as exc:
            raise ValueError("feedback record fields are invalid") from exc
        if (
            type(row.review) is not int
            or row.review <= 0
            or any(
                not isinstance(value, str) or not value.strip()
                for value in (row.profile, row.context, row.scope)
            )
            or type(row.verified) is not bool
            or (row.retracts is None and row.preference not in ("fast", "cheap"))
            or (
                row.retracts is not None
                and (
                    type(row.retracts) is not int
                    or not 0 < row.retracts < row.review
                    or row.preference is not None
                )
            )
        ):
            raise ValueError("feedback record types or values are invalid")
        key = (row.profile, row.context, row.review)
        if key in records:
            raise ValueError("duplicate review within profile and context")
        records[key] = row

    for row in records.values():
        if row.retracts is None:
            continue
        target = records.get((row.profile, row.context, row.retracts))
        if target is None or target.scope != row.scope or target.preference is None:
            raise ValueError(
                "retraction must refer to an earlier preference in the same scope"
            )

    choice = resolve_feedback(records.values(), profile, context, scope)
    if choice is None:
        raise ValueError("no applicable verified preference")
    metric = {"fast": "less total time", "cheap": "lower total cost"}[choice.preference]
    return (
        f"Saved decision preference for this request: prefer {metric} when comparing options. "
        "Follow the user's current instructions if they specify a different criterion."
    )
