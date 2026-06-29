"""Optional Plotly visualization for semantic SARIF clusters."""

from __future__ import annotations

from typing import Any

from drift.trinity.sarif_models import SarifFinding
from drift.trinity.sarif_pipeline.semantic_clusterer import ClusterResult, SemanticClusterer, semantic_clustering_available


def visualize_semantic_clusters(
    findings: list[SarifFinding],
    cluster_result: ClusterResult,
    *,
    title: str = "SARIF Semantic Clusters",
    embedding_model: str = "all-MiniLM-L6-v2",
) -> Any:
    if not semantic_clustering_available():
        raise RuntimeError("Visualization requires semantic clustering dependencies")

    try:
        import pandas as pd
        import plotly.express as px
        import umap
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("plotly, pandas, and umap-learn are required for visualization") from exc

    clusterer = SemanticClusterer(embedding_model=embedding_model)
    texts = [clusterer._embedding_text(f) for f in findings]
    embeddings = clusterer.generate_embeddings(texts)
    reducer = umap.UMAP(n_components=2, random_state=42, n_neighbors=15)
    coords = reducer.fit_transform(embeddings)

    df = pd.DataFrame(
        {
            "x": coords[:, 0],
            "y": coords[:, 1],
            "cluster": [
                str(int(label)) if int(label) != -1 else "Noise"
                for label in cluster_result.cluster_labels
            ],
            "rule": [f.rule_id for f in findings],
            "message": [f.message[:100] for f in findings],
            "file": [f.file_path for f in findings],
        }
    )

    fig = px.scatter(
        df,
        x="x",
        y="y",
        color="cluster",
        hover_data=["rule", "message", "file"],
        title=title,
        opacity=0.8,
    )
    fig.update_traces(marker={"size": 8})
    return fig
