#!/usr/bin/env python3
"""Standalone comparison runner for DRIFT memory ranking strategies.

This script can run in two modes:

* `synthetic` - uses the local deterministic benchmark corpus already used by
  `scripts/dmu_retrieval_benchmark.py`.
* `chroma` - uses the optional ChromaDB hooks for a live memory store.

The output is intentionally paper-friendly: JSON, CSV, and per-case trace
bundles for DMU, guarded, and RRF methods.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = Path(__file__).resolve().parent
for candidate in (str(SCRIPTS_DIR), str(ROOT)):
    if candidate not in sys.path:
        sys.path.insert(0, candidate)

from drift.core.alternative_ranking_algorithms import get_ranker
from drift.core.dmu import DMURetriever, compute_contextual_salience
from drift.core.dmu_score_decomposition import serialize_traces

try:
    from memory_store_config import get_config, get_chroma_store
except Exception:  # pragma: no cover - optional convenience import
    get_config = None
    get_chroma_store = None

from dmu_retrieval_benchmark import (
    BenchmarkCase,
    EMBEDDER,
    FakeCollection,
    FakePSC,
    MemoryRow,
    build_dataset,
    candidate_from_row,
    cosine_similarity,
)

METHOD_ALIASES = {
    "guarded_dmu": "guarded",
    "guarded_weighted": "guarded",
}
ALL_METHODS = ("cosine", "recent", "dmu", "guarded", "rrf")


def _parse_methods(raw: str | None) -> tuple[str, ...]:
    if not raw or not raw.strip():
        return ALL_METHODS
    methods: list[str] = []
    for token in raw.split(","):
        name = METHOD_ALIASES.get(token.strip().lower(), token.strip().lower())
        if not name:
            continue
        if name not in ALL_METHODS:
            raise ValueError(f"Unknown method {token!r}. Choose from: {', '.join(ALL_METHODS)}")
        if name not in methods:
            methods.append(name)
    return tuple(methods) if methods else ALL_METHODS


def _case_value(case: Any, key: str, default: Any = None) -> Any:
    if isinstance(case, dict):
        return case.get(key, default)
    return getattr(case, key, default)


def load_dataset(dataset_path: str | Path) -> List[Dict[str, Any]]:
    path = Path(dataset_path).expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(f"Dataset file not found: {path}")
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        if "cases" in data and isinstance(data["cases"], list):
            return data["cases"]
        if "case_id" in data:
            return [data]
    raise ValueError("Unsupported dataset format. Expected a list of cases or {'cases': [...]}." )


def _load_chroma_hooks():
    from chromadb_integration_hooks import (  # local module, imported lazily
        ChromaMemoryStore,
        get_candidates_for_case,
        get_query_embedding,
        load_dataset as load_chroma_dataset,
    )

    return ChromaMemoryStore, get_candidates_for_case, get_query_embedding, load_chroma_dataset


def _candidate_lookup(candidates: Sequence[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    return {str(candidate.get("id")): candidate for candidate in candidates}


def _top_k_cosine(candidates: Sequence[Dict[str, Any]], query_embedding: Sequence[float], top_k: int) -> List[Dict[str, Any]]:
    scored = sorted(
        candidates,
        key=lambda cand: cosine_similarity(list(query_embedding), list(cand.get("embedding", []))),
        reverse=True,
    )
    return list(scored[:top_k])


def _top_k_recent(candidates: Sequence[Dict[str, Any]], top_k: int) -> List[Dict[str, Any]]:
    return sorted(candidates, key=lambda cand: float(cand.get("timestamp", 0.0)), reverse=True)[:top_k]


def _score_selection(selected: Sequence[Dict[str, Any]], gold_id: str) -> Dict[str, Any]:
    ids = [str(item.get("id")) for item in selected]
    context_chars = sum(len(str(item.get("document", ""))) for item in selected)
    return {
        "top1_correct": bool(ids[:1] == [str(gold_id)]),
        "contains_correct": str(gold_id) in ids,
        "context_chars": context_chars,
    }


def _resolve_gold_id(case: Any) -> str:
    for key in ("gold_memory_id", "correct_memory_id", "memory_id", "gold_id"):
        value = _case_value(case, key)
        if value:
            return str(value)
    raise KeyError("Case is missing a gold memory identifier.")


def _build_query_context(case: Any, query_embedding: Sequence[float], current_time: float) -> Dict[str, Any]:
    alert_dims = _case_value(case, "psc_alert_dims", ())
    return {
        "query_embedding": list(query_embedding),
        "current_time": current_time,
        "psc_alert_dims": set(alert_dims or ()),
    }


def _evaluate_case_synthetic(
    case: BenchmarkCase,
    rows: Sequence[MemoryRow],
    retriever: DMURetriever,
    guarded_ranker,
    rrf_ranker,
    trace_root: Path,
    run_stamp: str,
    top_k: int,
) -> Dict[str, Any]:
    rows_by_id = {row.id: row for row in rows}
    query_embedding = EMBEDDER.embed_query(case.query)
    current_cycle = 1000 + case.turn_index
    query_context = _build_query_context(case, query_embedding, current_cycle)

    started = time.perf_counter()
    cosine_sel = _top_k_cosine(
        [
            {
                "id": row.id,
                "document": row.document,
                "timestamp": row.metadata.get("timestamp", 0),
                "embedding": row.embedding,
            }
            for row in rows
        ],
        query_embedding,
        top_k,
    )
    cosine_ms = (time.perf_counter() - started) * 1000

    started = time.perf_counter()
    recent_sel = _top_k_recent(
        [
            {
                "id": row.id,
                "document": row.document,
                "timestamp": row.metadata.get("timestamp", 0),
                "embedding": row.embedding,
            }
            for row in rows
        ],
        top_k,
    )
    recent_ms = (time.perf_counter() - started) * 1000

    started = time.perf_counter()
    dmu_out = retriever.retrieve(
        query_embedding,
        top_k=top_k,
        n_candidates=50,
        current_cycle=current_cycle,
        explain=True,
    )
    dmu_ms = (time.perf_counter() - started) * 1000
    dmu_sel, dmu_traces = dmu_out

    candidates = [
        candidate_from_row(row, query_embedding, current_cycle, set(case.psc_alert_dims))
        for row in rows
    ]

    started = time.perf_counter()
    guarded_sel, guarded_traces = guarded_ranker.rank(
        candidates,
        query_context,
        query_embedding=query_embedding,
        top_k=top_k,
        return_decompositions=True,
    )
    guarded_ms = (time.perf_counter() - started) * 1000

    started = time.perf_counter()
    rrf_sel, rrf_traces = rrf_ranker.rank(
        candidates,
        query_context,
        top_k=top_k,
        return_decompositions=True,
    )
    rrf_ms = (time.perf_counter() - started) * 1000

    method_traces = {
        "dmu": dmu_traces,
        "guarded": guarded_traces,
        "rrf": rrf_traces,
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

    def _scores(selected: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
        ids = [str(item.get("id")) for item in selected]
        context_chars = sum(len(rows_by_id[item_id].document) for item_id in ids if item_id in rows_by_id)
        return {
            "top1_correct": ids[:1] == [case.correct_memory_id],
            "contains_correct": case.correct_memory_id in ids,
            "context_chars": context_chars,
        }

    return {
        "case_id": case.case_id,
        "session_id": case.session_id,
        "turn_index": case.turn_index,
        "category": case.category,
        "mode": case.mode,
        "query": case.query,
        "correct_memory_id": case.correct_memory_id,
        "expected_answer": case.expected_answer,
        "cosine": {**_scores(cosine_sel), "latency_ms": round(cosine_ms, 3)},
        "recent": {**_scores(recent_sel), "latency_ms": round(recent_ms, 3)},
        "dmu": {**_scores(dmu_sel), "latency_ms": round(dmu_ms, 3)},
        "guarded": {**_scores(guarded_sel), "latency_ms": round(guarded_ms, 3)},
        "rrf": {**_scores(rrf_sel), "latency_ms": round(rrf_ms, 3)},
    }


def _evaluate_case_chroma(
    case: Dict[str, Any],
    *,
    retriever: DMURetriever,
    guarded_ranker,
    rrf_ranker,
    trace_root: Path,
    run_stamp: str,
    top_k: int,
    candidate_limit: int,
    apply_metadata_filter: bool,
    get_candidates_for_case,
    get_query_embedding,
) -> Dict[str, Any]:
    query = case["query"]
    gold_id = _resolve_gold_id(case)
    case_id = str(_case_value(case, "case_id", "case-unknown"))
    category = str(_case_value(case, "category", "unknown"))
    mode = str(_case_value(case, "mode", "live"))
    current_time = float(_case_value(case, "current_time", time.time()))

    query_embedding = get_query_embedding(query)
    candidates = get_candidates_for_case(
        case,
        n_results=candidate_limit,
        apply_metadata_filter=apply_metadata_filter,
    )
    query_context = _build_query_context(case, query_embedding, current_time)

    started = time.perf_counter()
    cosine_sel = _top_k_cosine(candidates, query_embedding, top_k)
    cosine_ms = (time.perf_counter() - started) * 1000

    started = time.perf_counter()
    recent_sel = _top_k_recent(candidates, top_k)
    recent_ms = (time.perf_counter() - started) * 1000

    started = time.perf_counter()
    dmu_sel, dmu_traces = retriever.retrieve(
        query_embedding,
        top_k=top_k,
        n_candidates=candidate_limit,
        current_cycle=int(current_time),
        explain=True,
    )
    dmu_ms = (time.perf_counter() - started) * 1000

    started = time.perf_counter()
    guarded_sel, guarded_traces = guarded_ranker.rank(
        candidates,
        query_context,
        query_embedding=query_embedding,
        top_k=top_k,
        return_decompositions=True,
    )
    guarded_ms = (time.perf_counter() - started) * 1000

    started = time.perf_counter()
    rrf_sel, rrf_traces = rrf_ranker.rank(
        candidates,
        query_context,
        top_k=top_k,
        return_decompositions=True,
    )
    rrf_ms = (time.perf_counter() - started) * 1000

    for method, traces in {
        "dmu": dmu_traces,
        "guarded": guarded_traces,
        "rrf": rrf_traces,
    }.items():
        if traces:
            serialize_traces(
                traces,
                case_id=case_id,
                output_dir=trace_root / method,
                timestamp=run_stamp,
                method=method,
            )

    return {
        "case_id": case_id,
        "session_id": str(_case_value(case, "session_id", "")),
        "turn_index": int(_case_value(case, "turn_index", 0) or 0),
        "category": category,
        "mode": mode,
        "query": query,
        "correct_memory_id": gold_id,
        "expected_answer": _case_value(case, "expected_answer", ""),
        "cosine": {**_score_selection(cosine_sel, gold_id), "latency_ms": round(cosine_ms, 3)},
        "recent": {**_score_selection(recent_sel, gold_id), "latency_ms": round(recent_ms, 3)},
        "dmu": {**_score_selection(dmu_sel, gold_id), "latency_ms": round(dmu_ms, 3)},
        "guarded": {**_score_selection(guarded_sel, gold_id), "latency_ms": round(guarded_ms, 3)},
        "rrf": {**_score_selection(rrf_sel, gold_id), "latency_ms": round(rrf_ms, 3)},
    }


def _summarize(results: Sequence[Dict[str, Any]], methods: Sequence[str], dataset_label: str) -> Dict[str, Any]:
    summary = {
        "cases": len(results),
        "methods": {},
        "dataset_version": dataset_label,
    }
    for method in methods:
        top1 = sum(1 for row in results if row[method]["top1_correct"])
        recall = sum(1 for row in results if row[method]["contains_correct"])
        summary["methods"][method] = {
            "top1_accuracy": round(top1 / len(results), 4) if results else 0.0,
            "contains_recall": round(recall / len(results), 4) if results else 0.0,
            "avg_context_chars": round(statistics.mean(row[method]["context_chars"] for row in results), 2) if results else 0.0,
            "avg_latency_ms": round(statistics.mean(row[method]["latency_ms"] for row in results), 3) if results else 0.0,
        }

    if "dmu" in summary["methods"] and "cosine" in summary["methods"]:
        summary["dmu_vs_cosine_context_delta_chars"] = round(
            summary["methods"]["dmu"]["avg_context_chars"] - summary["methods"]["cosine"]["avg_context_chars"],
            2,
        )
        summary["dmu_vs_cosine_context_delta_pct"] = round(
            (summary["dmu_vs_cosine_context_delta_chars"] / summary["methods"]["cosine"]["avg_context_chars"] * 100)
            if summary["methods"]["cosine"]["avg_context_chars"]
            else 0.0,
            2,
        )
    return summary


def _write_outputs(
    results: Sequence[Dict[str, Any]],
    summary: Dict[str, Any],
    output_dir: Path,
    methods: Sequence[str] = ALL_METHODS,
) -> Tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    json_path = output_dir / f"standalone_dmu_comparison_results_{stamp}.json"
    csv_path = output_dir / f"standalone_dmu_comparison_results_{stamp}.csv"
    json_path.write_text(json.dumps({"summary": summary, "results": list(results)}, indent=2), encoding="utf-8")
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "case_id",
            "session_id",
            "turn_index",
            "category",
            "mode",
            "method",
            "top1_correct",
            "contains_correct",
            "context_chars",
            "latency_ms",
        ])
        for row in results:
            for method in methods:
                if method not in row:
                    continue
                writer.writerow([
                    row["case_id"],
                    row["session_id"],
                    row["turn_index"],
                    row["category"],
                    row["mode"],
                    method,
                    int(row[method]["top1_correct"]),
                    int(row[method]["contains_correct"]),
                    row[method]["context_chars"],
                    row[method]["latency_ms"],
                ])
    return json_path, csv_path


def _print_summary(summary: Dict[str, Any]) -> None:
    print("\n" + "=" * 80)
    print("STANDALONE DMU COMPARISON SUMMARY")
    print("=" * 80)
    print(f"{'Method':<14} {'Top-1 Acc':>10} {'Recall@K':>10} {'Avg Latency (ms)':>18} {'Runs':>8}")
    print("-" * 80)
    for method in sorted(summary["methods"].keys()):
        stats = summary["methods"][method]
        print(
            f"{method:<14} "
            f"{stats['top1_accuracy']:>10.2%} "
            f"{stats['contains_recall']:>10.2%} "
            f"{stats['avg_latency_ms']:>18.3f} "
            f"{summary['cases']:>8}"
        )
    print("=" * 80)


def run_synthetic(
    cases: int,
    dataset_version: str,
    top_k: int,
    output_dir: Path,
    methods: Sequence[str] = ALL_METHODS,
) -> int:
    synthetic_cases, memories = build_dataset(cases, dataset_version=dataset_version)
    trace_root = output_dir / "score_traces" / dataset_version
    run_stamp = time.strftime("%Y%m%d_%H%M%S")

    retriever = DMURetriever(
        FakeCollection(memories, EMBEDDER),
        psc_engine=FakePSC(synthetic_cases[0].psc_alert_dims if synthetic_cases else ()),
        max_retrieval_count=10,
    )
    guarded_ranker = get_ranker("guarded", guardrail_threshold=0.08, semantic_weight=0.70)
    rrf_ranker = get_ranker("rrf")

    results: List[Dict[str, Any]] = []
    for case in synthetic_cases:
        results.append(
            _evaluate_case_synthetic(
                case,
                memories,
                retriever,
                guarded_ranker,
                rrf_ranker,
                trace_root,
                run_stamp,
                top_k,
            )
        )

    summary = _summarize(results, methods, dataset_version)
    json_path, csv_path = _write_outputs(results, summary, output_dir, methods=methods)
    _print_summary(summary)
    print(f"Wrote {json_path}")
    print(f"Wrote {csv_path}")
    print(f"Wrote trace bundles under {trace_root}")
    return 0


def _apply_chroma_env(persist_dir: str, collection_name: str, embedding_model: str) -> None:
    os.environ["DRIFT_CHROMA_PERSIST_DIR"] = persist_dir
    os.environ["DRIFT_MEMORY_COLLECTION"] = collection_name
    os.environ["DRIFT_EMBEDDING_MODEL"] = embedding_model
    if get_chroma_store is not None:
        from memory_store_config import reset_chroma_store

        reset_chroma_store()


def run_chroma(
    dataset_path: Path,
    *,
    top_k: int,
    candidate_limit: int,
    output_dir: Path,
    apply_metadata_filter: bool,
    methods: Sequence[str] = ALL_METHODS,
) -> int:
    _, get_candidates_for_case, get_query_embedding, load_chroma_dataset = _load_chroma_hooks()
    cases = load_chroma_dataset(dataset_path)
    if get_chroma_store is None:
        raise SystemExit("Chroma backend requires memory_store_config and chromadb_integration_hooks.")
    store = get_chroma_store()
    retriever = DMURetriever(store.collection, psc_engine=None, max_retrieval_count=10)
    guarded_ranker = get_ranker("guarded", guardrail_threshold=0.08, semantic_weight=0.70)
    rrf_ranker = get_ranker("rrf")
    trace_root = output_dir / "score_traces" / "chroma"
    run_stamp = time.strftime("%Y%m%d_%H%M%S")

    results: List[Dict[str, Any]] = []
    for case in cases:
        where_filter: Optional[Dict[str, Any]] = None
        if apply_metadata_filter and case.get("category"):
            where_filter = {"category": {"$eq": case["category"]}}

        chroma_results = store.query(
            query_text=case["query"],
            n_results=candidate_limit,
            where=where_filter,
            include=["documents", "metadatas", "embeddings", "distances"],
        )
        candidates: List[Dict[str, Any]] = []
        ids = chroma_results.get("ids", [[]])[0]
        documents = chroma_results.get("documents", [[]])[0]
        metadatas = chroma_results.get("metadatas", [[]])[0]
        embeddings = chroma_results.get("embeddings", [[]])[0]
        for idx, mem_id in enumerate(ids):
            meta = metadatas[idx] if idx < len(metadatas) and metadatas else {}
            emb = embeddings[idx] if idx < len(embeddings) and embeddings else []
            candidates.append(
                {
                    "id": mem_id,
                    "memory_id": meta.get("memory_id", mem_id),
                    "embedding": emb,
                    "document": documents[idx] if idx < len(documents) else "",
                    "timestamp": float(meta.get("timestamp", 0.0)),
                    "salience": float(meta.get("salience", 0.5)),
                    "emotional_valence": float(meta.get("emotional_valence", 0.0)),
                    "emotional_intensity": float(meta.get("emotional_intensity", 0.5)),
                    "retention_score": float(meta.get("retention_score", meta.get("retention_decay", 0.8))),
                    "trust_level": float(meta.get("trust_level", 0.75)),
                    "has_conflict": bool(meta.get("has_conflict", False)),
                    "conflict_status": meta.get("conflict_status", "none"),
                    **{
                        k: v
                        for k, v in meta.items()
                        if k
                        not in {
                            "memory_id",
                            "timestamp",
                            "salience",
                            "emotional_valence",
                            "emotional_intensity",
                            "retention_score",
                            "retention_decay",
                            "trust_level",
                            "has_conflict",
                            "conflict_status",
                        }
                    },
                }
            )

        query_embedding = store.embedding_function([case["query"]])[0]
        if hasattr(query_embedding, "tolist"):
            query_embedding = query_embedding.tolist()
        query_context = _build_query_context(case, query_embedding, float(_case_value(case, "current_time", time.time())))

        started = time.perf_counter()
        cosine_sel = _top_k_cosine(candidates, query_embedding, top_k)
        cosine_ms = (time.perf_counter() - started) * 1000

        started = time.perf_counter()
        recent_sel = _top_k_recent(candidates, top_k)
        recent_ms = (time.perf_counter() - started) * 1000

        started = time.perf_counter()
        dmu_sel, dmu_traces = retriever.retrieve(
            query_embedding,
            top_k=top_k,
            n_candidates=candidate_limit,
            current_cycle=int(_case_value(case, "current_time", time.time())),
            explain=True,
        )
        dmu_ms = (time.perf_counter() - started) * 1000

        started = time.perf_counter()
        guarded_sel, guarded_traces = guarded_ranker.rank(
            candidates,
            query_context,
            query_embedding=query_embedding,
            top_k=top_k,
            return_decompositions=True,
        )
        guarded_ms = (time.perf_counter() - started) * 1000

        started = time.perf_counter()
        rrf_sel, rrf_traces = rrf_ranker.rank(
            candidates,
            query_context,
            top_k=top_k,
            return_decompositions=True,
        )
        rrf_ms = (time.perf_counter() - started) * 1000

        for method, traces in {
            "dmu": dmu_traces,
            "guarded": guarded_traces,
            "rrf": rrf_traces,
        }.items():
            if traces:
                serialize_traces(
                    traces,
                    case_id=str(_case_value(case, "case_id", "case-unknown")),
                    output_dir=trace_root / method,
                    timestamp=run_stamp,
                    method=method,
                )

        def _scores(selected: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
            ids = [str(item.get("id")) for item in selected]
            context_chars = sum(len(item.get("document", "")) for item in selected)
            return {
                "top1_correct": ids[:1] == [str(_resolve_gold_id(case))],
                "contains_correct": str(_resolve_gold_id(case)) in ids,
                "context_chars": context_chars,
            }

        results.append(
            {
                "case_id": str(_case_value(case, "case_id", "case-unknown")),
                "session_id": str(_case_value(case, "session_id", "")),
                "turn_index": int(_case_value(case, "turn_index", 0) or 0),
                "category": str(_case_value(case, "category", "unknown")),
                "mode": str(_case_value(case, "mode", "live")),
                "query": case["query"],
                "correct_memory_id": _resolve_gold_id(case),
                "expected_answer": _case_value(case, "expected_answer", ""),
                "cosine": {**_scores(cosine_sel), "latency_ms": round(cosine_ms, 3)},
                "recent": {**_scores(recent_sel), "latency_ms": round(recent_ms, 3)},
                "dmu": {**_scores(dmu_sel), "latency_ms": round(dmu_ms, 3)},
                "guarded": {**_scores(guarded_sel), "latency_ms": round(guarded_ms, 3)},
                "rrf": {**_scores(rrf_sel), "latency_ms": round(rrf_ms, 3)},
            }
        )

    summary = _summarize(results, methods, "chroma")
    json_path, csv_path = _write_outputs(results, summary, output_dir, methods=methods)
    _print_summary(summary)
    print(f"Wrote {json_path}")
    print(f"Wrote {csv_path}")
    print(f"Wrote trace bundles under {trace_root}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Standalone DRIFT memory ranking comparison runner.")
    parser.add_argument("--backend", "--mode", choices=("synthetic", "chroma"), default="synthetic")
    parser.add_argument("--cases", type=int, default=100)
    parser.add_argument("--dataset-version", choices=("v1_label_leakage", "v2_opaque_labels"), default="v2_opaque_labels")
    parser.add_argument("--dataset", type=Path, default=None)
    parser.add_argument("--top-k", "--k", dest="top_k", type=int, default=3)
    parser.add_argument("--candidate-limit", type=int, default=None)
    parser.add_argument(
        "--methods",
        default="",
        help="Comma-separated rankers to score (default: all). Aliases: guarded_dmu -> guarded",
    )
    parser.add_argument("--output-dir", type=Path, default=ROOT / "benchmarks" / "comparison_runs")
    default_cfg = get_config() if get_config is not None else None
    parser.add_argument(
        "--chroma-persist-dir",
        default=(default_cfg.persist_directory if default_cfg else "./chroma_db"),
    )
    parser.add_argument(
        "--chroma-collection-name",
        default=(default_cfg.collection_name if default_cfg else "drift_memory"),
    )
    parser.add_argument(
        "--chroma-embedding-model",
        default=(default_cfg.embedding_model if default_cfg else "all-MiniLM-L6-v2"),
    )
    parser.add_argument("--no-metadata-filter", action="store_true")

    args = parser.parse_args()
    try:
        methods = _parse_methods(args.methods)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc

    candidate_limit = args.candidate_limit
    if candidate_limit is None:
        candidate_limit = default_cfg.default_n_results if default_cfg else 50

    if args.backend == "synthetic":
        return run_synthetic(args.cases, args.dataset_version, args.top_k, args.output_dir, methods=methods)

    if args.dataset is None:
        raise SystemExit("--dataset is required when --backend chroma is selected.")

    _apply_chroma_env(
        args.chroma_persist_dir,
        args.chroma_collection_name,
        args.chroma_embedding_model,
    )

    return run_chroma(
        args.dataset,
        top_k=args.top_k,
        candidate_limit=candidate_limit,
        output_dir=args.output_dir,
        apply_metadata_filter=not args.no_metadata_filter,
        methods=methods,
    )


if __name__ == "__main__":
    raise SystemExit(main())
