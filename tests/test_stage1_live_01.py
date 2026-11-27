from decimal import Decimal
import pytest
from stage1_live_01 import Budget, GENERATE_RESERVE, META_RESERVE, paired_prompts, score

def test_budget_counts_every_attempt_and_refuses_over_limit(tmp_path):
    b = Budget(tmp_path / "attempts.jsonl")
    for _ in range(20):
        b.reserve("metadata", Decimal("0.01"))
    with pytest.raises(RuntimeError):
        b.reserve("extra", Decimal("0"))
    assert b.calls == 20
    assert len(b.path.read_text().splitlines()) == 20

def test_budget_refuses_over_spend_before_attempt(tmp_path):
    b = Budget(tmp_path / "attempts.jsonl")
    b.reserve("first", Decimal("0.99"))
    with pytest.raises(RuntimeError):
        b.reserve("extra", Decimal("0.02"))
    assert b.calls == 1
    with pytest.raises(RuntimeError):
        Budget(b.path)

def test_reserved_full_experiment_is_under_authorization():
    assert 9 * META_RESERVE + 8 * GENERATE_RESERVE < Decimal("1")

def test_pair_only_changes_actual_emitted_block():
    a = 'header\n[Verified strategy selection] {"strategy":"wrong"}\nquestion'
    b = 'other header\n[Verified strategy selection] {"strategy":"right"}\nquestion'
    control, treatment = paired_prompts(a, b)
    assert control == a
    assert treatment == a.replace("wrong", "right")
    with pytest.raises(RuntimeError):
        paired_prompts(a, a)
    with pytest.raises(RuntimeError):
        paired_prompts(a, b + "\n" + b)

def test_independent_exact_score():
    assert score(" A\n", "A")
    assert not score("B", "A")
    assert not score("A or B", "A")
