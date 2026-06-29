"""Semantic clustering for SARIF findings (optional ML dependencies)."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from drift.trinity.sarif_models import SarifFinding

_SEMANTIC_DEPS: str | None = None
try:
    import hdbscan  # noqa: F401
    import numpy as np  # noqa: F401
    import umap  # noqa: F401
    from sentence_transformers import SentenceTransformer  # noqa: F401
except ImportError as exc:
    _SEMANTIC_DEPS = str(exc)


def semantic_clustering_available() -> bool:
    return _SEMANTIC_DEPS is None


@dataclass
class ClusterResult:
    cluster_labels: Any
    noise_points: int = 0
    n_clusters: int = 0
    cluster_summaries: dict[int, str] = field(default_factory=dict)


class SemanticClusterer:
    def __init__(
        self,
        embedding_model: str = "all-MiniLM-L6-v2",
        umap_n_neighbors: int = 15,
        umap_min_dist: float = 0.0,
        umap_n_components: int = 5,
        hdbscan_min_cluster_size: int = 2,
        hdbscan_min_samples: int = 1,
        metric: str = "euclidean",
        random_state: int = 42,
    ) -> None:
        if not semantic_clustering_available():
            raise RuntimeError(
                "Semantic clustering requires sentence-transformers, umap-learn, hdbscan, and numpy. "
                f"Import error: {_SEMANTIC_DEPS}"
            )
        from sentence_transformers import SentenceTransformer

        self.embedding_model_name = embedding_model
        self.model = SentenceTransformer(embedding_model)
        self.umap_n_neighbors = umap_n_neighbors
        self.umap_min_dist = umap_min_dist
        self.umap_n_components = umap_n_components
        self.hdbscan_min_cluster_size = hdbscan_min_cluster_size
        self.hdbscan_min_samples = hdbscan_min_samples
        self.metric = metric
        self.random_state = random_state

    def _embedding_text(self, finding: SarifFinding) -> str:
        norm = finding.normalized or {}
        parts = [
            finding.message,
            finding.snippet or "",
            str(norm.get("category", "")),
            finding.rule_id,
        ]
        return " | ".join(part for part in parts if part)

    def generate_embeddings(self, texts: list[str]) -> Any:
        import numpy as np

        return self.model.encode(texts, show_progress_bar=False, convert_to_numpy=True)

    def cluster(
        self,
        findings: list[SarifFinding],
        *,
        return_cluster_summaries: bool = True,
    ) -> ClusterResult:
        import hdbscan
        import numpy as np
        import umap

        if not findings:
            return ClusterResult(cluster_labels=np.array([]))

        texts = [self._embedding_text(f) for f in findings]
        embeddings = self.generate_embeddings(texts)

        if embeddings.shape[1] > self.umap_n_components:
            reducer = umap.UMAP(
                n_neighbors=self.umap_n_neighbors,
                min_dist=self.umap_min_dist,
                n_components=self.umap_n_components,
                metric="cosine",
                random_state=self.random_state,
            )
            reduced = reducer.fit_transform(embeddings)
        else:
            reduced = embeddings

        clusterer = hdbscan.HDBSCAN(
            min_cluster_size=self.hdbscan_min_cluster_size,
            min_samples=self.hdbscan_min_samples,
            metric=self.metric,
            cluster_selection_method="eom",
            prediction_data=True,
        )
        labels = clusterer.fit_predict(reduced)
        noise_points = int(np.sum(labels == -1))
        n_clusters = len(set(labels)) - (1 if -1 in labels else 0)

        summaries: dict[int, str] = {}
        if return_cluster_summaries and n_clusters > 0:
            summaries = self._generate_cluster_summaries(findings, labels, texts)

        return ClusterResult(
            cluster_labels=labels,
            noise_points=noise_points,
            n_clusters=n_clusters,
            cluster_summaries=summaries,
        )

    def _generate_cluster_summaries(
        self,
        findings: list[SarifFinding],
        labels: Any,
        texts: list[str],
    ) -> dict[int, str]:
        import numpy as np

        summaries: dict[int, str] = {}
        unique_labels = {int(label) for label in labels if int(label) != -1}
        for label in unique_labels:
            indices = np.where(labels == label)[0]
            categories = []
            for idx in indices:
                category = (findings[int(idx)].normalized or {}).get("category")
                if category:
                    categories.append(str(category))
            if categories:
                most_common = Counter(categories).most_common(1)[0][0]
                summaries[label] = f"Cluster {label}: {most_common} ({len(indices)} findings)"
            else:
                summaries[label] = f"Cluster {label}: {texts[int(indices[0])][:80]}..."
        return summaries

    def assign_clusters_to_findings(
        self,
        findings: list[SarifFinding],
        cluster_result: ClusterResult,
    ) -> list[SarifFinding]:
        for index, finding in enumerate(findings):
            label = int(cluster_result.cluster_labels[index])
            finding.properties.setdefault("semantic_cluster", {})
            finding.properties["semantic_cluster"] = {
                "cluster_id": label if label != -1 else None,
                "is_noise": label == -1,
                "cluster_summary": cluster_result.cluster_summaries.get(label, ""),
            }
        return findings
