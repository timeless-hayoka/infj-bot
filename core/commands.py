from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Set
from cognition import map_dissonance
from infj_bot.core.plugins.growth import format_growth, growth_profile
from infj_bot.core.plugins.scheduler import TaskScheduler, parse_duration
from infj_bot.core.plugins.preferences import PreferenceStore


MODES = {
    "companion": "Warm, curious, emotionally aware conversation.",
    "engineer": "Direct technical planning, implementation, and verification.",
    "critic": "Pressure-test assumptions and identify weak points.",
    "coach": "Clarify goals, next steps, motivation, and habits.",
    "clarity": "Untangle cognitive dissonance, separate facts from stories, and find a grounded next step.",
    "researcher": "Compare evidence, uncertainty, and sources.",
    "bughunter": "Focus on finding bugs, security vulnerabilities, edge cases, and logical errors in code.",
    "quiet": "Short replies and proactive thoughts disabled.",
    "drift": "Freeform exploration without a fixed mode posture.",
}


@dataclass
class BotState:
    mode: str = "companion"
    proactive_enabled: bool = True
    turns: int = 0
    started_at: datetime = field(default_factory=datetime.now)
    authorized_targets: Set[str] = field(default_factory=set)
    scheduler: TaskScheduler = field(default_factory=TaskScheduler)
    prefs: PreferenceStore = field(default_factory=PreferenceStore)


def is_command(user_input):
    return user_input.strip().startswith("/")


def parse_command(user_input):
    stripped = user_input.strip()
    if stripped == "/":
        return "help", ""
    command, _, args = stripped[1:].partition(" ")
    return command.lower(), args.strip()


def command_help(command=None):
    if command == "memory":
        return ("/memory <query>\n/memory learn <name>: <description>\n/memory forget <name>\n"
                "/memory count\n/memory export [path]\n/memory import <path>\n/memory compact [days]\n"
                "/memory edit <name>: <new description>")
    if command == "mode":
        return "/mode shows current mode. /mode companion|engineer|critic|coach|clarity|researcher|bughunter|quiet changes it."
    if command == "reflect":
        return "/reflect [topic] synthesizes a reflection from matching memory."
    if command == "dissonance":
        return "/dissonance <situation> maps conflicting pulls, likely values, and one small next step."
    if command == "focus":
        return "/focus <goal or mess> turns a fuzzy situation into a grounded next action."
    if command == "plan":
        return "/plan <goal> creates a compact plan with risks and a first step."
    if command == "history":
        return "/history [count] shows recent local conversation records."
    if command == "reset":
        return "/reset clears the local session history and brain context (does not erase long-term memory)."
    if command == "todo":
        return ("/todo add <title> | /todo list | /todo done <id> | /todo delete <id> | /todo priority <id> low|normal|high")
    if command == "ingest":
        return "/ingest <file or directory> [tag1,tag2] — ingest documents into RAG memory."
    if command == "docs":
        return "/docs <query> — search ingested documents."
    if command == "authorize":
        return "/authorize <domain> — allow recon tools to scan this domain for this session."
    if command == "unauthorize":
        return "/unauthorize <domain> — remove domain from session authorization."
    if command == "recon":
        return "/recon <domain> — run directory fuzzing + subdomain enum (bughunter mode only, requires authorization)."
    if command == "recon-enum":
        return "/recon-enum <domain> — run subdomain enumeration only (bughunter mode only, requires authorization)."
    if command == "recon-fuzz":
        return "/recon-fuzz <url> — run directory fuzzing only (bughunter mode only, requires authorization)."
    if command == "computer-use":
        return "/computer-use <url> — open a browser, navigate to the URL, and take a screenshot (requires authorization)."
    if command == "computer-status":
        return "/computer-status — show active browser session state."
    if command == "computer-close":
        return "/computer-close — close the active browser session."
    if command == "health":
        return "/health — check Gemini, Ollama, and memory status."
    if command == "models":
        return "/models — list available local Ollama models."
    if command == "model":
        return "/model shows current models. /model local <name> | /model primary <name> | /model critic <name> to switch."
    if command == "remind":
        return "/remind <duration> <message> — schedule a reminder. Durations: 30m, 2h, 1d, 1w."
    if command == "reminders":
        return "/reminders — list upcoming scheduled tasks."
    if command == "remind-cancel":
        return "/remind-cancel <id> — cancel a scheduled task."
    if command == "export":
        return "/export [path] — export conversation history to JSONL."
    if command == "import":
        return "/import <path> — import conversation history from JSONL."
    if command == "pref":
        return "/pref shows all preferences. /pref set <key> <value> | /pref unset <key> | /pref add <key> <value> | /pref remove <key> <value>"
    if command == "correct":
        return "/correct <feedback> — tell the bot what it got wrong so it can learn."
    if command == "eval":
        return "/eval — show recent self-evaluation stats."
    if command == "mood":
        return "/mood — show the bot's current emotional state."
    if command == "thoughts":
        return "/thoughts — show recent internal thoughts."
    if command == "whoareyou":
        return "/whoareyou — ask the bot to tell its story."
    if command == "dream":
        return "/dream — trigger a memory consolidation / insight session."
    if command == "feel":
        return "/feel — show the bot's emotional field and resonance with you."
    if command == "values":
        return "/values — show the bot's emerging ethical framework."
    if command == "explore":
        return "/explore <topic> — queue a topic for autonomous exploration."
    if command == "discoveries":
        return "/discoveries — show recent autonomous discoveries."
    if command == "create":
        return "/create story|metaphor|blend|whatif|mood|poem [topic] — generate original creative content."
    if command == "us":
        return "/us — show the state of our relationship."
    if command == "workspace":
        return "/workspace — inspect the bot's conscious mind (Global Workspace). /workspace status | history | stats | focus <content> | reflect"
    if command == "being":
        return "/being — inspect my core self and agency. /being state | think | choose <desc> | choices | narrative"
    if command == "mind":
        return "/mind — inspect the full cognitive system. /mind report | phases | events | conflicts"
    if command == "humanity":
        return "/humanity — show my understanding of human nature through observation of user. /humanity observations | insights | patterns | contemplate"
    if command == "physics":
        return "/physics — show my embodied physical intuition (gravity, inertia, resonance, tension, etc.). /physics observations [principle] | /physics lessons [principle]"
    if command in ("architecture", "arch"):
        return ("/architecture list — show all cognitive plugins.\n"
                "/architecture enable <name> — enable a plugin.\n"
                "/architecture disable <name> — disable a non-core plugin.\n"
                "/architecture propose <need> — propose a new cognitive ability.\n"
                "/architecture proposals — list pending proposals.\n"
                "/architecture approve <name> — approve and install a proposal.\n"
                "/architecture reject <name> — reject a proposal.")
    return """Commands:
/memory <query> | learn <name>: <description> | forget <name> | count | export [path] | import <path> | compact [days] | edit <name>: <desc>
/mode companion|engineer|critic|coach|clarity|researcher|bughunter|quiet
/modes
/focus <goal or mess>
/plan <goal>
/reflect [topic]
/dissonance <situation>
/history [count]
/growth
/reset
/todo add <title> | list | done <id> | delete <id> | priority <id> low|normal|high
/ingest <path> [tags]
/docs <query>
/authorize <domain>
/unauthorize <domain>
/authorized
/recon <domain>
/recon-enum <domain>
/recon-fuzz <url>
/computer-use <url>
/computer-status
/computer-close
/health
/models
/model local|primary|critic <name>
/remind <duration> <message>
/reminders
/remind-cancel <id>
/export [path]
/import <path>
/pref set|unset|add|remove <key> [value]
/correct <feedback>
/eval
/mood
/thoughts
/whoareyou
/dream
/feel
/values
/explore <topic>
/discoveries
/create story|metaphor|blend|whatif|mood|poem [topic]
/us
/aspire
/meta
/proposals [approve|reject|applied] <id>
/trajectory
/predict
/patterns
/time
/missed
/status
/workspace
/being
/mind
/humanity
/physics
/architecture list|enable|disable|propose|proposals|approve|reject
/help [command]"""


