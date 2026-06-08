"""
governor_metrics_api.py — debug/observability endpoint for the RateGovernor.

This is the CORRECTED version. The draft floating around read metrics.get(...),
keys like "cache_hits"/"cache_misses", and treated _pstate values as dicts with
a "consec_fail" field. None of that matches generation.py, where:
  * Metrics is an OBJECT (use .snapshot(), there is no .get())
  * the keys are dotted: "cache.hit" / "cache.miss" / "coalesced"
  * _pstate holds ProviderState dataclasses (field: consecutive_failures)

So this router just calls gov.metrics_report(), which already does the right
thing. Pass a callable that returns your live InfjBrain instance — no globals.

Wire-in (in web_app.py / api.py):
    from governor_metrics_api import build_governor_router
    app.include_router(build_governor_router(lambda: drift_brain))
"""

from __future__ import annotations

from typing import Callable

from fastapi import APIRouter, HTTPException


def build_governor_router(get_brain: Callable[[], object]) -> APIRouter:
    router = APIRouter()

    @router.get("/api/v1/system/governor-metrics")
    def governor_metrics():
        brain = get_brain()
        gov = getattr(brain, "_governor", None)
        if gov is None:
            raise HTTPException(
                status_code=503,
                detail=(
                    "RateGovernor not initialized. Call self.init_governor() in "
                    "InfjBrain.__init__ (eager) — it builds the governor and "
                    "validates provider config at boot."
                ),
            )
        return {"status": "online", **gov.metrics_report()}

    return router
