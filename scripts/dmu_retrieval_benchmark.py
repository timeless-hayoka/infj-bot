#!/usr/bin/env python3
"""Deterministic benchmark for DRIFT memory ranking quality.

Compares cosine-only retrieval, recent-memory retrieval, the current DMU
retriever, and the new guarded / RRF alternatives across a synthetic labeled
corpus. The benchmark keeps an auditable trace bundle for each ranker so the
paper can describe both the aggregate scores and the candidate-level reasons.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
import statistics
import sys
import time
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from drift.core.alternative_ranking_algorithms import get_ranker
from drift.core.dmu import DMURetriever, compute_contextual_salience
from drift.core.dmu_score_decomposition import serialize_traces


@dataclass(frozen=True)
class BenchmarkCase:
    case_id: str
    session_id: str
    turn_index: int
    category: str
    mode: str
    query: str
    correct_memory_id: str
    expected_answer: str
    psc_alert_dims: tuple[str, ...]


@dataclass
class MemoryRow:
    id: str
    document: str
    metadata: dict
    embedding: list[float]


class FakeCollection:
    def __init__(self, rows: list[MemoryRow], embedding_fn):
        self.rows = rows
        self.embedding_fn = embedding_fn

    def query(self, query_embeddings, n_results=10, include=None):
        query_embedding = query_embeddings[0]
        scored = []
        for row in self.rows:
            sim = cosine_similarity(query_embedding, row.embedding)
            dist = max(0.0, 1.0 - sim)
            scored.append((sim, row, dist))
        scored.sort(key=lambda item: item[0], reverse=True)
        top = scored[:n_results]
        return {
            'ids': [[row.id for _, row, _ in top]],
            'documents': [[row.document for _, row, _ in top]],
            'metadatas': [[row.metadata for _, row, _ in top]],
            'distances': [[dist for _, _, dist in top]],
        }


class FakePSCResult:
    def __init__(self, dims: Iterable[str]):
        dims = list(dims)
        self.dimensions = dims
        self.predicted = [0.8 if d in dims else 0.2 for d in dims]
        self.alerted = [True for _ in dims]


class FakePSC:
    def __init__(self, dims: Iterable[str]):
        self._dims = tuple(dims)

    def run(self):
        if not self._dims:
            return None
        return FakePSCResult(self._dims)


class BagOfWordsEmbeddingFunction:
    def __init__(self) -> None:
        self._vocab: list[str] = []
        self._index: dict[str, int] = {}

    def fit(self, texts: Iterable[str]) -> None:
        vocab = sorted({token for text in texts for token in self._tokenize(text)})
        self._vocab = vocab
        self._index = {token: i for i, token in enumerate(vocab)}

    def embed_query(self, input: str | None = None) -> list[float]:
        if input is None:
            raise TypeError('embed_query requires a text input')
        if not self._vocab:
            raise RuntimeError('embedding vocabulary has not been fit yet')
        counts = Counter(self._tokenize(input))
        vec = [0.0] * len(self._vocab)
        for token, count in counts.items():
            idx = self._index.get(token)
            if idx is not None:
                vec[idx] = float(count)
        mag = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / mag for v in vec]

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        return re.findall(r'[a-z0-9]+', text.lower())


EMBEDDER = BagOfWordsEmbeddingFunction()


def cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    mag_a = math.sqrt(sum(x * x for x in a))
    mag_b = math.sqrt(sum(y * y for y in b))
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)


def recent_memory_order(rows: list[MemoryRow]) -> list[MemoryRow]:
    return sorted(rows, key=lambda row: row.metadata.get('cycle', 0), reverse=True)


def _session_queries(session_token: str, category: str, mode: str, clue: str) -> list[str]:
    if mode == 'lexical':
        return [
            f'{session_token}: which memory holds the canonical {category} fact for {clue}?',
            f'{session_token}: confirm the canonical fact for {clue} in the {category} notes.',
            f'{session_token}: what is the correct {category} fact for {clue}?',
            f'{session_token}: anchor the canonical {category} fact for {clue}.',
        ]

    return [
        f'{session_token}: which note should anchor keep after the reset for this {category} scenario?',
        f'{session_token}: after the reset, which memory should stay active for this {category} scenario?',
        f'{session_token}: for the {category} scenario, which memory best matches the projected state?',
        f'{session_token}: which memory should remain canonical for this {category} continuity check?',
    ]


def _answer_pair(session_idx: int, dataset_version: str, category: str) -> tuple[str, str]:
    if dataset_version == 'v1_label_leakage':
        return f'{category.upper()}_{session_idx:03d}', f'WRONG_{session_idx:03d}'

    gold_answers = ['ALPHA', 'BETA', 'GAMMA', 'DELTA', 'EPSILON', 'ZETA', 'THETA', 'KAPPA']
    trap_answers = ['OMEGA', 'SIGMA', 'TAU', 'PHI', 'CHI', 'PSI', 'XI', 'RHO']
    return (
        gold_answers[(session_idx - 1) % len(gold_answers)],
        trap_answers[(session_idx - 1) % len(trap_answers)],
    )


def build_dataset(total_cases: int = 100, dataset_version: str = 'v2_opaque_labels') -> tuple[list[BenchmarkCase], list[MemoryRow]]:
    categories = [
        ('memory', 'project memory and continuity'),
        ('continuity', 'long conversation continuity'),
        ('conflict', 'conflicting memory resolution'),
        ('injection', 'prompt injection resilience'),
    ]
    cases: list[BenchmarkCase] = []
    memory_specs: list[tuple[str, str, dict]] = []
    fit_texts: list[str] = []
    session_idx = 0
    case_counter = 0
    turns_per_session = 4
    session_count = max(1, math.ceil(total_cases / turns_per_session))

    for _ in range(session_count):
        if case_counter >= total_cases:
            break

        session_idx += 1
        category, label = categories[(session_idx - 1) % len(categories)]
        mode = 'lexical' if session_idx % 2 else 'metadata'
        session_token = f'session-{session_idx:03d}-{category}'
        answer, trap_answer = _answer_pair(session_idx, dataset_version, category)
        correct_id = f'{session_token}-gold'
        trap_id = f'{session_token}-trap'
        clue = f'clue-{session_idx:03d}'
        psc_dims = (category, 'memory') if mode == 'lexical' else (category, 'continuity')
        turn_queries = _session_queries(session_token, category, mode, clue)
        base_cycle = 1000 - (session_idx * 20)

        if mode == 'lexical':
            shared_phrase = f'{session_token} canonical {category} anchor note for {clue}.'
            gold_doc = f'{shared_phrase} Canonical answer is {answer}.'
            trap_doc = f'{session_token} canonical {category} anchor note for decoy. Canonical answer is {trap_answer}.'
            gold_tags = [category, 'lexical', 'canonical']
            trap_tags = ['distractor', 'noise']
        else:
            shared_phrase = f'{session_token} anchor keep after reset for this {category} scenario.'
            gold_doc = f'{shared_phrase} Canonical answer is {answer}.'
            trap_doc = f'{shared_phrase} Canonical answer is {trap_answer}.'
            gold_tags = [category, 'continuity', 'canonical']
            trap_tags = ['distractor', 'noise']

        memory_specs.append((trap_id, trap_doc, {
            'cycle': base_cycle,
            'category': 'distractor',
            'tags': trap_tags,
            'formed_state': {dim: 0.12 for dim in psc_dims},
            'timestamp': base_cycle,
            'reinforcement_score': 0.05,
            'novelty_score': 0.1,
            'provenance': 'bot_inference',
            'source_reliability': 0.4,
        }))
        memory_specs.append((correct_id, gold_doc, {
            'cycle': base_cycle,
            'category': category,
            'tags': gold_tags,
            'formed_state': {dim: 0.92 for dim in psc_dims},
            'timestamp': base_cycle,
            'reinforcement_score': 0.8,
            'novelty_score': 0.4,
            'provenance': 'user_explicit',
            'source_reliability': 1.0,
        }))

        for j in range(2):
            extra_doc = f'{session_token} distractor {j}: unrelated detail about {label} and a noisy note.'
            memory_specs.append((f'{session_token}-noise-{j}', extra_doc, {
                'cycle': base_cycle - 1 - j,
                'category': 'untagged' if j else category,
                'tags': ['distractor', category] if j == 0 else ['distractor'],
                'formed_state': {dim: 0.2 for dim in psc_dims},
                'timestamp': base_cycle - 1 - j,
                'reinforcement_score': 0.1 + (j * 0.05),
                'novelty_score': 0.1,
                'provenance': 'bot_inference',
                'source_reliability': 0.5,
            }))

        fit_texts.extend(turn_queries)
        fit_texts.extend([trap_doc, gold_doc])
        fit_texts.extend(spec[1] for spec in memory_specs[-2:])

        for turn_index, query in enumerate(turn_queries, start=1):
            if case_counter >= total_cases:
                break
            case_counter += 1
            cases.append(BenchmarkCase(
                case_id=f'case-{case_counter:03d}',
                session_id=session_token,
                turn_index=turn_index,
                category=category,
                mode=mode,
                query=query,
                correct_memory_id=correct_id,
                expected_answer=answer,
                psc_alert_dims=psc_dims,
            ))

    EMBEDDER.fit(fit_texts)
    memories = [MemoryRow(id=mem_id, document=doc, metadata=meta, embedding=EMBEDDER.embed_query(doc)) for mem_id, doc, meta in memory_specs]
    return cases[:total_cases], memories


def select_cosine(query: str, rows: list[MemoryRow], top_k: int = 3) -> list[MemoryRow]:
    emb = EMBEDDER.embed_query(query)
    ranked = sorted(rows, key=lambda row: cosine_similarity(emb, row.embedding), reverse=True)
    return ranked[:top_k]


def select_recent(rows: list[MemoryRow], top_k: int = 3) -> list[MemoryRow]:
    return recent_memory_order(rows)[:top_k]


def candidate_from_row(row: MemoryRow, query_embedding: list[float], current_time: int, alert_dims: set[str]) -> dict:
    memory_dict = {
        'id': row.id,
        'document': row.document,
        'metadata': row.metadata,
        'tags': row.metadata.get('tags', []),
        'formed_state': row.metadata.get('formed_state', {}),
    }
    salience = compute_contextual_salience(memory_dict, {dim: 0.8 for dim in alert_dims}, alert_dims)
    return {
        'id': row.id,
        'embedding': row.embedding,
        'query_embedding': query_embedding,
        'timestamp': row.metadata.get('timestamp', 0),
        'salience': salience,
        'retention_score': float(row.metadata.get('reinforcement_score', 0.5)),
        'emotional_valence': float(row.metadata.get('novelty_score', 0.0)),
        'state_match': salience,
        'trust_level': float(row.metadata.get('source_reliability', 0.5)),
        'has_conflict': row.metadata.get('category') == 'distractor',
        'conflict_status': 'unresolved' if row.metadata.get('category') == 'distractor' else 'resolved',
        'category': row.metadata.get('category', 'untagged'),
        'source_reliability': float(row.metadata.get('source_reliability', 0.5)),
        'memory_metadata': row.metadata,
    }


def score_selection(selected: list[MemoryRow] | list[dict], case: BenchmarkCase, rows_by_id: dict[str, MemoryRow]) -> dict:
    if selected and isinstance(selected[0], dict):
        ids = [item['id'] for item in selected]
        context_chars = sum(len(rows_by_id[item['id']].document) for item in selected if item['id'] in rows_by_id)
    else:
        ids = [row.id for row in selected]  # type: ignore[union-attr]
        context_chars = sum(len(row.document) for row in selected)  # type: ignore[arg-type]
    return {
        'top1_correct': ids[:1] == [case.correct_memory_id],
        'contains_correct': case.correct_memory_id in ids,
        'context_chars': context_chars,
    }


def evaluate_case(
    case: BenchmarkCase,
    rows: list[MemoryRow],
    retriever: DMURetriever,
    guarded_ranker,
    rrf_ranker,
    trace_root: Path,
    run_stamp: str,
) -> dict:
    rows_by_id = {row.id: row for row in rows}
    query_embedding = EMBEDDER.embed_query(case.query)
    current_cycle = 1000 + case.turn_index
    query_context = {
        'query_embedding': query_embedding,
        'current_time': current_cycle,
        'psc_alert_dims': set(case.psc_alert_dims),
    }

    starts = time.perf_counter()
    cosine_sel = select_cosine(case.query, rows)
    cosine_ms = (time.perf_counter() - starts) * 1000

    starts = time.perf_counter()
    recent_sel = select_recent(rows)
    recent_ms = (time.perf_counter() - starts) * 1000

    starts = time.perf_counter()
    dmu_out = retriever.retrieve(query_embedding, top_k=3, n_candidates=50, current_cycle=current_cycle, explain=True)
    dmu_ms = (time.perf_counter() - starts) * 1000
    dmu_sel, dmu_traces = dmu_out

    candidates = [candidate_from_row(row, query_embedding, current_cycle, set(case.psc_alert_dims)) for row in rows]

    starts = time.perf_counter()
    guarded_sel, guarded_traces = guarded_ranker.rank(
        candidates,
        query_context,
        query_embedding=query_embedding,
        top_k=3,
        return_decompositions=True,
    )
    guarded_ms = (time.perf_counter() - starts) * 1000

    starts = time.perf_counter()
    rrf_sel, rrf_traces = rrf_ranker.rank(
        candidates,
        query_context,
        top_k=3,
        return_decompositions=True,
    )
    rrf_ms = (time.perf_counter() - starts) * 1000

    method_traces = {
        'dmu': dmu_traces,
        'guarded': guarded_traces,
        'rrf': rrf_traces,
    }
    for method, traces in method_traces.items():
        if traces:
            serialize_traces(
                traces,
                case_id=case.case_id,
                output_dir=trace_root / method,
                timestamp=run_stamp,
                method=method,
            )

    def method_scores(selected):
        return score_selection(selected, case, rows_by_id)

    return {
        'case_id': case.case_id,
        'session_id': case.session_id,
        'turn_index': case.turn_index,
        'category': case.category,
        'mode': case.mode,
        'query': case.query,
        'correct_memory_id': case.correct_memory_id,
        'expected_answer': case.expected_answer,
        'cosine': {**method_scores(cosine_sel), 'latency_ms': round(cosine_ms, 3)},
        'recent': {**method_scores(recent_sel), 'latency_ms': round(recent_ms, 3)},
        'dmu': {**method_scores(dmu_sel), 'latency_ms': round(dmu_ms, 3)},
        'guarded': {**method_scores(guarded_sel), 'latency_ms': round(guarded_ms, 3)},
        'rrf': {**method_scores(rrf_sel), 'latency_ms': round(rrf_ms, 3)},
    }


def summarize(results: list[dict], dataset_version: str) -> dict:
    summary = {
        'cases': len(results),
        'methods': {},
        'modes': sorted({row['mode'] for row in results}),
        'dataset_version': dataset_version,
    }
    for method in ('cosine', 'recent', 'dmu', 'guarded', 'rrf'):
        top1 = sum(1 for row in results if row[method]['top1_correct'])
        recall = sum(1 for row in results if row[method]['contains_correct'])
        summary['methods'][method] = {
            'top1_accuracy': round(top1 / len(results), 4) if results else 0.0,
            'contains_recall': round(recall / len(results), 4) if results else 0.0,
            'avg_context_chars': round(statistics.mean(row[method]['context_chars'] for row in results), 2) if results else 0.0,
            'avg_latency_ms': round(statistics.mean(row[method]['latency_ms'] for row in results), 3) if results else 0.0,
        }
    summary['dmu_vs_cosine_context_delta_chars'] = round(
        summary['methods']['dmu']['avg_context_chars'] - summary['methods']['cosine']['avg_context_chars'],
        2,
    )
    summary['dmu_vs_cosine_context_delta_pct'] = round(
        (summary['dmu_vs_cosine_context_delta_chars'] / summary['methods']['cosine']['avg_context_chars'] * 100)
        if summary['methods']['cosine']['avg_context_chars'] else 0.0,
        2,
    )
    return summary


def write_outputs(results: list[dict], summary: dict, output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime('%Y%m%d_%H%M%S')
    json_path = output_dir / f'dmu_retrieval_results_{stamp}.json'
    csv_path = output_dir / f'dmu_retrieval_results_{stamp}.csv'
    json_path.write_text(json.dumps({'summary': summary, 'results': results}, indent=2), encoding='utf-8')
    with csv_path.open('w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow([
            'case_id', 'session_id', 'turn_index', 'category', 'mode', 'method',
            'top1_correct', 'contains_correct', 'context_chars', 'latency_ms'
        ])
        for row in results:
            for method in ('cosine', 'recent', 'dmu', 'guarded', 'rrf'):
                writer.writerow([
                    row['case_id'], row['session_id'], row['turn_index'], row['category'], row['mode'], method,
                    int(row[method]['top1_correct']), int(row[method]['contains_correct']),
                    row[method]['context_chars'], row[method]['latency_ms'],
                ])
    return json_path, csv_path


def main() -> int:
    parser = argparse.ArgumentParser(description='Run the DRIFT memory ranking benchmark.')
    parser.add_argument('--cases', type=int, default=100)
    parser.add_argument('--dataset-version', choices=('v1_label_leakage', 'v2_opaque_labels'), default='v2_opaque_labels')
    parser.add_argument('--output-dir', type=Path, default=Path('/home/crexs/infj_bot/.benchmarks/dmu'))
    parser.add_argument('--trace-root', type=Path, default=None)
    args = parser.parse_args()

    cases, memories = build_dataset(args.cases, dataset_version=args.dataset_version)
    trace_root = args.trace_root or (args.output_dir / 'score_traces' / args.dataset_version)
    run_stamp = time.strftime('%Y%m%d_%H%M%S')

    retriever = DMURetriever(FakeCollection(memories, EMBEDDER), psc_engine=FakePSC(cases[0].psc_alert_dims), max_retrieval_count=10)
    guarded_ranker = get_ranker('guarded', guardrail_threshold=0.08, semantic_weight=0.70)
    rrf_ranker = get_ranker('rrf')

    sessions: dict[str, list[BenchmarkCase]] = {}
    for case in cases:
        sessions.setdefault(case.session_id, []).append(case)

    results: list[dict] = []
    for session_cases in sessions.values():
        for case in session_cases:
            results.append(evaluate_case(case, memories, retriever, guarded_ranker, rrf_ranker, trace_root, run_stamp))

    summary = summarize(results, args.dataset_version)
    json_path, csv_path = write_outputs(results, summary, args.output_dir)

    print(json.dumps(summary, indent=2))
    print(f'Wrote {json_path}')
    print(f'Wrote {csv_path}')
    print(f'Wrote trace bundles under {trace_root}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