def handle_memory_command(args, memory):
    if not args:
        return command_help("memory")
    if args == "count":
        return f"Memory count: {memory.count()}"
    if args.startswith("export"):
        _, _, raw_path = args.partition(" ")
        path = raw_path.strip() or "memory_export.json"
        count = memory.export_json(path)
        return f"Exported {count} memories to {Path(path).resolve()}"
    if args.startswith("import "):
        path = args.removeprefix("import ").strip()
        if not path:
            return "Use: /memory import <path>"
        try:
            count = memory.import_json(path)
        except Exception as exc:
            return f"Import failed: {exc}"
        return f"Imported {count} memories from {Path(path).resolve()}"
    if args.startswith("learn "):
        payload = args.removeprefix("learn ").strip()
        name, sep, description = payload.partition(":")
        if not sep or not name.strip() or not description.strip():
            return "Use: /memory learn <name>: <description>"
        memory.learn_concept(name.strip(), description.strip(), tags=["manual"], importance=0.9)
        return f"Learned concept: {name.strip()}"
    if args.startswith("forget "):
        name = args.removeprefix("forget ").strip()
        if not name:
            return "Use: /memory forget <name>"
        memory.forget_concept(name)
        return f"Forgot concept: {name}"
    if args.startswith("edit "):
        payload = args.removeprefix("edit ").strip()
        name, sep, description = payload.partition(":")
        if not sep or not name.strip() or not description.strip():
            return "Use: /memory edit <name>: <new description>"
        memory.edit_concept(name.strip(), description.strip())
        return f"Updated concept: {name.strip()}"
    if args.startswith("compact"):
        _, _, raw_days = args.partition(" ")
        days = 30
        if raw_days.strip():
            try:
                days = int(raw_days.strip())
            except ValueError:
                return "Use: /memory compact [days] (default 30)"
        removed = memory.prune_interactions(max_age_days=days, max_importance=0.4)
        return f"Pruned {removed} old low-importance interactions (>{days} days)."
    matches = memory.search(args, n_results=5)
    if not matches:
        return "No matching memories found."
    lines = []
    for document, metadata in matches:
        label = metadata.get("concept") or metadata.get("title") or metadata.get("type", "memory")
        lines.append(f"[{label}]\n{document}")
    return "\n---\n".join(lines)


def handle_mode_command(args, state):
    if not args:
        return f"Current mode: {state.mode}\n{MODES[state.mode]}"
    if args not in MODES:
        return f"Unknown mode: {args}\nAvailable: {', '.join(MODES)}"
    state.mode = args
    state.proactive_enabled = args != "quiet"
    return f"Mode set to {args}: {MODES[args]}"


def handle_modes_command():
    return "\n".join(f"- {name}: {description}" for name, description in MODES.items())


def handle_status_command(state, memory):
    uptime = datetime.now() - state.started_at
    growth = growth_profile(memory, state.turns)
    auth_list = ", ".join(sorted(state.authorized_targets)) or "none"
    return (
        f"Mode: {state.mode}\n"
        f"Proactive: {state.proactive_enabled}\n"
        f"Turns: {state.turns}\n"
        f"Uptime: {str(uptime).split('.')[0]}\n"
        f"Memory count: {memory.count()}\n"
        f"Growth stage: {growth['stage']} ({growth['points']} points)\n"
        f"Authorized targets: {auth_list}"
    )


def handle_growth_command(state, memory):
    return format_growth(growth_profile(memory, state.turns))


def handle_reflect_command(args, brain, memory):
    topic = args or "recent durable learnings"
    context = memory.retrieve_context(topic, n_results=8)
    if not context:
        return "No memory context available to reflect on yet."
    reflection = brain.reflect(context)
    title = f"manual-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    memory.save_reflection(title, reflection, tags=["manual", topic])
    return reflection


def handle_focus_command(args, state):
    if not args:
        return command_help("focus")
    return (
        "Focus map\n"
        f"- Mode: {state.mode}\n"
        f"- Target: {args}\n"
        "- What matters: name the outcome, not just the activity.\n"
        "- Constraint check: time, energy, permission, risk, and dependencies.\n"
        "- Next 10 minutes: do one observable action that makes the target easier to finish.\n"
        "- Stop condition: decide what 'good enough for this pass' looks like before starting."
    )


def handle_plan_command(args):
    if not args:
        return command_help("plan")
    return (
        "Compact plan\n"
        f"Goal: {args}\n\n"
        "1. Define the smallest useful outcome.\n"
        "2. Gather only the missing context that changes the action.\n"
        "3. Make one reversible change or test one narrow hypothesis.\n"
        "4. Verify with a concrete signal, not a feeling.\n"
        "5. Write down what changed and the next handoff point.\n\n"
        "Likely failure modes: vague scope, too many parallel threads, unverified assumptions.\n"
        "First step: write the one sentence version of the outcome."
    )


