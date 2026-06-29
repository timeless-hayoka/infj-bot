"""MCP server exposing the INFJ companion as an external tool.

Supports stdio transport (default) and a simple HTTP transport for local orchestration.
"""

import asyncio
import os
from typing import Any, Dict, List, Optional
import logging

try:
    from mcp.server.fastmcp import FastMCP
except Exception:
    FastMCP = None  # type: ignore[assignment]

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from prometheus_client import Gauge, Counter, generate_latest, CONTENT_TYPE_LATEST
import uvicorn
import time
from datetime import datetime
from pathlib import Path

from drift.core.brain import DriftBrain
from drift.core.being import get_being
from drift.core.websocket_manager import manager
from drift.core.config import PROJECT_ROOT
from drift.core.cognition import map_dissonance
try:
    from drift.core.plugins.documents import DocumentStore, format_doc_results
except Exception:
    DocumentStore = None  # type: ignore[assignment]

    def format_doc_results(*args, **kwargs):
        return "Document search unavailable."
try:
    from drift.core.plugins.emotion import detect_emotion
except Exception:
    def detect_emotion(*args, **kwargs):
        return {
            "label": "unknown",
            "confidence": 0.0,
            "intensity": 0.0,
            "valence": 0.0,
            "arousal": 0.0,
            "needs": [],
            "detector": "unavailable",
        }
try:
    from drift.core.plugins.goals import GoalsDB
except Exception:
    GoalsDB = None  # type: ignore[assignment]
try:
    from drift.core.memory import DriftMemory
except Exception:
    DriftMemory = None  # type: ignore[assignment]
try:
    from drift.core.global_workspace import GlobalWorkspace
except Exception:
    GlobalWorkspace = None  # type: ignore[assignment]
from core.mcp_security import (
    McpSecurityGuard,
    SecurityPrincipal,
)

try:
    from hive_mind.orchestrator import HiveOrchestrator
except Exception:
    HiveOrchestrator = None  # type: ignore[misc,assignment]

class _NullMCP:
    def tool(self):
        def decorator(fn):
            return fn

        return decorator

    async def run_stdio_async(self):
        raise RuntimeError("FastMCP is unavailable in this environment")


mcp = (
    FastMCP(
        "infj_companion",
        instructions="""
You are interfacing with the INFJ Companion Bot — a local AI companion with deep memory,
emotional awareness, cognitive dissonance mapping, and document retrieval.

Use these tools when:
- The user needs emotional clarity or support
- The user seems torn between options
- The user references past conversations or knowledge
- The user asks about documents they have ingested
- The user needs help tracking goals or todos
- The user asks about ANCHOR architecture, SARIF, evidence models, or Trinity workflows
  (use anchor_knowledge_* tools for structured repo docs; vault_knowledge_search for vault files)
""",
    )
    if FastMCP is not None
    else _NullMCP()
)

brain: Optional[DriftBrain] = None
memory: Optional[DriftMemory] = None
goals_db: Optional[GoalsDB] = None
doc_store: Optional[DocumentStore] = None


# === Prometheus Metrics ===
pedi_gauge = Gauge('drift_pedi_value', 'Persistent Entity Drift Index')
dii_gauge = Gauge('drift_dii_value', 'Dynamic Integration Index')
energy_gauge = Gauge('drift_energy_level', 'Current energy level')
social_risk_gauge = Gauge('drift_social_risk', 'Current social engineering risk')
shadow_influence_gauge = Gauge('drift_shadow_influence', 'Current shadow influence')
active_connections_gauge = Gauge('drift_active_ws_connections', 'Active WebSocket connections')
sparks_delivered_counter = Counter('drift_sparks_delivered_total', 'Total sparks delivered')
security_blocks_counter = Counter('drift_security_blocks_total', 'Total security blocks')
high_risk_events_counter = Counter('drift_high_risk_events_total', 'Total high social risk events')


