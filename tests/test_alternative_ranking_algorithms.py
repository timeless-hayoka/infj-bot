from __future__ import annotations

from drift.core.alternative_ranking_algorithms import GuardedWeightedRanker, get_ranker


def test_guarded_weighted_ranker_prefers_semantic_match() -> None:
    ranker = GuardedWeightedRanker(guardrail_threshold=0.05)
    query_context = {'query_embedding': [1.0, 0.0, 0.0], 'current_time': 0}
    candidates = [
        {'id': 'gold', 'embedding': [1.0, 0.0, 0.0], 'timestamp': 10, 'salience': 0.2, 'trust_level': 0.9},
        {'id': 'distractor', 'embedding': [0.2, 0.9, 0.0], 'timestamp': 20, 'salience': 0.9, 'trust_level': 0.7},
    ]

    ranked, decomps = ranker.rank(candidates, query_context, query_embedding=[1.0, 0.0, 0.0], top_k=2)

    assert ranked[0]['id'] == 'gold'
    assert decomps[0].candidate_id == 'gold'
    assert any(d.semantic_rank == 1 for d in decomps)


def test_ranker_factory_returns_known_ranker() -> None:
    ranker = get_ranker('guarded')
    assert isinstance(ranker, GuardedWeightedRanker)