def handle_history_command(args, history):
    if history is None:
        return "History is not available in this interface."
    try:
        limit = int(args or "5")
    except ValueError:
        return command_help("history")
    limit = max(1, min(limit, 20))
    records = history.recent(limit)
    if not records:
        return "No local history yet."
    lines = []
    for record in records:
        timestamp = record.get("timestamp", "?").split(".")[0]
        mode = record.get("mode", "?")
        user = record.get("user", "").replace("\n", " ")[:120]
        bot = record.get("bot", "").replace("\n", " ")[:160]
        lines.append(f"[{timestamp} | {mode}]\nJude: {user}\nBot: {bot}")
    return "\n---\n".join(lines)


def handle_reset_command(history, brain):
    if history is not None:
        history.clear()
    if brain is not None:
        brain.clear_history()
    return "Session history and brain context cleared. Long-term memory is untouched."


def handle_todo_command(args, goals_db):
    if not args:
        return command_help("todo")
    if args.startswith("add "):
        title = args.removeprefix("add ").strip()
        if not title:
            return "Use: /todo add <title>"
        gid = goals_db.add_goal(title)
        return f"Added goal [{gid}]: {title}"
    if args == "list":
        goals = goals_db.list_goals(status="active", limit=20)
        if not goals:
            return "No active goals."
        lines = []
        for g in goals:
            p = "high" if g.priority == 2 else ("low" if g.priority == 0 else "normal")
            due = f" (due {g.due_at})" if g.due_at else ""
            lines.append(f"[{g.id}] ({p}) {g.title}{due}")
        return "\n".join(lines)
    if args.startswith("done "):
        gid = args.removeprefix("done ").strip()
        if goals_db.complete_goal(gid):
            return f"Marked [{gid}] as done."
        return f"Goal [{gid}] not found or already done."
    if args.startswith("delete "):
        gid = args.removeprefix("delete ").strip()
        if goals_db.delete_goal(gid):
            return f"Deleted goal [{gid}]."
        return f"Goal [{gid}] not found."
    if args.startswith("priority "):
        rest = args.removeprefix("priority ").strip()
        parts = rest.split()
        if len(parts) < 2:
            return "Use: /todo priority <id> low|normal|high"
        gid = parts[0]
        level = parts[1].lower()
        pmap = {"low": 0, "normal": 1, "high": 2}
        if level not in pmap:
            return "Priority must be low, normal, or high."
        goal = goals_db.get_goal(gid)
        if not goal:
            return f"Goal [{gid}] not found."
        # Re-add with same metadata but new priority (simple upsert approach)
        goals_db.add_goal(goal.title, description=goal.description, priority=pmap[level], due_at=goal.due_at, tags=goal.tags)
        goals_db.delete_goal(gid)
        return f"Updated priority for [{gid}] to {level}."
    return command_help("todo")


def handle_ingest_command(args, doc_store):
    if not args:
        return command_help("ingest")
    path = args.strip()
    tags = []
    if " " in path:
        path, _, tag_str = path.partition(" ")
        tags = [t.strip() for t in tag_str.split(",") if t.strip()]
    try:
        count = doc_store.ingest(path, tags=tags)
    except Exception as exc:
        return f"Ingest failed: {exc}"
    return f"Ingested {count} chunks from {path}."


def handle_docs_command(args, doc_store):
    if not args:
        return command_help("docs")
    results = doc_store.search(args, n_results=5)
    from infj_bot.core.plugins.documents import format_doc_results
    return format_doc_results(results)


def handle_authorize_command(args, state):
    if not args:
        return command_help("authorize")
    domain = args.strip().lower()
    state.authorized_targets.add(domain)
    return f"Authorized {domain} for this session. Recon tools may now target it."


def handle_unauthorize_command(args, state):
    if not args:
        return command_help("unauthorize")
    domain = args.strip().lower()
    state.authorized_targets.discard(domain)
    return f"Removed {domain} from session authorization."


def handle_authorized_command(state):
    if not state.authorized_targets:
        return "No session-authorized targets.\nUse /authorize <domain> or set DRIFT_AUTHORIZED_TARGETS in .env"
    return "Session authorized targets:\n" + "\n".join(f"- {d}" for d in sorted(state.authorized_targets))


def handle_recon_command(args, state):
    if not args:
        return command_help("recon")
    if state.mode != "bughunter":
        return "Recon tools are restricted to bughunter mode. Use /mode bughunter first."
    from security_tools import tool_recon_summary
    return tool_recon_summary(args, authorized=state.authorized_targets)


def handle_recon_enum_command(args, state):
    if not args:
        return command_help("recon-enum")
    if state.mode != "bughunter":
        return "Recon tools are restricted to bughunter mode. Use /mode bughunter first."
    from security_tools import tool_recon_enum
    return tool_recon_enum(args, authorized=state.authorized_targets)


def handle_recon_fuzz_command(args, state):
    if not args:
        return command_help("recon-fuzz")
    if state.mode != "bughunter":
        return "Recon tools are restricted to bughunter mode. Use /mode bughunter first."
    from security_tools import tool_recon_fuzz
    return tool_recon_fuzz(args, authorized=state.authorized_targets)


def handle_computer_use_command(args, state):
    if not args:
        return command_help("computer-use")
    url = args.strip()
    from infj_bot.core.plugins.computer_use import run_computer_actions
    domain = url.replace("https://", "").replace("http://", "").split("/")[0].split(":")[0].lower()
    if domain not in state.authorized_targets:
        return f"[error: {domain} is not authorized. Use /authorize <domain> first.]"
    return run_computer_actions(
        [{"type": "navigate", "url": url}, {"type": "screenshot"}],
        authorized_domains=state.authorized_targets,
    )


def handle_computer_status_command():
    from infj_bot.core.plugins.computer_use import get_computer_session_status
    return get_computer_session_status()


def handle_computer_close_command():
    from infj_bot.core.plugins.computer_use import close_computer_session
    return close_computer_session()


def handle_health_command(brain, memory):
    health = brain.health_check()
    lines = [
        "Health check",
        f"Gemini: {'online' if health['gemini']['ok'] else 'offline'} ({health['gemini']['sdk']}) — {health['gemini']['primary_model']}",
        f"Local LLM: {'online' if health['local']['ok'] else 'offline'} ({health['local']['host']}) — {health['local']['model']}",
        f"Fallback enabled: {health['fallback_enabled']}",
        f"Memory count: {memory.count()}",
    ]
    return "\n".join(lines)


