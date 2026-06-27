"""Shared security and observability helpers for the MCP server."""

from __future__ import annotations

import contextlib
import hashlib
import json
import logging
import os
import time
from collections import defaultdict, deque
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Deque, Dict, Iterable, Mapping, MutableMapping, Optional

from prometheus_client import Counter, Gauge, Histogram

try:  # Optional, but available in this environment.
    import jwt
except Exception:  # pragma: no cover - optional dependency
    jwt = None  # type: ignore[assignment]

try:  # Optional, but available in this environment.
    from jwt import PyJWKClient
except Exception:  # pragma: no cover - optional dependency
    PyJWKClient = None  # type: ignore[assignment]

from core.unified_audit import audit_log
from core.jsonl_logger import HardenedJsonlLogger

logger = logging.getLogger("infj_mcp.security")

MCP_TOOL_CALLS = Counter(
    "infj_mcp_tool_calls_total",
    "Total MCP tool calls observed",
    ["tool", "status"],
)
MCP_TOOL_DURATION = Histogram(
    "infj_mcp_tool_duration_seconds",
    "Duration of MCP tool calls",
    ["tool"],
)
MCP_AUTH_FAILURES = Counter(
    "infj_mcp_auth_failures_total",
    "Authentication failures observed by the MCP server",
    ["reason"],
)
MCP_RATE_LIMIT_HITS = Counter(
    "infj_mcp_rate_limit_hits_total",
    "Rate limit rejections observed by the MCP server",
    ["tool"],
)
MCP_ACTIVE_CALLS = Gauge(
    "infj_mcp_active_calls",
    "Currently active MCP tool calls",
)


@dataclass(slots=True)
class SecurityPrincipal:
    """Authenticated identity for an MCP caller."""

    identity: str
    token_prefix: str
    source: str
    scopes: tuple[str, ...] = ()
    claims: Dict[str, Any] | None = None


@dataclass(slots=True)
class RateLimitDecision:
    allowed: bool
    retry_after_seconds: float = 0.0
    limit: int = 0
    window_seconds: int = 0


