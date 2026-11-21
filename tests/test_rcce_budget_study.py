import json
from collections import Counter

import rcce_budget_study as study


def test_history_changes_and_contains_distractors(tmp_path):
    root = tmp_path / "history"
    study.prepare(root)
    cases = study.make_cases()
    assert len(cases) == 72
    assert sorted(Counter(profile for profile, *_ in cases).values()) == [9] * 8
    for profile, context, _, options, expected, _ in cases:
        rows = json.loads((root / f"{profile}.json").read_text())
        assert len(rows) == 51
        verified = sorted(r for r in rows if r[1:3] == [profile, context] and r[4])
        assert len(verified) == 4
        assert [r[3] for r in verified] == [
            verified[-1][3],
            verified[1][3],
            verified[1][3],
            verified[-1][3],
        ]
        assert verified[1][3] != verified[-1][3]
        assert verified[-1][3] == study.latest_rule(profile, context)
        assert expected in {"A", "B"}
        replay = study.build_prompt(rows, profile, context, options, "replay")
        organized = study.build_prompt(rows, profile, context, options, "organized")
        assert (
            replay.split("Feedback records")[0]
            == organized.split("Feedback records")[0]
        )
        assert replay.count("\nReview ") == 51 and organized.count("\nReview ") == 1


def test_strict_json_choice():
    assert study.decode_choice('{"choice": "A"}') == "A"
    for bad in (
        "A",
        "{}",
        '{"choice":"C"}',
        '{"choice":"A","choice":"B"}',
        '{"choice":"A","extra":0}',
    ):
        assert study.decode_choice(bad) is None


def test_prespecified_verdicts():
    rows = []
    for profile, context, instance, _, _, _ in study.make_cases():
        for arm in study.ARMS:
            rows.append(
                dict(
                    profile=profile,
                    context=context,
                    instance=instance,
                    arm=arm,
                    correct=arm == "organized",
                    choice="A",
                    prompt_tokens=100,
                )
            )
    assert study.analyze(rows)["verdict"] == "organized_accuracy_advantage"
    for row in rows:
        row.update(
            correct=True, prompt_tokens=100 if row["arm"] == "organized" else 200
        )
    assert study.analyze(rows)["verdict"] == "organized_token_efficiency"
    for row in rows:
        row["prompt_tokens"] = 100
    assert study.analyze(rows)["verdict"] == "use_replay_matched"
    rows[0]["choice"] = None
    assert study.analyze(rows)["verdict"] == "measurement_failed"
