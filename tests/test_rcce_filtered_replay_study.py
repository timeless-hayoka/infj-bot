from collections import Counter

from drift.core.rcce_feedback import Feedback, relevant_feedback, resolve_feedback
import rcce_filtered_replay_study as study
from rcce_budget_study import PROMPT_BYTE_LIMIT


def test_applicable_retractions_and_scope_precedence():
    base = Feedback(10, "P0", "copper", "default", "cheap")
    rush = Feedback(20, "P0", "copper", "rush", "fast")
    wrong = Feedback(30, "P0", "copper", "rush", "cheap")
    retract = Feedback(40, "P0", "copper", "rush", retracts=30)
    unverified = Feedback(50, "P0", "copper", "rush", "cheap", verified=False)
    unrelated = Feedback(90, "P1", "copper", "rush", "cheap")
    rows = [unrelated, rush, retract, unverified, base, wrong]
    assert relevant_feedback(rows, "P0", "copper", "rush") == [
        retract,
        wrong,
        rush,
        base,
    ]
    assert resolve_feedback(rows, "P0", "copper", "rush") is rush
    assert resolve_feedback(rows, "P0", "copper", "standard") is base
    assert resolve_feedback(rows, "P1", "quartz", "rush") is None


def test_matched_fresh_cases_share_task_but_differ_in_history_view():
    banks = dict(study.histories())
    cases = study.tasks()
    assert len(cases) == len({case[:3] for case in cases}) == 48
    assert Counter(case[2] for case in cases) == {
        "rush": 24,
        "fragile": 12,
        "standard": 12,
    }
    for profile, context, scope, jobs, options, expected, arms in cases:
        assert set(arms) == set(study.ARMS)
        views = {}
        for arm in arms:
            prompt = study.build_prompt(
                banks[profile], profile, context, scope, jobs, options, arm
            )
            assert len(prompt.encode()) <= PROMPT_BYTE_LIMIT
            views[arm] = prompt.split("\nFeedback:\n")
        assert len({head for head, _ in views.values()}) == 1
        assert len(views["full"][1].splitlines()) == 51
        chronological = views["filtered"][1].splitlines()
        ids = [int(line.split()[0]) for line in chronological]
        assert ids == sorted(ids, reverse=True)
        selected = views["organized"][1]
        assert selected in chronological and selected != chronological[0]
        assert all(line in views["full"][1].splitlines() for line in chronological)
        rule = study.preference(profile, context)
        assert selected.endswith(study.inverse(rule) if scope == "rush" else rule)
        assert expected in "AB"


def test_decision_thresholds_against_filtered_replay():
    rows = [
        dict(
            profile=profile,
            context=context,
            scope=scope,
            arm=arm,
            correct=arm == "organized",
            choice="A",
            prompt_tokens=100,
        )
        for profile, context, scope, *_ in study.tasks()
        for arm in study.ARMS
    ]
    assert study.summarize(rows)["verdict"] == "organizer_accuracy"
    for row in rows:
        row.update(
            correct=True, prompt_tokens=100 if row["arm"] == "organized" else 150
        )
    assert study.summarize(rows)["verdict"] == "organizer_efficiency"
    for row in rows:
        row["prompt_tokens"] = 100
    assert study.summarize(rows)["verdict"] == "use_filtered_equivalent"
    rows[0]["choice"] = None
    assert study.summarize(rows)["verdict"] == "measurement_failed"