class McpSecurityGuard:
    """Centralizes auth, rate limiting, metrics, and audit logging."""

    def __init__(
        self,
        *,
        expected_token: str | None,
        jwt_secret: str | None = None,
        jwks_url: str | None = None,
        audit_path: str | Path | None = None,
        mirror_outcome_path: str | Path | None = None,
        rate_limit_defaults: Mapping[str, tuple[int, int]] | None = None,
        open_mode: bool = False,
    ) -> None:
        self.expected_token = expected_token
        self.jwt_secret = jwt_secret or None
        self.jwks_url = jwks_url or None
        self.open_mode = open_mode
        self.rate_limit_defaults = dict(rate_limit_defaults or {})
        self._windows: dict[tuple[str, str], Deque[float]] = defaultdict(deque)
        self._last_call: dict[tuple[str, str], float] = {}
        self.audit_logger = HardenedJsonlLogger(
            Path(audit_path or Path.cwd() / "mcp_audit.jsonl")
        )
        self.mirror_outcome_path = Path(mirror_outcome_path) if mirror_outcome_path else None
        self._jwks_client = None
        if self.jwks_url and PyJWKClient is not None:
            self._jwks_client = PyJWKClient(self.jwks_url)

    @staticmethod
    def _token_prefix(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()[:12]

    @staticmethod
    def _normalize_scopes(claims: Mapping[str, Any] | None) -> tuple[str, ...]:
        if not claims:
            return ()
        raw = claims.get("scopes", claims.get("scope", claims.get("permissions", ())))
        if isinstance(raw, str):
            return tuple(scope for scope in raw.replace(",", " ").split() if scope)
        if isinstance(raw, Iterable):
            return tuple(str(scope) for scope in raw if scope)
        return ()

    def _decode_jwt(self, token: str) -> Dict[str, Any] | None:
        if jwt is None:
            return None
        try:
            if self._jwks_client is not None:
                signing_key = self._jwks_client.get_signing_key_from_jwt(token)
                return jwt.decode(
                    token,
                    signing_key.key,
                    algorithms=["RS256", "ES256", "PS256"],
                    options={"verify_aud": False},
                )
            if self.jwt_secret:
                return jwt.decode(
                    token,
                    self.jwt_secret,
                    algorithms=["HS256", "HS384", "HS512"],
                    options={"verify_aud": False},
                )
        except Exception as exc:  # pragma: no cover - defensive path
            logger.warning("JWT decode failed: %s", exc)
            return None
        return None

    def authenticate(
        self,
        *,
        token: str | None,
        source: str,
    ) -> SecurityPrincipal:
        if not token:
            if self.open_mode or not self.expected_token:
                return SecurityPrincipal(
                    identity="open-mode",
                    token_prefix="open-mode",
                    source=source,
                    scopes=(),
                    claims={},
                )
            MCP_AUTH_FAILURES.labels(reason="missing_token").inc()
            raise PermissionError("Authentication required")

        claims = None
        token_prefix = self._token_prefix(token)

        if token.startswith("eyJ"):
            claims = self._decode_jwt(token)
            if claims is not None:
                token_prefix = self._token_prefix(token)
                identity = str(claims.get("sub") or claims.get("client_id") or token_prefix)
                return SecurityPrincipal(
                    identity=identity,
                    token_prefix=token_prefix,
                    source=source,
                    scopes=self._normalize_scopes(claims),
                    claims=dict(claims),
                )

        if self.expected_token and token != self.expected_token:
            MCP_AUTH_FAILURES.labels(reason="invalid_token").inc()
            raise PermissionError("Invalid authentication token")

        return SecurityPrincipal(
            identity=token_prefix,
            token_prefix=token_prefix,
            source=source,
            scopes=(),
            claims=claims or {},
        )

    def required_scope_for(self, tool_name: str, kwargs: Mapping[str, Any] | None = None) -> str | None:
        kwargs = kwargs or {}
        if tool_name == "autonomy":
            return "autonomy:execute"
        if tool_name == "ingest_document":
            return "documents:write"
        if tool_name in {"todo_add", "todo_complete"}:
            return "todo:write"
        if tool_name in {"memory_search", "document_search", "todo_list", "companion_think"}:
            return "read"
        if kwargs.get("reproduce"):
            return "hunt:execute"
        return None

    def enforce_scope(self, principal: SecurityPrincipal, scope: str | None) -> None:
        if not scope or principal.identity == "open-mode":
            return
        if scope == "read":
            return
        if scope not in principal.scopes:
            MCP_AUTH_FAILURES.labels(reason="missing_scope").inc()
            raise PermissionError(f"Missing required scope: {scope}")

    def get_rate_limit(self, tool_name: str) -> tuple[int, int]:
        return self.rate_limit_defaults.get(tool_name, self.rate_limit_defaults.get("default", (60, 60)))

    def check_rate_limit(self, principal: SecurityPrincipal, tool_name: str) -> RateLimitDecision:
        limit, window_seconds = self.get_rate_limit(tool_name)
        now = time.monotonic()
        key = (principal.identity, tool_name)
        window = self._windows[key]
        window_start = now - window_seconds
        while window and window[0] < window_start:
            window.popleft()
        if len(window) >= limit:
            retry_after = max(0.0, window[0] + window_seconds - now) if window else float(window_seconds)
            MCP_RATE_LIMIT_HITS.labels(tool=tool_name).inc()
            return RateLimitDecision(
                allowed=False,
                retry_after_seconds=retry_after,
                limit=limit,
                window_seconds=window_seconds,
            )
        window.append(now)
        self._last_call[key] = now
        return RateLimitDecision(allowed=True, limit=limit, window_seconds=window_seconds)

    def _mirror_outcome_memory(self, record: Dict[str, Any]) -> None:
        if self.mirror_outcome_path is None:
            return
        try:
            existing: dict[str, Any] = {}
            if self.mirror_outcome_path.exists():
                existing = json.loads(self.mirror_outcome_path.read_text(encoding="utf-8"))
                if not isinstance(existing, dict):
                    existing = {}
            existing.setdefault("mcp_audit_events", [])
            events = list(existing["mcp_audit_events"])
            events.append(record)
            existing["mcp_audit_events"] = events[-500:]
            self.mirror_outcome_path.parent.mkdir(parents=True, exist_ok=True)
            self.mirror_outcome_path.write_text(json.dumps(existing, indent=2), encoding="utf-8")
        except Exception:
            logger.debug("Unable to mirror MCP audit event", exc_info=True)

    def audit(
        self,
        *,
        event: str,
        tool: str,
        principal: SecurityPrincipal | None,
        status: str,
        transport: str,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event": event,
            "tool": tool,
            "status": status,
            "transport": transport,
            "identity": principal.identity if principal else "unknown",
            "token_prefix": principal.token_prefix if principal else "unknown",
            "scopes": list(principal.scopes) if principal else [],
            "details": dict(details or {}),
        }
        self.audit_logger.append(record)
        audit_log(event, "mcp_server", record)
        self._mirror_outcome_memory(record)

    @contextmanager
    def tool_span(self, *, tool: str, principal: SecurityPrincipal | None, transport: str):
        MCP_ACTIVE_CALLS.inc()
        start = time.perf_counter()
        try:
            yield
            MCP_TOOL_CALLS.labels(tool=tool, status="success").inc()
            self.audit(event="tool_call", tool=tool, principal=principal, status="success", transport=transport)
        except Exception as exc:
            MCP_TOOL_CALLS.labels(tool=tool, status="error").inc()
            self.audit(
                event="tool_call",
                tool=tool,
                principal=principal,
                status="error",
                transport=transport,
                details={"error": str(exc)},
            )
            raise
        finally:
            duration = time.perf_counter() - start
            MCP_TOOL_DURATION.labels(tool=tool).observe(duration)
            MCP_ACTIVE_CALLS.dec()