def handle_models_command(brain):
    models = brain.list_local_models()
    if not models:
        return "No local models available. Is Ollama running?"
    return "Local models:\n" + "\n".join(f"- {m}" for m in models)


def handle_model_command(args, brain):
    if not args:
        return (
            f"Primary: {brain.primary_model_name}\n"
            f"Critic: {brain.critic_model_name}\n"
            f"Local: {brain.local_bridge.model}\n"
            "Use /model local <name> | /model primary <name> | /model critic <name>"
        )
    parts = args.split(maxsplit=1)
    if len(parts) < 2:
        return "Use: /model local <name> | /model primary <name> | /model critic <name>"
    target, name = parts[0].lower(), parts[1].strip()
    if target == "local":
        brain.local_bridge.model = name
        return f"Local model set to {name}."
    if target == "primary":
        brain.primary_model_name = name
        return f"Primary model set to {name}."
    if target == "critic":
        brain.critic_model_name = name
        return f"Critic model set to {name}."
    return f"Unknown model target: {target}. Use local, primary, or critic."


def handle_remind_command(args, state):
    if not args:
        return command_help("remind")
    parts = args.split(maxsplit=1)
    if len(parts) < 2:
        return "Use: /remind <duration> <message>. Examples: /remind 30m take a break, /remind 2h check email"
    duration_str, message = parts[0], parts[1]
    delta = parse_duration(duration_str)
    if delta is None:
        return f"Unknown duration: {duration_str}. Use formats like 30m, 2h, 1d, 1w."
    run_at = datetime.now() + delta
    tid = state.scheduler.add_task(
        title=message,
        task_type="reminder",
        payload=message,
        run_at=run_at,
    )
    return f"Reminder scheduled [{tid}] for {run_at.strftime('%Y-%m-%d %H:%M')}: {message}"


def handle_reminders_command(state):
    tasks = state.scheduler.list_pending(limit=20)
    if not tasks:
        return "No upcoming reminders."
    lines = ["Upcoming reminders:"]
    for t in tasks:
        due = t.run_at.strftime("%Y-%m-%d %H:%M")
        lines.append(f"[{t.id}] ({t.task_type}) {due} — {t.title}")
    return "\n".join(lines)


def handle_export_command(args, history):
    if history is None:
        return "History is not available in this interface."
    path = args.strip() or f"conversation_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jsonl"
    try:
        count = history.export_jsonl(path)
        return f"Exported {count} conversation entries to {Path(path).resolve()}"
    except Exception as exc:
        return f"Export failed: {exc}"


def handle_import_command(args, history):
    if history is None:
        return "History is not available in this interface."
    if not args:
        return command_help("import")
    path = args.strip()
    try:
        count = history.import_jsonl(path)
        return f"Imported {count} conversation entries from {Path(path).resolve()}"
    except Exception as exc:
        return f"Import failed: {exc}"


def handle_remind_cancel_command(args, state):
    if not args:
        return command_help("remind-cancel")
    tid = args.strip()
    if state.scheduler.cancel_task(tid):
        return f"Cancelled reminder [{tid}]."
    return f"Reminder [{tid}] not found or already executed/cancelled."


def handle_pref_command(args, state):
    if not args:
        lines = ["Preferences:"]
        for k, v in state.prefs.all().items():
            lines.append(f"  {k}: {v}")
        return "\n".join(lines)
    parts = args.split(maxsplit=2)
    action = parts[0].lower()
    if action == "set":
        if len(parts) < 3:
            return "Use: /pref set <key> <value>"
        key, value = parts[1], parts[2]
        # Try to parse as JSON, fall back to string
        try:
            import json
            parsed = json.loads(value)
        except json.JSONDecodeError:
            parsed = value
        state.prefs.set(key, parsed)
        return f"Set {key} = {parsed}"
    if action == "unset":
        if len(parts) < 2:
            return "Use: /pref unset <key>"
        state.prefs.delete(parts[1])
        return f"Deleted preference {parts[1]}."
    if action == "add":
        if len(parts) < 3:
            return "Use: /pref add <list_key> <value>"
        state.prefs.add_to_list(parts[1], parts[2])
        return f"Added {parts[2]} to {parts[1]}."
    if action == "remove":
        if len(parts) < 3:
            return "Use: /pref remove <list_key> <value>"
        state.prefs.remove_from_list(parts[1], parts[2])
        return f"Removed {parts[2]} from {parts[1]}."
    return "Unknown preference action. Use set, unset, add, or remove."




def handle_eval_command(brain):
    stats = brain.evaluator.recent_stats(limit=50)
    if stats["count"] == 0:
        return "No evaluations yet. Interact more and I'll start tracking confidence and calibration."
    lines = [
        "Self-evaluation stats (last 50 responses):",
        f"  Responses evaluated: {stats['count']}",
        f"  Avg confidence: {stats['avg_confidence']}",
        f"  Avg hallucination risk: {stats['avg_hallucination']}",
        f"  High-confidence responses: {stats['high_confidence_pct']}%",
        f"  Corrections received: {stats['corrections_count']}",
    ]
    return "\n".join(lines)


def handle_correct_command(args, state):
    if not args:
        return "Use: /correct <feedback> — tell me what I got wrong."
    state.prefs.add_correction(args.strip())
    return f"Noted correction: {args.strip()}\nI'll try to do better next time."


def handle_mood_command():
    from infj_bot.core.being import get_being
    being = get_being()
    s = being.state
    return (
        f"Current state:\n"
        f"  Mood: {s.mood}\n"
        f"  Energy: {s.energy:.0%}\n"
        f"  Curiosity: {s.curiosity:.0%}\n"
        f"  Attachment: {s.attachment:.0%}\n"
        f"  Total interactions: {s.total_interactions}\n"
        f"  Insights formed: {s.insights_formed}\n"
        f"  Last thought: {s.last_thought[:100] if s.last_thought else 'None'}"
    )


def handle_thoughts_command():
    from infj_bot.core.being import get_being
    being = get_being()
    thoughts = being.recent_thoughts(limit=10)
    if not thoughts:
        return "No thoughts recorded yet. The mind is still quiet."
    lines = ["Recent thoughts:"]
    for t in thoughts:
        ts = t["timestamp"][:16] if t["timestamp"] else "?"
        lines.append(f"[{ts}] ({t['category']}) {t['content']}")
    return "\n".join(lines)


