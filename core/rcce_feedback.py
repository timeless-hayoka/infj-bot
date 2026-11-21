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
