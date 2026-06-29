"""Hyperparameter tuning helpers for semantic SARIF clustering."""

from __future__ import annotations

import itertools
from typing import Any

from drift.trinity.sarif_models import SarifFinding
from drift.trinity.sarif_pipeline.semantic_clusterer import ClusterResult, SemanticClusterer, semantic_clustering_available


class ClusterHyperparameterTuner:
    def __init__(self, clusterer: SemanticClusterer) -> None:
        if not semantic_clustering_available():
            raise RuntimeError("ClusterHyperparameterTuner requires semantic clustering dependencies")
        self.clusterer = clusterer

    def tune(
        self,
        findings: list[SarifFinding],
        param_grid: dict[str, list[Any]] | None = None,
    ) -> dict[str, Any]:
        try:
            from sklearn.metrics import silhouette_score
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("scikit-learn is required for ClusterHyperparameterTuner") from exc

        if param_grid is None:
            param_grid = {
                "umap_n_neighbors": [10, 15, 25],
                "hdbscan_min_cluster_size": [2, 3, 5],
                "hdbscan_min_samples": [1, 2],
            }

        best_score = -1.0
        best_params: dict[str, Any] = {}
        results: list[dict[str, Any]] = []

        for params in itertools.product(*param_grid.values()):
            param_dict = dict(zip(param_grid.keys(), params))
            for key, value in param_dict.items():
                setattr(self.clusterer, key, value)

            cluster_result = self.clusterer.cluster(findings, return_cluster_summaries=False)
            labels = cluster_result.cluster_labels
            label_set = set(int(label) for label in labels)

            score = -1.0
            if len(label_set) > 1 and label_set != {-1}:
                embeddings = self.clusterer.generate_embeddings(
                    [self.clusterer._embedding_text(f) for f in findings]
                )
                try:
                    score = float(silhouette_score(embeddings, labels))
                except Exception:
                    score = -1.0

            row = {
                "params": param_dict,
                "score": score,
                "n_clusters": cluster_result.n_clusters,
                "noise_points": cluster_result.noise_points,
            }
            results.append(row)
            if score > best_score:
                best_score = score
                best_params = param_dict

        return {"best_params": best_params, "best_score": best_score, "all_results": results}
