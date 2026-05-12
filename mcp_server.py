"""MCP server exposing the INFJ companion as an external tool.

Supports stdio transport (default) and a simple HTTP transport for local orchestration.
"""

import asyncio
import os
from typing import Any, Dict, List, Optional
import logging
from collections import deque

from mcp.server.fastmcp import FastMCP

from fastapi import FastAPI, HTTPException, Request
import uvicorn
import time

from brain import InfjBrain
from cognition import map_dissonance
from documents import DocumentStore, format_doc_results
from emotion import detect_emotion
from goals import GoalsDB
from memory import InfjMemory
from global_workspace import GlobalWorkspace
from hive_mind.orchestrator import HiveOrchestrator

mcp = FastMCP(
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
""",
)

brain: Optional[InfjBrain] = None
memory: Optional[InfjMemory] = None
goals_db: Optional[GoalsDB] = None
doc_store: Optional[DocumentStore] = None


def get_brain() -> InfjBrain:
    global brain
    if brain is None:
        brain = InfjBrain()
    return brain


def get_memory() -> InfjMemory:
    global memory
    if memory is None:
        memory = InfjMemory()
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

    # Map public tool names to callables
    TOOLS: Dict[str, Any] = {
        "emotional_clarity": emotional_clarity,
        "dissonance_map": dissonance_map,
        "memory_search": memory_search,
        "document_search": document_search,
        "todo_list": todo_list,
        "todo_add": todo_add,
        "todo_complete": todo_complete,
        "companion_think": companion_think,
        "ingest_document": ingest_document,
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

    rate_limit_per_min = int(os.getenv("MCP_RATE_LIMIT_PER_MIN", "60"))
    rate_buckets: Dict[str, deque] = {}

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

    # start background worker (modern asyncio)
    try:
        asyncio.create_task(schedule_worker())
    except RuntimeError:
        # event loop not running yet; uvicorn will start it later
        pass

    @app.get("/health")
    def health() -> Dict[str, str]:
        return {"status": "ok", "transport": "http"}

    @app.get("/metrics")
    def metrics_endpoint() -> Dict[str, Any]:
        return {
            "metrics": metrics,
            "rate_limit_per_min": rate_limit_per_min,
            "scheduled": len(scheduled),
        }

    def check_rate_limit(client_ip: str) -> None:
        now = time.time()
        window_start = now - 60
        q = rate_buckets.get(client_ip)
        if q is None:
            q = deque()
            rate_buckets[client_ip] = q
        while q and q[0] < window_start:
            q.popleft()
        if len(q) >= rate_limit_per_min:
            raise HTTPException(status_code=429, detail="Too many requests")
        q.append(now)

    @app.post("/invoke/{tool_name}")
    async def invoke(tool_name: str, body: Dict[str, Any], request: Request):
        # Rate limit by client IP
        client_ip = request.client.host if request.client else "unknown"
        check_rate_limit(client_ip)
        fn = TOOLS.get(tool_name)
        if fn is None:
            raise HTTPException(status_code=404, detail=f"Tool {tool_name} not found")

        # Authentication: prefer Authorization header Bearer <token>
        auth_header = request.headers.get("authorization")
        auth_token = None
        if auth_header and auth_header.lower().startswith("bearer "):
            auth_token = auth_header.split(None, 1)[1]
        # fallback to body._auth for tests/legacy
        if not auth_token and isinstance(body, dict):
            auth_token = body.get("_auth")

        if token:
            if not auth_token:
                raise HTTPException(status_code=401, detail="Missing auth token")
            if auth_token != token:
                raise HTTPException(status_code=403, detail="Invalid auth token")

        args: List[Any] = body.get("args") or []
        kwargs: Dict[str, Any] = body.get("kwargs") or {}
        try:
            result = fn(*args, **kwargs)
            metrics["invoke_count"] += 1
            return {"result": result}
        except Exception as exc:  # pragma: no cover - surface errors to caller
            raise HTTPException(status_code=500, detail=str(exc))

    @app.post("/autonomy")
    async def autonomy(body: Dict[str, Any], request: Request):
        """Execute a small plan of tool invocations sequentially.

        Body shape:
          {"plan": [{"tool": "name", "args": [...], "kwargs": {...}}], "_auth": "token"}

        Returns: {"results": [ {"tool": name, "result": ..., "error": ... }, ... ]}
        """
        # Authentication header
        auth_header = request.headers.get("authorization")
        auth_token = None
        if auth_header and auth_header.lower().startswith("bearer "):
            auth_token = auth_header.split(None, 1)[1]
        if not auth_token and isinstance(body, dict):
            auth_token = body.get("_auth")

        if token:
            if not auth_token:
                raise HTTPException(status_code=401, detail="Missing auth token")
            if auth_token != token:
                raise HTTPException(status_code=403, detail="Invalid auth token")

        plan = body.get("plan") or []
        if not isinstance(plan, list):
            raise HTTPException(status_code=400, detail="Plan must be a list")

        # Rate-limit / cooldown per token (or 'anon')
        key = auth_token or "anon"
        now = time.time()
        last = last_run.get(key, 0)
        if now - last < min_interval:
            raise HTTPException(status_code=429, detail="Autonomy calls too frequent")
        last_run[key] = now

        # Execute the entire plan under concurrency semaphore
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
                    out = fn(*args, **kwargs)
                    results.append({"tool": tool_name, "result": out})
                except Exception as exc:
                    results.append({"tool": tool_name, "error": str(exc)})

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
    return format_doc_results(results)


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
    try:
        hive = HiveOrchestrator()
        status = hive.get_status()
        # Demo lightweight consensus using the engine
        demo = hive.consensus.run_simple_consensus(
            topic="Current hive health check",
            proposals=[
                {"node": "spark-0", "role": "PRIMARY", "position": "healthy", "confidence": 0.9},
                {"node": "seed-1", "role": "CRITIC", "position": "healthy", "confidence": 0.75},
            ],
        )
        return (
            f"Hive nodes: {status.get('nodes', 0)}\n"
            f"Consensus: {status.get('consensus', 'idle')}\n"
            f"Drift bridge: {status.get('drift_bridge', 'ok')}\n"
            f"Demo consensus: {demo['decision']} (agreement {demo['agreement']})"
        )
    except Exception as e:
        return f"Hive status unavailable: {e}"


@mcp.tool()
def workspace_snapshot() -> str:
    """Get a snapshot of the current global workspace (active concepts, attention, bindings)."""
    try:
        gw = GlobalWorkspace()
        snap = gw.snapshot()
        return f"Active concepts: {len(snap.get('concepts', []))}\nAttention focus: {snap.get('focus', 'none')}\nBindings: {snap.get('bindings', 0)}"
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