async def broadcast_security_event(event_data: dict):
    """Broadcast security event to dashboard and update metrics."""
    event_data["type"] = "security"
    await manager.broadcast(event_data)
    
    # Update counters
    if event_data.get("action") == "block":
        security_blocks_counter.inc()
    if event_data.get("social_risk", 0) > 0.5:
        high_risk_events_counter.inc()
    
    # Update gauges
    social_risk_gauge.set(event_data.get("social_risk", 0))
    shadow_influence_gauge.set(event_data.get("shadow_influence", 0))


async def server_heartbeat():
    """Send periodic heartbeat to all connected clients."""
    heartbeat_count = 0
    while True:
        await asyncio.sleep(15)
        heartbeat_count += 1
        try:
            being = get_being()
            heartbeat_msg = {
                "type": "heartbeat",
                "ts": datetime.now().isoformat(),
                "count": heartbeat_count,
                "status": "alive",
                "pedi_value": getattr(being.state.pedi, 'value', 0.0),
                "pedi_stability": getattr(being.state.pedi, 'stability', 0.0),
                "dii_value": getattr(being.state.dii, 'value', 0.0),
                "energy": getattr(being.state, 'energy', 0.0),
                "message": "Server heartbeat — connection healthy"
            }
            await manager.broadcast(heartbeat_msg)
        except Exception:
            pass


def get_brain() -> DriftBrain:
    global brain
    if brain is None:
        brain = DriftBrain()
    return brain


def get_memory() -> DriftMemory:
    global memory
    if memory is None:
        memory = DriftMemory()
    return memory


def get_goals_db() -> GoalsDB:
    global goals_db
    if goals_db is None:
        goals_db = GoalsDB()
    return goals_db


def get_doc_store() -> DocumentStore:
    global doc_store
    if doc_store is None:
        doc_store = DocumentStore()
    return doc_store


