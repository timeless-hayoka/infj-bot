from __future__ import annotations

import math

from drift.trinity.imagine_core import ImagineCore
from drift.trinity.reality_anchor import RealityAnchor
from drift.trinity.te7_executive import TrinityExecutive
from drift.trinity.trinity_core import Trinity


def test_trinity_mode_selection_and_recalibration_are_stable():
    executive = TrinityExecutive({})

    assert executive.select_mode({'ambiguity': 0.05, 'risk': 0.1, 'novelty': 0.05}) == 'grounded'
    assert executive.select_mode({'ambiguity': 0.35, 'risk': 0.4, 'novelty': 0.25}) == 'hybrid'
    assert executive.select_mode({'ambiguity': 0.8, 'risk': 0.7, 'novelty': 0.85}) == 'exploratory'

    weights = executive.allocate_weights(
        'hybrid',
        history={'false_positive_rate': 0.8, 'drift_score': 0.45, 'avg_confidence': 0.9},
    )

    expected_keys = {
        'dmU_weight',
        'reasoning_weight',
        'imagination_weight',
        'validation_weight',
        'output_gate_weight',
        'executive_control_weight',
    }
    assert set(weights) == expected_keys
    assert math.isclose(sum(weights.values()), 1.0, abs_tol=1e-6)
    assert weights['validation_weight'] > weights['imagination_weight']


def test_imagine_core_prunes_low_confidence_and_keeps_oob_signal():
    imagine = ImagineCore(hallucination_budget=0.5, confidence_threshold=0.55)
    context = {
        'mode': 'hybrid',
        'novelty': 0.35,
        'signals': [
            {'type': 'oob_vuln', 'hypothesis': 'cross-contract storage collision'},
            'the function delegates to another contract and uses call',
            'ordinary status update with no interesting surface',
            {'summary': 'edge case around unchecked arithmetic'},
        ],
    }

    hypotheses = imagine.generate_hypotheses(context)

    assert hypotheses
    assert len(hypotheses) <= math.ceil(len(context['signals']) * 0.5)
    assert all(item['confidence'] >= 0.55 for item in hypotheses)
    assert hypotheses[0]['confidence'] >= hypotheses[-1]['confidence']
    assert any(item['type'] == 'oob_vuln' for item in hypotheses)


def test_reality_anchor_rejects_metadata_constraints_case_insensitively():
    anchor = RealityAnchor()

    approved = anchor.validate(
        {'type': 'speculative', 'flag': 'observed', 'source': 'analysis'},
        ['owner_only_path'],
    )
    rejected = anchor.validate(
        {'type': 'Owner_Only_Path', 'flag': 'observed', 'source': 'analysis'},
        ['owner_only_path'],
    )

    assert approved['approved'] is True
    assert rejected['approved'] is False
    assert rejected['violations'] == 1


def test_trinity_run_returns_validation_summary():
    trinity = Trinity(TrinityExecutive({}), ImagineCore(hallucination_budget=0.5, confidence_threshold=0.5), RealityAnchor())

    result = trinity.run(
        {
            'ambiguity': 0.05,
            'risk': 0.1,
            'novelty': 0.05,
            'signals': [
                {'type': 'oob_vuln', 'hypothesis': 'storage collision'},
                'ordinary note',
            ],
            'constraints': ['owner_only_path'],
        }
    )

    assert result['mode'] == 'grounded'
    assert result['hypotheses'] == []
    assert result['summary'] == {'generated': 0, 'validated': 0, 'rejected': 0}
    assert result['validation_results'] == []
