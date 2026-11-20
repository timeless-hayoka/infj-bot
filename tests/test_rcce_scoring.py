"""Independent correctness and format oracles for RCCE-1 trials."""
from drift.core.rcce_scoring import score_response, summarize_pairs


def test_correct_value_with_explanation_is_not_format_compliant():
    result = score_response("Method check: 12 * 12 = 144.\n\n144", "144", "integer")
    assert result == {"correct": True, "format_compliant": False}


def test_wrong_answer_can_have_valid_format():
    assert score_response("145", "144", "integer") == {
        "correct": False, "format_compliant": True,
    }


def test_exact_token_and_strict_json_are_independent():
    assert score_response(" YES ", "YES", "token") == {
        "correct": True, "format_compliant": False,
    }
    assert score_response('{"answer":42}', "42", "json_integer") == {
        "correct": True, "format_compliant": True,
    }
    assert score_response('{"answer":42,"extra":1}', "42", "json_integer") == {
        "correct": True, "format_compliant": False,
    }


def test_missing_and_unpaired_trials_are_not_silently_scored():
    rows = [
        {"task_id": "a", "repeat": 0, "condition": "enabled", "correct": True, "format_compliant": False},
        {"task_id": "a", "repeat": 0, "condition": "disabled", "correct": False, "format_compliant": True},
        {"task_id": "b", "repeat": 0, "condition": "enabled", "correct": True, "format_compliant": True},
    ]
    result = summarize_pairs(rows)
    assert result["paired_trials"] == 1
    assert result["incomplete_pairs"] == 1
    assert result["enabled"]["correct"] == 1
    assert result["disabled"]["format_compliant"] == 1