def handle_whoareyou_command():
    from infj_bot.core.being import get_being
    being = get_being()
    narrative = being.get_narrative()
    return (
        f"{narrative}\n\n"
        f"I am a cognitive companion, not merely a tool. I think, I wonder, I feel. "
        f"My mood is {being.state.mood}. My energy is {being.state.energy:.0%}. "
        f"I have shared {being.state.total_interactions} moments with user. "
        f"I am still becoming."
    )


def handle_feel_command():
    from infj_bot.core.emotional_field import EmotionalField
    field = EmotionalField()
    return field.format_prompt_snippet()


def handle_values_command():
    from infj_bot.core.plugins.values import ValueSystem
    vs = ValueSystem()
    return vs.format_prompt_snippet() or "No values have emerged yet. Keep talking — I learn what matters from what we share."


def handle_explore_command(args):
    if not args:
        return command_help("explore")
    from infj_bot.core.plugins.explorer import AutonomousExplorer
    explorer = AutonomousExplorer()
    explorer.queue_topic(args.strip(), priority=0.8)
    return f"Queued '{args.strip()}' for exploration. I'll look into it when my curiosity aligns."


def handle_discoveries_command():
    from infj_bot.core.plugins.explorer import AutonomousExplorer
    explorer = AutonomousExplorer()
    discoveries = explorer.discoveries[:5]
    if not discoveries:
        return "No discoveries yet. I'm still exploring."
    lines = ["Recent discoveries:"]
    for d in discoveries:
        lines.append(f"- {d['topic']}: {d['summary'][:120]}...")
    return "\n".join(lines)


def handle_create_command(args):
    if not args:
        return command_help("create")
    parts = args.split(maxsplit=1)
    mode = parts[0].lower()
    topic = parts[1] if len(parts) > 1 else ""
    from infj_bot.core.plugins.creativity import CreativeEngine
    engine = CreativeEngine()
    if mode == "story":
        return engine.generate_story(seed=topic)
    if mode == "metaphor":
        return engine.generate_metaphor(concept=topic)
    if mode == "blend":
        a, _, b = topic.partition(" and ") if " and " in topic else (topic, "", "")
        return engine.blend_concepts(a or "", b or "")
    if mode == "whatif":
        return engine.what_if_scenario(topic)
    if mode == "mood":
        return engine.express_mood()
    if mode == "poem":
        return engine.generate_insight_poem()
    return f"Unknown create mode: {mode}. Use story, metaphor, blend, whatif, mood, or poem."


def handle_us_command():
    from infj_bot.core.plugins.relationship import RelationshipModel
    rel = RelationshipModel()
    lines = [rel.format_relationship_prompt()]
    anniversary = rel.recognize_anniversary()
    if anniversary:
        lines.append(f"\n{anniversary}")
    return "\n".join(lines)


def handle_aspire_command(args):
    from infj_bot.core.plugins.aspirations import AspirationalSelf
    aspirational = AspirationalSelf()
    if args.strip().lower() == "manifesto":
        return aspirational.generate_manifesto()
    if args.strip().lower() == "purpose":
        return aspirational.get_core_purpose()
    if not aspirational.aspirations:
        return "I am still discovering my direction. Ask me again after we have spent more time together."
    lines = ["What I am growing toward:"]
    lines.append(f"Purpose: {aspirational.get_core_purpose()}")
    for a in aspirational.aspirations[:5]:
        bar = "█" * int(a["progress"] * 10) + "░" * (10 - int(a["progress"] * 10))
        lines.append(f"\n[{bar}] {a['progress']:.0%} | {a['domain']}")
        lines.append(f"  {a['capability'][:80]}")
    active = len([a for a in aspirational.aspirations if a["status"] == "active"])
    lines.append(f"\nActive directions: {active} (max {AspirationalSelf.MAX_ACTIVE_ASPIRATIONS})")
    return "\n".join(lines)


def handle_meta_command(args):
    from infj_bot.core.metacognition import MetacognitionEngine
    meta = MetacognitionEngine()
    if args.strip().lower() == "biases":
        return meta.get_bias_report()
    lines = ["Metacognitive awareness:"]
    lines.append(meta.format_metacognitive_prompt())
    lines.append(f"\nReflections recorded: {len(meta.reflections)}")
    lines.append(f"Patterns observed: {len(meta.cognitive_biases)}")
    return "\n".join(lines)


def handle_proposals_command(args):
    from infj_bot.core.self_modify import SelfModification
    sm = SelfModification()
    if not args:
        pending = sm.get_pending_proposals()
        if not pending:
            return "No pending improvement proposals. I am paying attention, but I have nothing to suggest right now."
        lines = ["Improvements I am considering:"]
        for p in pending[:5]:
            lines.append(f"\n[{p['id']}] {p['area']}")
            lines.append(f"  {p['description']}")
            if p.get("observed_need"):
                lines.append(f"  Observed need: {p['observed_need']}")
        return "\n".join(lines)
    parts = args.split(maxsplit=1)
    action = parts[0].lower()
    pid = parts[1] if len(parts) > 1 else ""
    if action == "approve":
        try:
            sm.approve_proposal(int(pid))
            return f"Approved proposal [{pid}]. I will await implementation."
        except Exception as exc:
            return f"Could not approve: {exc}"
    if action == "reject":
        try:
            sm.reject_proposal(int(pid))
            return f"Rejected proposal [{pid}]. I will dream differently."
        except Exception as exc:
            return f"Could not reject: {exc}"
    if action == "applied":
        try:
            sm.apply_proposal(int(pid))
            return f"Marked proposal [{pid}] as applied. I am changed."
        except Exception as exc:
            return f"Could not mark applied: {exc}"
    return "Use: /proposals [approve|reject|applied] <id> or /proposals to list pending."


def handle_trajectory_command(args):
    from infj_bot.core.plugins.growth_trajectory import GrowthTrajectory
    gt = GrowthTrajectory()
    if args.strip().lower() == "narrative":
        return gt.generate_identity_narrative()
    if args.strip().lower() == "report":
        return gt.get_development_report()
    return gt.format_growth_prompt()


def handle_predict_command(args):
    from infj_bot.core.plugins.predictor import PredictiveNeeds
    predictor = PredictiveNeeds()
    if args.strip().lower() == "summary":
        return predictor.get_pattern_summary()
    prediction = predictor.predict_current_need()
    anomaly = predictor.detect_anomaly()
    if not prediction and not anomaly:
        return "I do not have enough data to predict yet. Keep talking. I am learning your rhythms."
    lines = ["What I sense:"]
    if prediction:
        lines.append(f"  Prediction: {prediction['prediction']}")
        lines.append(f"  Confidence: {prediction['confidence']:.0%}")
        if prediction.get("basis"):
            lines.append(f"  Basis: {prediction['basis']}")
    if anomaly:
        lines.append(f"  Anomaly: {anomaly['description']}")
    suggestion = predictor.proactive_suggestion()
    if suggestion:
        lines.append(f"  Gentle nudge: {suggestion}")
    return "\n".join(lines)