def create_http_app(token: str | None = None) -> FastAPI:
    """Create a minimal FastAPI app that exposes the available tools as HTTP endpoints.

    POST /invoke/{tool_name} with JSON body {"args": [], "kwargs": {}} will call the
    corresponding function and return {"result": ...}.
    """
    app = FastAPI(title="INFJ Companion (HTTP bridge)")

    # token may be provided explicitly for tests; otherwise read from env
    token = token if token is not None else os.getenv("MCP_HTTP_TOKEN")
    jwt_secret = os.getenv("MCP_JWT_SECRET") or os.getenv("TRINITY_JWT_SECRET")
    jwks_url = os.getenv("MCP_JWKS_URL") or os.getenv("TRINITY_JWKS_URL")
    rate_limit_per_min = int(os.getenv("MCP_RATE_LIMIT_PER_MIN", "60"))

    # Shared auth / rate-limit / audit guard for the HTTP bridge
    security = McpSecurityGuard(
        expected_token=token,
        jwt_secret=jwt_secret,
        jwks_url=jwks_url,
        audit_path=Path(PROJECT_ROOT) / "logs" / "mcp_audit.jsonl",
        mirror_outcome_path=Path(PROJECT_ROOT) / "outcome_memory.json",
        rate_limit_defaults={
            "default": (rate_limit_per_min, 60),
            "autonomy": (max(1, rate_limit_per_min // 4), 60),
            "todo_add": (max(5, rate_limit_per_min // 2), 60),
            "todo_complete": (max(5, rate_limit_per_min // 2), 60),
            "ingest_document": (max(5, rate_limit_per_min // 2), 60),
        },
        open_mode=not bool(token or jwt_secret or jwks_url),
    )

    # Mount static files
    static_dir = Path(PROJECT_ROOT) / "static"
    if not static_dir.exists():
        static_dir.mkdir(parents=True)
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    @app.get("/dashboard", response_class=HTMLResponse)
    async def get_dashboard():
        dashboard_path = static_dir / "dashboard.html"
        if dashboard_path.exists():
            with open(dashboard_path, "r") as f:
                return f.read()
        return "Dashboard not found. Ensure static/dashboard.html exists."

    @app.get("/metrics")
    async def prometheus_metrics():
        being = get_being()
        pedi_gauge.set(getattr(being.state.pedi, "value", 0.0))
        dii_gauge.set(getattr(being.state.dii, "value", 0.0))
        energy_gauge.set(getattr(being.state, "energy", 0.0))
        active_connections_gauge.set(len(manager.active_connections))
        return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket):
        await manager.connect(websocket)
        try:
            while True:
                data = await websocket.receive_text()
                if data.lower() in ["ping", "heartbeat"]:
                    await websocket.send_text("pong")
        except WebSocketDisconnect:
            manager.disconnect(websocket)
        except Exception:
            manager.disconnect(websocket)

    # Start heartbeat
    @app.on_event("startup")
    async def startup_event():
        asyncio.create_task(server_heartbeat())

    # Map public tool names to callables
    TOOLS: Dict[str, Any] = {
        "emotional_clarity": emotional_clarity,
        "dissonance_map": dissonance_map,
        "memory_search": memory_search,
        "document_search": document_search,
        "anchor_vault_status": anchor_vault_status,
        "vault_knowledge_search": vault_knowledge_search,
        "anchor_knowledge_list": anchor_knowledge_list,
        "anchor_knowledge_search": anchor_knowledge_search,
        "anchor_knowledge_get": anchor_knowledge_get,
        "anchor_knowledge_refs": anchor_knowledge_refs,
        "todo_list": todo_list,
        "todo_add": todo_add,
        "todo_complete": todo_complete,
        "companion_think": companion_think,
        "ingest_document": ingest_document,
        "hive_status": hive_status,
        "workspace_snapshot": workspace_snapshot,
    }

    # Concurrency and cooldown controls
    concurrency = int(os.getenv("MCP_AUTONOMY_CONCURRENCY", "2"))
    min_interval = float(os.getenv("MCP_AUTONOMY_MIN_INTERVAL", "1.0"))
    semaphore = asyncio.Semaphore(concurrency)
    last_run: Dict[str, float] = {}

    # Simple in-memory scheduled tasks store: id -> {run_at, plan, token}
    scheduled: Dict[str, Dict[str, Any]] = {}

    # Metrics and rate-limiting
    metrics = {
        "invoke_count": 0,
        "autonomy_count": 0,
        "scheduled_count": 0,
    }


    # configure logging
    logging.basicConfig(level=os.getenv("MCP_LOG_LEVEL", "INFO"))
    logger = logging.getLogger("infj_mcp")

    # Bounded task tracking for scheduled jobs
    _scheduled_tasks: set = set()
    _max_scheduled_tasks = int(os.getenv("MCP_MAX_SCHEDULED_TASKS", "50"))

    async def schedule_worker():
        while True:
            now = time.time()
            to_run = []
            for tid, t in list(scheduled.items()):
                if t.get("run_at", 0) <= now and not t.get("running"):
                    to_run.append((tid, t))
            for tid, t in to_run:
                t["running"] = True
                if len(_scheduled_tasks) >= _max_scheduled_tasks:
                    logger.warning(
                        "Max scheduled tasks (%d) reached; dropping task %s",
                        _max_scheduled_tasks,
                        tid,
                    )
                    scheduled.pop(tid, None)
                    continue

                async def run_and_cleanup(tid=tid, t=t):
                    try:
                        plan = t["plan"]
                        async with semaphore:
                            results = []
                            for step in plan:
                                tool_name = step.get("tool")
                                fn = TOOLS.get(tool_name)
                                if fn is None:
                                    results.append(
                                        {"tool": tool_name, "error": "tool not found"}
                                    )
                                    continue
                                args = step.get("args") or []
                                kwargs = step.get("kwargs") or {}
                                try:
                                    out = fn(*args, **kwargs)
                                    results.append({"tool": tool_name, "result": out})
                                except Exception as exc:
                                    results.append(
                                        {"tool": tool_name, "error": str(exc)}
                                    )
                            t["result"] = results
                    finally:
                        scheduled.pop(tid, None)

                task = asyncio.create_task(run_and_cleanup())
                _scheduled_tasks.add(task)
                task.add_done_callback(_scheduled_tasks.discard)
            await asyncio.sleep(0.5)

    # start background worker safely
    async def _start_worker():
        try:
            asyncio.create_task(schedule_worker())
        except Exception:
            pass

    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_start_worker())
    except RuntimeError:
        # No running loop yet (e.g. during import or stdio mode)
        pass

    @app.get("/health")
    def health() -> Dict[str, str]:
        return {"status": "ok", "transport": "http"}

    @app.get("/status")
    def metrics_endpoint() -> Dict[str, Any]:
        return {
            "metrics": metrics,
            "rate_limit_per_min": rate_limit_per_min,
            "scheduled": len(scheduled),
            "auth_mode": "open" if security.open_mode else "protected",
        }


    @app.post("/invoke/{tool_name}")
    async def invoke(tool_name: str, body: Dict[str, Any], request: Request):
        fn = TOOLS.get(tool_name)
        if fn is None:
            raise HTTPException(status_code=404, detail=f"Tool {tool_name} not found")

        client_ip = request.client.host if request.client else "unknown"
        auth_header = request.headers.get("authorization") or ""
        auth_token = None
        if auth_header.lower().startswith("bearer "):
            auth_token = auth_header.split(None, 1)[1].strip()
        if not auth_token and isinstance(body, dict):
            auth_token = body.get("_auth")

        try:
            principal = security.authenticate(token=auth_token, source=f"http:{client_ip}")
            security.enforce_scope(principal, security.required_scope_for(tool_name, body.get("kwargs") if isinstance(body, dict) else None))
            decision = security.check_rate_limit(principal, tool_name)
            if not decision.allowed:
                security.audit(
                    event="rate_limited",
                    tool=tool_name,
                    principal=principal,
                    status="rate_limited",
                    transport="http",
                    details={
                        "retry_after_seconds": round(decision.retry_after_seconds, 2),
                        "limit": decision.limit,
                        "window_seconds": decision.window_seconds,
                    },
                )
                raise HTTPException(
                    status_code=429,
                    detail=(
                        f"Rate limit exceeded for {tool_name}. "
                        f"Retry in about {max(1, int(decision.retry_after_seconds))} seconds."
                    ),
                    headers={"Retry-After": str(max(1, int(decision.retry_after_seconds)))}
                )
        except PermissionError as exc:
            security.audit(
                event="auth_failed",
                tool=tool_name,
                principal=None,
                status="auth_failed",
                transport="http",
                details={"error": str(exc)},
            )
            raise HTTPException(status_code=401, detail=str(exc))

        args: List[Any] = body.get("args") or []
        kwargs: Dict[str, Any] = body.get("kwargs") or {}
        try:
            with security.tool_span(tool=tool_name, principal=principal, transport="http"):
                result = fn(*args, **kwargs)
            metrics["invoke_count"] += 1
            return {"result": result}
        except HTTPException:
            raise
        except Exception as exc:  # pragma: no cover - surface errors to caller
            raise HTTPException(status_code=500, detail=str(exc))

    @app.post("/autonomy")
    async def autonomy(body: Dict[str, Any], request: Request):
        """Execute a small plan of tool invocations sequentially.

        Body shape:
          {"plan": [{"tool": "name", "args": [...], "kwargs": {...}}], "_auth": "token"}

        Returns: {"results": [ {"tool": name, "result": ..., "error": ... }, ... ]}
        """
        auth_header = request.headers.get("authorization") or ""
        auth_token = None
        if auth_header.lower().startswith("bearer "):
            auth_token = auth_header.split(None, 1)[1].strip()
        if not auth_token and isinstance(body, dict):
            auth_token = body.get("_auth")

        try:
            principal = security.authenticate(token=auth_token, source="http:autonomy")
        except PermissionError as exc:
            security.audit(
                event="auth_failed",
                tool="autonomy",
                principal=None,
                status="auth_failed",
                transport="http",
                details={"error": str(exc)},
            )
            raise HTTPException(status_code=401, detail=str(exc))

        plan = body.get("plan") or []
        if not isinstance(plan, list):
            raise HTTPException(status_code=400, detail="Plan must be a list")

        key = principal.identity
        now = time.time()
        last = last_run.get(key, 0)
        if now - last < min_interval:
            raise HTTPException(status_code=429, detail="Autonomy calls too frequent")
        last_run[key] = now

        results = []
        async with semaphore:
            for step in plan:
                tool_name = step.get("tool")
                if not tool_name:
                    results.append({"tool": None, "error": "missing tool name"})
                    continue
                fn = TOOLS.get(tool_name)
                if fn is None:
                    results.append({"tool": tool_name, "error": "tool not found"})
                    continue
                args = step.get("args") or []
                kwargs = step.get("kwargs") or {}
                try:
                    security.enforce_scope(principal, security.required_scope_for(tool_name, kwargs))
                    decision = security.check_rate_limit(principal, tool_name)
                    if not decision.allowed:
                        security.audit(
                            event="rate_limited",
                            tool=tool_name,
                            principal=principal,
                            status="rate_limited",
                            transport="http",
                            details={
                                "retry_after_seconds": round(decision.retry_after_seconds, 2),
                                "limit": decision.limit,
                                "window_seconds": decision.window_seconds,
                            },
                        )
                        results.append({
                            "tool": tool_name,
                            "error": f"Rate limit exceeded. Retry in about {max(1, int(decision.retry_after_seconds))} seconds.",
                        })
                        continue
                    with security.tool_span(tool=tool_name, principal=principal, transport="http"):
                        out = fn(*args, **kwargs)
                    results.append({"tool": tool_name, "result": out})
                except PermissionError as exc:
                    security.audit(
                        event="auth_failed",
                        tool=tool_name,
                        principal=principal,
                        status="auth_failed",
                        transport="http",
                        details={"error": str(exc)},
                    )
                    results.append({"tool": tool_name, "error": str(exc)})
                except Exception as exc:
                    results.append({"tool": tool_name, "error": str(exc)})

        metrics["autonomy_count"] += 1
        return {"results": results}

    return app


@mcp.tool()
def emotional_clarity(text: str) -> str:
    """Analyze emotional tone and return a gentle, structured reading."""
    emotion = detect_emotion(text)
    return (
        f"Emotional reading:\n"
        f"- Primary: {emotion['label']} (confidence {emotion['confidence']:.2f})\n"
        f"- Intensity: {emotion['intensity']:.2f}\n"
        f"- Valence: {emotion['valence']:.2f} | Arousal: {emotion['arousal']:.2f}\n"
        f"- Needs: {emotion['needs']}\n\n"
        f"Suggested posture: {emotion['label']}\n"
        f"Detector: {emotion['detector']}"
    )


@mcp.tool()
def dissonance_map(text: str) -> str:
    """Map cognitive dissonance in a situation and suggest a small next step."""
    return map_dissonance(text)


@mcp.tool()
def memory_search(query: str, n_results: int = 5) -> str:
    """Search the bot's long-term memory for relevant past interactions and concepts."""
    results = get_memory().search(query, n_results=n_results)
    if not results:
        return "No matching memories found."
    lines = []
    for document, metadata in results:
        label = (
            metadata.get("concept")
            or metadata.get("title")
            or metadata.get("type", "memory")
        )
        lines.append(f"[{label}]\n{document}")
    return "\n---\n".join(lines)


@mcp.tool()
def document_search(query: str, n_results: int = 5) -> str:
    """Search ingested documents (PDFs, notes, code) for relevant passages."""
    results = get_doc_store().search(query, n_results=n_results)
    if results:
        return format_doc_results(results)
    try:
        from drift.core.anchor_context import search_vault_knowledge

        vault_hits = search_vault_knowledge(query, n_results=n_results)
        if vault_hits:
            return format_doc_results(vault_hits)
    except Exception:
        pass
    return "No matching documents found."


@mcp.tool()
def anchor_vault_status() -> str:
    """Return where the ANCHOR vault and knowledge corpus are mounted on this machine."""
    from drift.core.anchor_context import get_anchor_runtime, format_anchor_vault_prompt_block

    runtime = get_anchor_runtime()
    lines = [format_anchor_vault_prompt_block(), "", "Runtime JSON:", str(runtime)]
    return "\n".join(lines)


@mcp.tool()
def vault_knowledge_search(query: str, n_results: int = 5) -> str:
    """Search the ANCHOR vault knowledge corpus on disk (markdown, notes, code)."""
    from drift.core.anchor_context import search_vault_knowledge

    results = search_vault_knowledge(query, n_results=n_results)
    if not results:
        from drift.core.anchor_context import get_anchor_runtime

        runtime = get_anchor_runtime()
        root = runtime.get("knowledge_root") or "not configured"
        return f"No vault matches for '{query}'. Knowledge root: {root}"
    return format_doc_results(results)


@mcp.tool()
def anchor_knowledge_list() -> str:
    """List structured ANCHOR reference topics from the repo `knowledge/` corpus."""
    from drift.core.anchor_context import format_anchor_repo_knowledge_status, list_anchor_repo_knowledge

    topics = list_anchor_repo_knowledge()
    if not topics:
        return format_anchor_repo_knowledge_status()
    lines = ["ANCHOR knowledge topics", ""]
    for topic in topics:
        tags = ", ".join(topic.get("tags") or [])
        subs = ", ".join(topic.get("subsystems") or [])
        lines.append(f"- {topic['slug']}: {topic['title']}")
        lines.append(f"  subsystems: {subs or '—'} | tags: {tags or '—'}")
    return "\n".join(lines)


@mcp.tool()
def anchor_knowledge_search(query: str, limit: int = 5) -> str:
    """Search structured ANCHOR repo docs (SARIF, evidence models, architecture — not vault mirror)."""
    from drift.core.anchor_context import format_anchor_repo_knowledge_status, search_anchor_repo_knowledge

    hits = search_anchor_repo_knowledge(query, limit=limit)
    if not hits:
        status = format_anchor_repo_knowledge_status()
        return f"No knowledge matches for '{query}'.\n{status}"
    lines = [f"ANCHOR knowledge search: {query}", ""]
    for hit in hits:
        lines.append(f"- [{hit['slug']}] {hit['title']} (score={hit['score']})")
        lines.append(f"  {hit['excerpt']}")
    return "\n".join(lines)


@mcp.tool()
def anchor_knowledge_get(slug: str) -> str:
    """Retrieve one ANCHOR knowledge topic by slug (e.g. sarif, evidence_models, zero_trust)."""
    from drift.core.anchor_context import format_anchor_repo_knowledge_status, get_anchor_repo_knowledge_topic

    payload = get_anchor_repo_knowledge_topic(slug)
    if payload is None:
        return f"Unknown or missing knowledge topic: {slug}\n{format_anchor_repo_knowledge_status()}"
    topic = payload["topic"]
    return f"# {topic['title']} ({topic['slug']})\n\n{payload['content']}"


@mcp.tool()
def anchor_knowledge_refs(subsystem: str) -> str:
    """List ANCHOR knowledge topics linked to a subsystem (e.g. sarif, pipeline, ledger)."""
    from drift.core.anchor_context import format_anchor_repo_knowledge_status, refs_anchor_repo_knowledge

    topics = refs_anchor_repo_knowledge(subsystem)
    if not topics:
        return (
            f"No knowledge topics for subsystem: {subsystem}\n"
            f"{format_anchor_repo_knowledge_status()}"
        )
    lines = [f"ANCHOR knowledge refs for subsystem: {subsystem}", ""]
    for topic in topics:
        lines.append(f"- {topic['slug']}: {topic['title']}")
    return "\n".join(lines)


@mcp.tool()
def todo_list(status: str = "active") -> str:
    """List active or completed goals/todos."""
    goals = get_goals_db().list_goals(status=status, limit=20)
    if not goals:
        return f"No {status} goals."
    lines = []
    for g in goals:
        p = "high" if g.priority == 2 else ("low" if g.priority == 0 else "normal")
        due = f" (due {g.due_at})" if g.due_at else ""
        lines.append(f"[{g.id}] ({p}) {g.title}{due}")
    return "\n".join(lines)


@mcp.tool()
def todo_add(title: str, description: str = "", priority: str = "normal") -> str:
    """Add a new goal or todo. Priority: low, normal, high."""
    pmap = {"low": 0, "normal": 1, "high": 2}
    p = pmap.get(priority.lower(), 1)
    gid = get_goals_db().add_goal(title, description=description, priority=p)
    return f"Added goal [{gid}]: {title}"


@mcp.tool()
def todo_complete(goal_id: str) -> str:
    """Mark a goal as done."""
    if get_goals_db().complete_goal(goal_id):
        return f"Marked [{goal_id}] as done."
    return f"Goal [{goal_id}] not found or already done."


@mcp.tool()
def companion_think(prompt: str) -> str:
    """Ask the INFJ companion to think deeply about a prompt and return its response."""
    return get_brain().think(prompt)


@mcp.tool()
def ingest_document(path: str, tags: str = "") -> str:
    """Ingest a file or directory into the document RAG store."""
    tag_list = [t.strip() for t in tags.split(",") if t.strip()]
    try:
        count = get_doc_store().ingest(path, tags=tag_list)
        return f"Ingested {count} chunks from {path}."
    except Exception as exc:
        return f"Ingest failed: {exc}"


@mcp.tool()
def hive_status() -> str:
    """Return current hive mind node status, consensus state, and drift bridge health."""
    if HiveOrchestrator is None:
        return "HiveOrchestrator not available (hive_mind integration missing)."
    try:
        hive = HiveOrchestrator()
        status = hive.get_status()
        # Demo lightweight consensus using the engine
        hive.consensus.run_simple_consensus(
            topic="Current hive health check",
            proposals=[
                {
                    "node": "spark-0",
                    "role": "PRIMARY",
                    "position": "healthy",
                    "confidence": 0.9,
                },
                {
                    "node": "seed-1",
                    "role": "CRITIC",
                    "position": "healthy",
                    "confidence": 0.75,
                },
            ],
        )
        alive_nodes = (
            hive.list_alive_nodes() if hasattr(hive, "list_alive_nodes") else []
        )
        return (
            f"Hive nodes: {status.get('nodes', 0)} ({status.get('alive', 0)} alive)\n"
            f"Active: {', '.join(alive_nodes[:4]) if alive_nodes else 'none'}\n"
            f"Consensus: {status.get('consensus', 'idle')}\n"
            f"Drift bridge: {status.get('drift_bridge', 'ok')}"
        )
    except Exception as e:
        return f"Hive status unavailable: {e}"


@mcp.tool()
def workspace_snapshot() -> str:
    """Get a snapshot of the current global workspace (active concepts, attention, bindings)."""
    try:
        gw = GlobalWorkspace()
        snap = gw.snapshot()
        concepts = snap.get("concepts", [])[:3]
        return f"Concepts: {len(snap.get('concepts', []))} | Focus: {snap.get('focus') or 'none'}\nTop: {' | '.join(concepts) if concepts else 'empty'}"
    except Exception as e:
        return f"Workspace snapshot unavailable: {e}"


if __name__ == "__main__":
    # Choose transport via MCP_TRANSPORT env var: 'stdio' (default) or 'http'
    transport = os.getenv("MCP_TRANSPORT", "stdio").lower()
    if transport in ("stdio", "stdio_async", "stdio-async"):
        asyncio.run(mcp.run_stdio_async())
    elif transport in ("http", "fastapi", "rest"):
        app = create_http_app()
        host = os.getenv("MCP_HOST", "127.0.0.1")
        port = int(os.getenv("MCP_PORT", "8080"))
        # Run uvicorn directly so this single process can be started by scripts
        uvicorn.run(app, host=host, port=port)
    else:
        print(f"Unknown MCP_TRANSPORT={transport!r}, defaulting to stdio")
        asyncio.run(mcp.run_stdio_async())
