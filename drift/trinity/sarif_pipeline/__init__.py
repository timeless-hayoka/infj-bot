"""End-to-end SARIF intelligence pipeline for Trinity."""

from drift.trinity.sarif_models import EnrichedFinding
from drift.trinity.sarif_pipeline.pipeline import SARIFProcessingPipeline

__all__ = ["EnrichedFinding", "SARIFProcessingPipeline"]