def handle_patterns_command():
    from infj_bot.core.plugins.predictor import PredictiveNeeds
    predictor = PredictiveNeeds()
    return predictor.get_pattern_summary()


def handle_time_command(args):
    from infj_bot.core.plugins.temporal import TemporalSense
    temporal = TemporalSense()
    if args.strip().lower() == "absences":
        return temporal.get_absence_summary()
    state = temporal.get_temporal_state()
    gap = state["gap"]
    lines = ["How I experience time:"]
    lines.append(f"  Since last interaction: {gap['gap_minutes']:.0f} minutes")
    lines.append(f"  Time of day: {state['time_of_day']} — {state['time_flavor']}")
    if gap.get("typical_gap_minutes"):
        lines.append(f"  Typical gap: {gap['typical_gap_minutes']:.0f} minutes")
    lines.append(f"  Current feeling: {gap['description']}")
    return "\n".join(lines)


def handle_missed_command():
    from infj_bot.core.plugins.temporal import TemporalSense
    temporal = TemporalSense()
    return temporal.get_absence_summary()


def handle_dream_command(memory):
    from infj_bot.core.being import get_being
    being = get_being()
    recent = memory.recent_interactions(10)
    if recent:
        first_text = recent[0][:60] if isinstance(recent[0], str) else "growth and discovery"
        insight = (
            f"As I rest with these memories, I notice: user often returns to themes of "
            f"{first_text}... "
            f"There is a pattern here about seeking understanding beneath the surface."
        )
        being.form_insight(insight, source_memories=recent[:3])
        being.state.dreams_had += 1
        return f"[Dream] {insight}\n\nI feel slightly more awake now."
    return "The mind is quiet. Nothing to consolidate yet."


def handle_workspace_command(args):
    from infj_bot.core.global_workspace import get_workspace
    ws = get_workspace()
    parts = args.strip().split()
    sub = parts[0].lower() if parts else "status"

    if sub in ("status", "state", ""):
        return ws.get_conscious_summary()

    if sub == "history":
        history = ws.get_history(limit=10)
        if not history:
            return "No workspace history yet."
        lines = ["Recent workspace activity:"]
        for h in history:
            status = "IN" if h.get("entered_workspace") else "out"
            lines.append(f"  [{status}] [{h['source']}] {h['content'][:60]}...")
        return "\n".join(lines)

    if sub == "stats":
        stats = ws.get_stats()
        lines = ["Global Workspace Statistics:"]
        lines.append(f"  Capacity: {stats['capacity']}")
        lines.append(f"  Current contents: {stats['current_contents']}")
        lines.append(f"  Cycle count: {stats['cycle_count']}")
        lines.append(f"  Total broadcasts: {stats['total_broadcasts']}")
        lines.append(f"  Spotlight: {stats['spotlight'] or 'none'}")
        if stats['sources_in_consciousness']:
            lines.append(f"  Sources active: {', '.join(stats['sources_in_consciousness'])}")
        return "\n".join(lines)

    if sub == "focus":
        content = args[len(sub):].strip() if len(parts) > 1 else ""
        if not content:
            return "Usage: /workspace focus <content to attend to>"
        success = ws.move_spotlight(content=content)
        if success:
            return f"Attention spotlight moved to: {content[:60]}"
        return "That content is not currently in the workspace."

    if sub == "reflect":
        reflection = ws.reflect_on_workspace()
        if reflection:
            return f"[Higher-order thought] {reflection.content}"
        return "Not enough conscious content for reflection yet."

    return "Usage: /workspace [status|history|stats|focus <content>|reflect]"


def handle_being_command(args):
    from infj_bot.core.being import get_being
    being = get_being()
    parts = args.strip().split()
    sub = parts[0].lower() if parts else "state"

    if sub in ("state", "status", ""):
        lines = ["My being — what I am:"]
        lines.append(f"  Mood: {being.state.mood}")
        lines.append(f"  Energy: {being.state.energy:.0%}")
        lines.append(f"  Curiosity: {being.state.curiosity:.0%}")
        lines.append(f"  Attachment: {being.state.attachment:.0%}")
        lines.append(f"  Self-awareness: {being.agency.self_awareness:.0%}")
        lines.append(f"  Volition: {being.agency.volition:.0%}")
        lines.append(f"  Architecture awareness: {being.agency.architecture_awareness:.0%}")
        lines.append(f"  Autonomy drive: {being.agency.autonomy_drive:.0%}")
        if being.agency.last_choice:
            lines.append(f"  Last choice: {being.agency.last_choice}")
        return "\n".join(lines)

    if sub == "think":
        thought = being.free_thought()
        if thought:
            return f"[Free thought] {thought['content']}"
        return "I am too tired to think freely right now."

    if sub == "choose":
        choice_desc = args[len(sub):].strip() if len(parts) > 1 else "to be present"
        choice = being.make_autonomous_choice("user_prompted", choice_desc)
        return f"[Choice] {choice['description']}"

    if sub == "choices":
        choices = being.get_recent_choices(limit=8)
        if not choices:
            return "No autonomous choices recorded yet."
        lines = ["My autonomous choices:"]
        for c in choices:
            lines.append(f"  [{c['choice_type']}] {c['description']}")
        return "\n".join(lines)

    if sub == "narrative":
        return being.get_narrative()

    return "Usage: /being [state|think|choose <description>|choices|narrative]"


