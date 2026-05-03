"""MCP server exposing the INFJ companion as an external tool."""
import asyncio
import json
from mcp.server.fastmcp import FastMCP

from brain import InfjBrain
from cognition import detect_dissonance, map_dissonance
from documents import DocumentStore, format_doc_results
from emotion import detect_emotion
from goals import GoalsDB
from memory import InfjMemory

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

brain = InfjBrain()
memory = InfjMemory()
goals_db = GoalsDB()
doc_store = DocumentStore()


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
    results = memory.search(query, n_results=n_results)
    if not results:
        return "No matching memories found."
    lines = []
    for document, metadata in results:
        label = metadata.get("concept") or metadata.get("title") or metadata.get("type", "memory")
        lines.append(f"[{label}]\n{document}")
    return "\n---\n".join(lines)


@mcp.tool()
def document_search(query: str, n_results: int = 5) -> str:
    """Search ingested documents (PDFs, notes, code) for relevant passages."""
    results = doc_store.search(query, n_results=n_results)
    return format_doc_results(results)


@mcp.tool()
def todo_list(status: str = "active") -> str:
    """List active or completed goals/todos."""
    goals = goals_db.list_goals(status=status, limit=20)
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
    gid = goals_db.add_goal(title, description=description, priority=p)
    return f"Added goal [{gid}]: {title}"


@mcp.tool()
def todo_complete(goal_id: str) -> str:
    """Mark a goal as done."""
    if goals_db.complete_goal(goal_id):
        return f"Marked [{goal_id}] as done."
    return f"Goal [{goal_id}] not found or already done."


@mcp.tool()
def companion_think(prompt: str) -> str:
    """Ask the INFJ companion to think deeply about a prompt and return its response."""
    return brain.think(prompt)


@mcp.tool()
def ingest_document(path: str, tags: str = "") -> str:
    """Ingest a file or directory into the document RAG store."""
    tag_list = [t.strip() for t in tags.split(",") if t.strip()]
    try:
        count = doc_store.ingest(path, tags=tag_list)
        return f"Ingested {count} chunks from {path}."
    except Exception as exc:
        return f"Ingest failed: {exc}"


if __name__ == "__main__":
    # Default to stdio transport for MCP compatibility
    asyncio.run(mcp.run_stdio_async())
