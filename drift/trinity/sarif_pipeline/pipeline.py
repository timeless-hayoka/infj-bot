"""End-to-end SARIF processing: parse, normalize, dedupe, cluster, enrich, persist."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from drift.trinity.adapters.sarif import load_sarif_file
from drift.trinity.rule_normalizer import RuleNormalizer
from drift.trinity.sarif_deduplicator import SarifDeduplicator
from drift.trinity.sarif_models import EnrichedFinding, NormalizedRule, SarifFinding
from drift.trinity.sarif_pipeline.semantic_clusterer import ClusterResult, SemanticClusterer, semantic_clustering_available
from drift.trinity.sarif_pipeline.storage import ChromaFindingStore, init_sqlite, persist_sqlite


class SARIFProcessingPipeline:
    def __init__(
        self,
        db_path: Path | str = Path("security_findings.db"),
        chroma_directory: Path | str | None = Path("./chroma_db"),
        chroma_collection: str = "security_findings",
        mapping_file: Path | None = None,
        line_tolerance: int = 3,
        dedupe_strategy: str = "normalized",
        enable_semantic_clustering: bool = True,
        embedding_model: str = "all-MiniLM-L6-v2",
        llm_summarizer: Callable[[str], str] | None = None,
        source_root: Path | str | None = None,
        enable_chroma: bool = True,
    ) -> None:
        self.db_path = Path(db_path)
        self.chroma_directory = Path(chroma_directory) if chroma_directory else None
        self.chroma_collection = chroma_collection
        self.source_root = Path(source_root) if source_root else None
        self.llm_summarizer = llm_summarizer
        self.dedupe_strategy = dedupe_strategy

        self.deduplicator = SarifDeduplicator(line_tolerance=line_tolerance)
        self.normalizer = RuleNormalizer(mapping_file=mapping_file)

        self.clusterer: SemanticClusterer | None = None
        if enable_semantic_clustering and semantic_clustering_available():
            self.clusterer = SemanticClusterer(embedding_model=embedding_model)
        elif enable_semantic_clustering:
            self.clusterer = None  # deps missing; pipeline still runs without clustering

        self._chroma_store: ChromaFindingStore | None = None
        if enable_chroma and self.chroma_directory is not None:
            try:
                self._chroma_store = ChromaFindingStore(
                    self.chroma_directory,
                    collection_name=chroma_collection,
                )
            except RuntimeError:
                self._chroma_store = None

        init_sqlite(self.db_path)

    def process(
        self,
        sarif_files: dict[str, Path | str],
        *,
        enable_llm_summaries: bool = False,
    ) -> list[EnrichedFinding]:
        all_findings: list[SarifFinding] = []
        for tool, path in sarif_files.items():
            all_findings.extend(load_sarif_file(path, tool_hint=tool))

        norm_map: dict[int, NormalizedRule] = {
            id(finding): self.normalizer.normalize(finding) for finding in all_findings
        }

        for finding in all_findings:
            norm = norm_map[id(finding)]
            finding.normalized = {
                "original_rule_id": norm.original_rule_id,
                "tool": norm.tool,
                "cwe": norm.cwe,
                "owasp": norm.owasp,
                "category": norm.category,
                "severity_hint": norm.severity_hint,
                "tags": norm.tags,
                "confidence": norm.confidence,
                "mapping_version": self.normalizer.mapping_version,
            }

        findings_by_tool: dict[str, list[SarifFinding]] = {}
        for finding in all_findings:
            findings_by_tool.setdefault(finding.tool, []).append(finding)

        dedup_result = self.deduplicator.deduplicate_cross_tool(
            findings_by_tool,
            strategy=self.dedupe_strategy,
        )
        unique_findings = dedup_result.unique_findings

        cluster_result: ClusterResult | None = None
        if self.clusterer and unique_findings:
            cluster_result = self.clusterer.cluster(unique_findings)
            self.clusterer.assign_clusters_to_findings(unique_findings, cluster_result)

        cluster_summaries = cluster_result.cluster_summaries if cluster_result else {}
        enriched_list: list[EnrichedFinding] = []

        for finding in unique_findings:
            norm = norm_map.get(id(finding)) or self.normalizer.normalize(finding)
            context = self._get_source_context(finding) if self.source_root else None
            cluster_meta = finding.properties.get("semantic_cluster") or {}
            cluster_id = cluster_meta.get("cluster_id")
            base_summary = cluster_summaries.get(cluster_id, "") if cluster_id is not None else ""

            final_summary = base_summary
            if enable_llm_summaries and self.llm_summarizer and cluster_id is not None:
                prompt = self._build_cluster_prompt(finding, cluster_id, base_summary)
                try:
                    final_summary = self.llm_summarizer(prompt).strip()
                except Exception as exc:  # pragma: no cover - LLM hook failures are non-fatal
                    final_summary = base_summary or f"LLM summarization failed: {exc}"

            enriched = EnrichedFinding(
                finding=finding,
                normalized=norm,
                source_context=context,
                dedup_key=self.deduplicator.key_strategy(finding, strategy=self.dedupe_strategy),
                cluster_id=cluster_id,
                cluster_summary=final_summary,
            )
            enriched_list.append(enriched)
            self._persist(enriched)

        return enriched_list

    def to_trinity_findings(
        self,
        enriched_list: list[EnrichedFinding],
        *,
        source_path: Path | str,
    ) -> list[dict]:
        from drift.trinity.adapters.sarif import sarif_finding_to_trinity_dict

        source_path = Path(source_path)
        results: list[dict] = []
        for index, enriched in enumerate(enriched_list):
            row = sarif_finding_to_trinity_dict(enriched.finding, index=index, source_path=source_path)
            row["cluster_id"] = enriched.cluster_id
            row["cluster_summary"] = enriched.cluster_summary
            row["source_context"] = enriched.source_context
            results.append(row)
        return results

    def _build_cluster_prompt(self, finding: SarifFinding, cluster_id: int, base_summary: str) -> str:
        category = (finding.normalized or {}).get("category", "Unknown")
        return (
            "You are a senior security researcher.\n"
            f"Cluster {cluster_id} contains findings semantically similar to this one:\n"
            f"Rule: {finding.rule_id}\n"
            f"Message: {finding.message}\n"
            f"Category: {category}\n\n"
            f"Base summary: {base_summary}\n\n"
            "Provide a concise, professional one-paragraph summary of the vulnerability pattern "
            "represented by this cluster, including common root causes and recommended mitigations."
        )

    def _get_source_context(self, finding: SarifFinding, context_lines: int = 6) -> str:
        if not self.source_root:
            return ""
        try:
            file_path = self.source_root / finding.file_path.lstrip("./")
            if not file_path.exists():
                return ""
            lines = file_path.read_text(encoding="utf-8", errors="ignore").splitlines()
            start = max(0, finding.start_line - 1 - context_lines)
            end = min(len(lines), finding.start_line + context_lines)
            return "\n".join(lines[start:end])
        except OSError:
            return ""

    def _persist(self, enriched: EnrichedFinding) -> None:
        persist_sqlite(self.db_path, enriched)
        if self._chroma_store is not None:
            self._chroma_store.upsert(enriched)