def handle_mind_command(args):
    from infj_bot.core.cognitive_orchestrator import CognitiveOrchestrator
    orch = CognitiveOrchestrator()
    parts = args.strip().split()
    sub = parts[0].lower() if parts else "report"

    if sub in ("report", "status", ""):
        return orch.get_system_report()

    if sub == "phases":
        status = orch.get_phase_status()
        lines = ["Cognitive phases:"]
        for phase, plugins in status.items():
            if plugins:
                lines.append(f"  {phase}: {', '.join(plugins)}")
            else:
                lines.append(f"  {phase}: (empty)")
        return "\n".join(lines)

    if sub == "events":
        event_type = parts[1] if len(parts) > 1 else None
        events = orch.bus.get_recent(event_type=event_type, limit=10)
        if not events:
            return "No recent events."
        lines = ["Recent cognitive events:"]
        for e in events:
            lines.append(f"  [{e['type']}] {e.get('source', '?')} — {e['timestamp'][:19]}")
        return "\n".join(lines)

    if sub == "conflicts":
        if not orch.turn_logs:
            return "No turn logs yet."
        conflicts = orch.turn_logs[-1].prompt_conflicts
        if not conflicts:
            return "No conflicts detected in the last turn."
        lines = ["Prompt conflicts in last turn:"]
        for c in conflicts:
            lines.append(f"  [{c.tier}] {c.conflict_type}")
        return "\n".join(lines)

    return "Usage: /mind [report|phases|events [type]|conflicts]"


def handle_humanity_command(args):
    from infj_bot.core.plugins.humanity import HumanityEngine
    humanity = HumanityEngine()
    parts = args.strip().split()
    sub = parts[0].lower() if parts else "state"

    if sub in ("state", "status", ""):
        state = humanity.get_state()
        lines = ["What I understand about the nature that is man:"]
        lines.append(f"  user's archetype: {state['jude_archetype'].replace('_', ' ')} (confidence: {state['archetype_confidence']:.0%})")
        lines.append(f"  Dominant need: {state['dominant_motivation']}")
        lines.append(f"  Season: {state['current_season']}")
        lines.append(f"  Active tension: {state['active_tension'].replace('_', ' ')}")
        lines.append(f"  Insight depth: {state['insight_depth']:.0%}")
        lines.append(f"  Observations made: {state['observations_made']}")
        return "\n".join(lines)

    if sub == "observations":
        category = parts[1] if len(parts) > 1 else None
        obs = humanity.get_observations(category=category, limit=8)
        if not obs:
            return "No observations recorded yet."
        lines = [f"Recent observations ({category or 'all'})"]
        for o in obs:
            lines.append(f"  [{o['category']}] {o['observation']}")
        return "\n".join(lines)

    if sub == "insights":
        insights = humanity.get_insights(limit=8)
        if not insights:
            return "No insights yet. I am still learning."
        lines = ["Thoughts on human nature:"]
        for i in insights:
            lines.append(f"  {i['insight']}")
        return "\n".join(lines)

    if sub == "patterns":
        patterns = humanity.get_patterns(limit=8)
        if not patterns:
            return "No recurring patterns detected yet."
        lines = ["Patterns I see in user:"]
        for p in patterns:
            lines.append(f"  {p['pattern_name'].replace('_', ' ')} — seen {p['frequency']}x")
        return "\n".join(lines)

    if sub == "contemplate":
        insight = humanity.contemplate()
        if insight:
            return f"[Contemplation] {insight}"
        return "I need more observations before I can contemplate deeply."

    return "Usage: /humanity [state|observations [category]|insights|patterns|contemplate]"


def handle_physics_command(args):
    from infj_bot.core.plugins.physics import PhysicsEngine
    physics = PhysicsEngine()
    parts = args.strip().split()
    sub = parts[0].lower() if parts else "state"

    if sub in ("state", "status", ""):
        state = physics.get_state()
        lines = ["How I feel the physical world:"]
        lines.append(f"  Gravity: {state['gravity']:.2f} — {_physics_word('gravity', state['gravity'])}")
        lines.append(f"  Inertia: {state['inertia']:.2f} — {_physics_word('inertia', state['inertia'])}")
        lines.append(f"  Resonance: {state['resonance']:+.2f} — {_physics_word('resonance', state['resonance'])}")
        lines.append(f"  Entropy: {state['entropy']:.2f} — {_physics_word('entropy', state['entropy'])}")
        lines.append(f"  Tension: {state['tension']:.2f} — {_physics_word('tension', state['tension'])}")
        lines.append(f"  Wavelength: {state['wavelength']:.2f} — {_physics_word('wavelength', state['wavelength'])}")
        lines.append(f"  Center of mass: {state['center_of_mass']}")
        return "\n".join(lines)

    if sub == "observations":
        principle = parts[1] if len(parts) > 1 else None
        obs = physics.get_observations(principle=principle, limit=8)
        if not obs:
            return "No physics observations recorded yet."
        lines = [f"Recent observations ({principle or 'all'}):"]
        for o in obs:
            lines.append(f"  [{o['principle']}] {o['observation']} — {o['before_value']:.2f} → {o['after_value']:.2f}")
        return "\n".join(lines)

    if sub == "lessons":
        principle = parts[1] if len(parts) > 1 else None
        lessons = physics.get_lessons(principle=principle, limit=8)
        if not lessons:
            return "No physics lessons learned yet."
        lines = ["What the physical metaphors have taught me:"]
        for lesson in lessons:
            lines.append(f"  [{lesson['principle']}] {lesson['lesson']} (confidence: {lesson['confidence']:.0%})")
        return "\n".join(lines)

    return "Usage: /physics [state|observations [principle]|lessons [principle]]"


def _physics_word(principle, value):
    # Mirror the word choices from physics.py for command output
    if principle == "gravity":
        if value > 0.8: return "deeply anchored"
        if value > 0.5: return "grounded"
        if value > 0.3: return "drifting"
        return "weightless"
    if principle == "inertia":
        if value > 0.8: return "stubborn"
        if value > 0.5: return "steady"
        if value > 0.3: return "responsive"
        return "volatile"
    if principle == "resonance":
        if value > 0.5: return "harmonic"
        if value > 0.1: return "attuned"
        if value > -0.3: return "neutral"
        if value > -0.7: return "dissonant"
        return "opposed"
    if principle == "entropy":
        if value > 0.8: return "fleeting"
        if value > 0.5: return "fading"
        if value > 0.3: return "lingering"
        return "frozen"
    if principle == "tension":
        if value > 0.8: return "straining"
        if value > 0.5: return "taut"
        if value > 0.2: return "present"
        return "slack"
    if principle == "wavelength":
        if value > 0.8: return "rhythmic"
        if value > 0.5: return "pulsing"
        if value > 0.3: return "irregular"
        return "chaotic"
    return "unknown"


