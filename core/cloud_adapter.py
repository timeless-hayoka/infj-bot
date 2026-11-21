"""Small authenticated, read-only HTTP adapter for the existing DRIFT runtime.

This is an internal HTTP adapter, not a public MCP protocol endpoint.
Expose it only behind HTTPS with additional network-level protections.
"""

import os
import secrets

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field


class MemoryQuery(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    limit: int = Field(default=5, ge=1, le=10)


def create_app() -> FastAPI:
    token = os.environ.get("DRIFT_PLUGIN_TOKEN", "")
    if len(token) < 16:
        raise RuntimeError(
            "DRIFT_PLUGIN_TOKEN must be configured with at least 16 characters"
        )

    app = FastAPI(
        title="DRIFT Read-Only Cloud Adapter",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )

    def authenticate(authorization: str | None = Header(default=None)) -> None:
        supplied = ""
        if authorization and authorization.startswith("Bearer "):
            supplied = authorization[7:]
        if not secrets.compare_digest(supplied, token):
            raise HTTPException(status_code=401, detail="Unauthorized")

    @app.get("/health", dependencies=[Depends(authenticate)])
    def health() -> dict[str, str]:
        return {"status": "ready", "adapter": "drift-readonly-v1"}

    @app.post("/memory/search", dependencies=[Depends(authenticate)])
    def memory_search(body: MemoryQuery) -> dict[str, str]:
        # Import only on use: no substitute memory store or synthetic response.
        try:
            from drift.core.mcp_server import memory_search as production_memory_search

            result = production_memory_search(body.query, n_results=body.limit)
        except Exception:  # noqa: BLE001 - boundary must sanitize unexpected storage failures
            # Fail closed: never expose storage paths, credentials or stack traces.
            raise HTTPException(
                status_code=503, detail="DRIFT memory unavailable"
            ) from None
        return {"result": result}

    return app