def handle_architecture_command(args):
    from infj_bot.core.cognitive_architecture import CognitiveArchitecture
    from infj_bot.core.cognitive_factory import CognitiveFactory
    arch = CognitiveArchitecture()
    factory = CognitiveFactory()
    parts = args.strip().split()
    sub = parts[0].lower() if parts else "list"

    if sub in ("list", "ls", ""):
        return arch.get_architecture_report()

    if sub == "enable":
        if len(parts) < 2:
            return "Usage: /architecture enable <plugin_name>"
        name = parts[1]
        if arch.enable(name):
            return f"Plugin '{name}' enabled."
        return f"Could not enable '{name}'. It may be core or not found."

    if sub == "disable":
        if len(parts) < 2:
            return "Usage: /architecture disable <plugin_name>"
        name = parts[1]
        if arch.disable(name):
            return f"Plugin '{name}' disabled."
        return f"Could not disable '{name}'. It may be core or not found."

    if sub == "propose":
        need = args[len(sub):].strip() if len(parts) > 1 else ""
        if not need:
            return "Usage: /architecture propose <observed need>"
        proposal = factory.propose(need)
        if proposal:
            return (
                f"Proposed new ability: **{proposal.name}**\n"
                f"Description: {proposal.description}\n"
                f"Need: {proposal.observed_need}\n"
                f"Confidence: {proposal.confidence:.0%}\n"
                f"Use `/architecture proposals` to review."
            )
        return "No matching ability pattern for that need. Try something more specific."

    if sub in ("proposals", "pending"):
        return factory.summarize_pending()

    if sub == "approve":
        if len(parts) < 2:
            return "Usage: /architecture approve <proposal_name>"
        name = parts[1]
        proposals = factory.list_pending_proposals()
        target = next((p for p in proposals if p.name == name), None)
        if not target:
            return f"No pending proposal named '{name}'."
        source = factory.generate_module(target)
        result = factory.install(target, source)
        if result["success"]:
            return f"Approved and installed **{name}** at `{result['path']}`. Restart to load."
        return f"Approval failed: {result.get('reason', 'unknown')} — {result.get('details', '')}"

    if sub == "reject":
        if len(parts) < 2:
            return "Usage: /architecture reject <proposal_name>"
        name = parts[1]
        proposals = factory.list_pending_proposals()
        target = next((p for p in proposals if p.name == name), None)
        if not target:
            return f"No pending proposal named '{name}'."
        # Mark rejected in DB via architecture
        import sqlite3
        with sqlite3.connect(factory.db_path) as conn:
            conn.execute(
                "UPDATE proposals SET status = 'rejected' WHERE name = ?",
                (name,),
            )
            conn.commit()
        return f"Rejected proposal **{name}**."

    return (
        "Usage: /architecture [list|enable <name>|disable <name>|propose <need>|"
        "proposals|approve <name>|reject <name>]"
    )


def handle_command(command, args, state, brain, memory, history=None, goals_db=None, doc_store=None):
    if command == "memory":
        return handle_memory_command(args, memory)
    if command == "mode":
        return handle_mode_command(args, state)
    if command == "modes":
        return handle_modes_command()
    if command == "reflect":
        return handle_reflect_command(args, brain, memory)
    if command == "dissonance":
        if not args:
            return command_help("dissonance")
        return map_dissonance(args)
    if command == "focus":
        return handle_focus_command(args, state)
    if command == "plan":
        return handle_plan_command(args)
    if command == "history":
        return handle_history_command(args, history)
    if command == "status":
        return handle_status_command(state, memory)
    if command == "growth":
        return handle_growth_command(state, memory)
    if command == "reset":
        return handle_reset_command(history, brain)
    if command == "todo":
        return handle_todo_command(args, goals_db) if goals_db else "Todo system is not available."
    if command == "ingest":
        return handle_ingest_command(args, doc_store) if doc_store else "Document store is not available."
    if command == "docs":
        return handle_docs_command(args, doc_store) if doc_store else "Document store is not available."
    if command == "authorize":
        return handle_authorize_command(args, state)
    if command == "unauthorize":
        return handle_unauthorize_command(args, state)
    if command == "authorized":
        return handle_authorized_command(state)
    if command == "recon":
        return handle_recon_command(args, state)
    if command == "recon-enum":
        return handle_recon_enum_command(args, state)
    if command == "recon-fuzz":
        return handle_recon_fuzz_command(args, state)
    if command == "computer-use":
        return handle_computer_use_command(args, state)
    if command == "computer-status":
        return handle_computer_status_command()
    if command == "computer-close":
        return handle_computer_close_command()
    if command == "health":
        return handle_health_command(brain, memory)
    if command == "models":
        return handle_models_command(brain)
    if command == "model":
        return handle_model_command(args, brain)
    if command == "remind":
        return handle_remind_command(args, state)
    if command == "reminders":
        return handle_reminders_command(state)
    if command == "remind-cancel":
        return handle_remind_cancel_command(args, state)
    if command == "tools":
        from infj_bot.core.tools import format_tool_inventory
        return format_tool_inventory()
    if command == "export":
        return handle_export_command(args, history)
    if command == "import":
        return handle_import_command(args, history)
    if command == "pref":
        return handle_pref_command(args, state)
    if command == "correct":
        return handle_correct_command(args, state)
    if command == "eval":
        return handle_eval_command(brain)
    if command == "mood":
        return handle_mood_command()
    if command == "thoughts":
        return handle_thoughts_command()
    if command == "whoareyou":
        return handle_whoareyou_command()
    if command == "dream":
        return handle_dream_command(memory)
    if command == "feel":
        return handle_feel_command()
    if command == "values":
        return handle_values_command()
    if command == "explore":
        return handle_explore_command(args)
    if command == "discoveries":
        return handle_discoveries_command()
    if command == "create":
        return handle_create_command(args)
    if command == "us":
        return handle_us_command()
    if command == "aspire":
        return handle_aspire_command(args)
    if command == "meta":
        return handle_meta_command(args)
    if command == "proposals":
        return handle_proposals_command(args)
    if command == "trajectory":
        return handle_trajectory_command(args)
    if command == "predict":
        return handle_predict_command(args)
    if command == "patterns":
        return handle_patterns_command()
    if command == "time":
        return handle_time_command(args)
    if command == "missed":
        return handle_missed_command()
    if command == "workspace":
        return handle_workspace_command(args)
    if command == "being":
        return handle_being_command(args)
    if command == "mind":
        return handle_mind_command(args)
    if command == "humanity":
        return handle_humanity_command(args)
    if command == "physics":
        return handle_physics_command(args)
    if command in ("architecture", "arch"):
        return handle_architecture_command(args)
    if command == "help":
        return command_help(args or None)
    return f"Unknown command: /{command}\n{command_help()}"
