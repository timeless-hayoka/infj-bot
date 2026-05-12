"""Cognitive Architecture — the bot's self-building mind.

This module transforms the bot from a flat collection of hardcoded modules
into a dynamic, self-assembling cognitive architecture. Every cognitive
ability registers itself. The consciousness loop is assembled at runtime.
New abilities can be proposed, generated, approved, and installed.

Core concept: the bot owns its cognitive growth. Jude approves.
"""

import ast
import json
import logging
import random
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from config import ARCHITECTURE_DB

logger = logging.getLogger("infj_bot")

# Modules that the architecture cannot function without
CORE_PLUGINS = {"being", "memory", "emotional_field", "values", "brain"}

# Forbidden imports in user-created plugins
FORBIDDEN_IMPORTS = {
    "os",
    "subprocess",
    "socket",
    "urllib",
    "urllib2",
    "requests",
    "http",
    "ftplib",
    "smtplib",
    "telnetlib",
    "pickle",
    "cpickle",
    "marshal",
    "ctypes",
    "mmap",
    "resource",
    "pty",
    "pwd",
    "grp",
    "spwd",
    "sys",
    "builtins",
    "__builtin__",
}


@dataclass
class CycleContext:
    """Context passed to every plugin's cycle method."""

    being: Any
    memory: Any
    state: Any
    brain: Any
    iteration: int
    minutes_since_interaction: float
    last_interaction_time: Optional[datetime]
    last_user_input: str = ""
    last_interaction: Optional[Dict] = None


@dataclass
class CognitivePlugin:
    """A registered cognitive ability."""

    name: str
    description: str
    module_path: str
    instance_factory: Optional[Callable] = None
    instance: Any = field(default=None, repr=False)

    # Consciousness loop
    cycle_handler: Optional[str] = None
    cycle_frequency: int = 1
    cycle_condition: Optional[str] = None  # e.g. "random(0.25)"
    cycle_priority: int = 50

    # Prompt injection
    prompt_formatter: Optional[str] = None
    prompt_priority: int = 50
    prompt_section: str = "cognitive"  # core, cognitive, analysis, context

    # Commands: {command_name: handler_name}
    commands: Dict[str, str] = field(default_factory=dict)

    # Lifecycle
    enabled: bool = True
    is_core: bool = False
    is_user_created: bool = False
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def should_run_cycle(self, iteration: int) -> bool:
        """Determine if this plugin should run on the given loop iteration."""
        if not self.enabled:
            return False
        if self.cycle_handler is None:
            return False
        if iteration % self.cycle_frequency != 0:
            return False
        if self.cycle_condition:
            if self.cycle_condition.startswith("random("):
                prob = float(
                    self.cycle_condition.replace("random(", "").replace(")", "")
                )
                return random.random() < prob
        return True

    def run_cycle(self, context: CycleContext):
        """Execute the plugin's cycle method if configured."""
        if self.instance is None or not self.enabled:
            return
        handler_name = self.cycle_handler
        if handler_name and hasattr(self.instance, handler_name):
            handler = getattr(self.instance, handler_name)
            try:
                handler(context)
            except Exception:
                logger.exception(
                    f"Plugin '{self.name}' cycle handler '{handler_name}' failed"
                )

    def format_prompt(self) -> str:
        """Get prompt snippet from this plugin if configured."""
        if self.instance is None or not self.enabled or not self.prompt_formatter:
            return ""
        if hasattr(self.instance, self.prompt_formatter):
            try:
                return getattr(self.instance, self.prompt_formatter)() or ""
            except Exception:
                logger.exception(f"Plugin '{self.name}' prompt formatter failed")
        return ""


@dataclass
class LoopStep:
    """A runnable step in the consciousness loop."""

    plugin: CognitivePlugin
    instance: Any = field(default=None, repr=False)

    def __post_init__(self):
        if self.instance is None:
            if self.plugin.instance is not None:
                self.instance = self.plugin.instance
            elif self.plugin.instance_factory is not None:
                try:
                    self.instance = self.plugin.instance_factory()
                except Exception:
                    logger.exception(
                        "Failed to instantiate plugin '%s' in LoopStep",
                        self.plugin.name,
                    )
            if self.instance is not None:
                self.plugin.instance = self.instance

    def should_run(self, iteration: int) -> bool:
        return self.plugin.should_run_cycle(iteration)

    def run(self, context: CycleContext):
        self.plugin.run_cycle(context)


@dataclass
class PluginProposal:
    """A proposal for a new cognitive ability."""

    id: int = 0
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    name: str = ""
    description: str = ""
    module_type: str = (
        "observer"  # observer, predictor, responder, memory_enhancer, creative, tracker
    )
    observed_need: str = ""
    purpose: str = ""
    rationale: str = ""
    status: str = "pending"  # pending, approved, rejected, installed
    reviewed_at: Optional[str] = None
    installed_at: Optional[str] = None


class CognitiveArchitecture:
    """The registry and orchestrator of all cognitive abilities."""

    _instance: Optional["CognitiveArchitecture"] = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    @classmethod
    def reset_instance(cls):
        """Reset the singleton. Used primarily in tests."""
        cls._instance = None

    def __init__(self, db_path: Optional[Path] = None):
        if self._initialized:
            return
        self.db_path = str(db_path or ARCHITECTURE_DB)
        self._init_db()
        self._plugins: Dict[str, CognitivePlugin] = {}
        self._load_registry()
        self._initialized = True

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS cognitive_plugins (
                    name TEXT PRIMARY KEY,
                    description TEXT,
                    module_path TEXT,
                    cycle_handler TEXT,
                    cycle_frequency INTEGER,
                    cycle_condition TEXT,
                    cycle_priority INTEGER,
                    prompt_formatter TEXT,
                    prompt_priority INTEGER,
                    prompt_section TEXT,
                    commands TEXT,
                    enabled INTEGER DEFAULT 1,
                    is_core INTEGER DEFAULT 0,
                    is_user_created INTEGER DEFAULT 0,
                    created_at TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS plugin_proposals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    name TEXT NOT NULL,
                    description TEXT NOT NULL,
                    module_type TEXT NOT NULL,
                    observed_need TEXT,
                    purpose TEXT,
                    rationale TEXT,
                    status TEXT NOT NULL DEFAULT 'pending',
                    reviewed_at TEXT,
                    installed_at TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS architecture_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    plugin_name TEXT,
                    description TEXT
                )
                """
            )
            conn.commit()

    def _load_registry(self):
        """Load registered plugins from DB."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("SELECT * FROM cognitive_plugins").fetchall()
        for row in rows:
            plugin = self._row_to_plugin(row)
            self._plugins[plugin.name] = plugin

    def _row_to_plugin(self, row: sqlite3.Row) -> CognitivePlugin:
        return CognitivePlugin(
            name=row["name"],
            description=row["description"] or "",
            module_path=row["module_path"] or row["name"],
            cycle_handler=row["cycle_handler"],
            cycle_frequency=row["cycle_frequency"] or 1,
            cycle_condition=row["cycle_condition"],
            cycle_priority=row["cycle_priority"] or 50,
            prompt_formatter=row["prompt_formatter"],
            prompt_priority=row["prompt_priority"] or 50,
            prompt_section=row["prompt_section"] or "cognitive",
            commands=json.loads(row["commands"]) if row["commands"] else {},
            enabled=bool(row["enabled"]),
            is_core=bool(row["is_core"]),
            is_user_created=bool(row["is_user_created"]),
            created_at=row["created_at"] or datetime.now().isoformat(),
        )

    def _plugin_to_row(self, plugin: CognitivePlugin) -> tuple:
        return (
            plugin.name,
            plugin.description,
            plugin.module_path,
            plugin.cycle_handler,
            plugin.cycle_frequency,
            plugin.cycle_condition,
            plugin.cycle_priority,
            plugin.prompt_formatter,
            plugin.prompt_priority,
            plugin.prompt_section,
            json.dumps(plugin.commands),
            int(plugin.enabled),
            int(plugin.is_core),
            int(plugin.is_user_created),
            plugin.created_at,
        )

    def register(self, plugin: CognitivePlugin):
        """Register a cognitive plugin. Instantiates if factory provided."""
        if plugin.name in self._plugins:
            # Update existing — preserve wired instance and enabled state
            existing = self._plugins[plugin.name]
            if existing.instance is not None:
                plugin.instance = existing.instance
            plugin.enabled = existing.enabled

        self._plugins[plugin.name] = plugin

        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO cognitive_plugins
                (name, description, module_path, cycle_handler, cycle_frequency,
                 cycle_condition, cycle_priority, prompt_formatter, prompt_priority,
                 prompt_section, commands, enabled, is_core, is_user_created, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                self._plugin_to_row(plugin),
            )
            conn.commit()

        self._record_event(
            "registered", plugin.name, f"Registered plugin: {plugin.description}"
        )

    def unregister(self, name: str) -> bool:
        """Remove a user-created plugin. Core plugins cannot be unregistered."""
        if name not in self._plugins:
            return False
        plugin = self._plugins[name]
        if plugin.is_core or name in CORE_PLUGINS:
            return False
        del self._plugins[name]
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM cognitive_plugins WHERE name = ?", (name,))
            conn.commit()
        self._record_event("unregistered", name, "Plugin unregistered")
        return True

    def enable(self, name: str) -> bool:
        if name not in self._plugins:
            return False
        self._plugins[name].enabled = True
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE cognitive_plugins SET enabled = 1 WHERE name = ?", (name,)
            )
            conn.commit()
        self._record_event("enabled", name, "Plugin enabled")
        return True

    def disable(self, name: str) -> bool:
        if name not in self._plugins:
            return False
        if self._plugins[name].is_core or name in CORE_PLUGINS:
            return False
        self._plugins[name].enabled = False
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE cognitive_plugins SET enabled = 0 WHERE name = ?", (name,)
            )
            conn.commit()
        self._record_event("disabled", name, "Plugin disabled")
        return True

    def list_plugins(self) -> List[str]:
        return list(self._plugins.keys())

    def get_plugin(self, name: str) -> Optional[CognitivePlugin]:
        return self._plugins.get(name)

    def get_enabled_plugins(self) -> List[CognitivePlugin]:
        return [p for p in self._plugins.values() if p.enabled]

    def get_loop_steps(self) -> List[LoopStep]:
        """Get enabled plugins with cycle handlers as LoopSteps, ordered by priority."""
        plugins = [p for p in self._plugins.values() if p.enabled and p.cycle_handler]
        plugins.sort(key=lambda p: p.cycle_priority)
        return [LoopStep(plugin=p) for p in plugins]

    def get_prompt_plugins(self) -> List[CognitivePlugin]:
        """Get enabled plugins with prompt formatters, ordered by priority."""
        plugins = [
            p for p in self._plugins.values() if p.enabled and p.prompt_formatter
        ]
        plugins.sort(key=lambda p: p.prompt_priority)
        return plugins

    def get_commands(self) -> Dict[str, tuple]:
        """Build unified command dispatch table: {cmd: (plugin_name, handler_name)}."""
        table: Dict[str, tuple] = {}
        for plugin in self._plugins.values():
            if not plugin.enabled:
                continue
            for cmd, handler in plugin.commands.items():
                table[cmd] = (plugin.name, handler)
        return table

    def run_cycles(self, context: CycleContext):
        """Run all enabled cycle handlers for the current iteration."""
        for step in self.get_loop_steps():
            if step.should_run(context.iteration):
                step.run(context)

    def assemble_prompt_sections(self) -> Dict[str, List[str]]:
        """Assemble prompt snippets from all enabled plugins."""
        sections: Dict[str, List[str]] = {
            "core": [],
            "cognitive": [],
            "analysis": [],
            "context": [],
        }
        for plugin in self.get_prompt_plugins():
            snippet = plugin.format_prompt()
            if snippet:
                section = (
                    plugin.prompt_section
                    if plugin.prompt_section in sections
                    else "cognitive"
                )
                sections[section].append(snippet)
        return sections

    # ---- Proposal system ----

    def propose_plugin(self, proposal: PluginProposal) -> PluginProposal:
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.execute(
                """
                INSERT INTO plugin_proposals
                (timestamp, name, description, module_type, observed_need, purpose, rationale, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    proposal.timestamp,
                    proposal.name,
                    proposal.description,
                    proposal.module_type,
                    proposal.observed_need,
                    proposal.purpose,
                    proposal.rationale,
                    proposal.status,
                ),
            )
            conn.commit()
            proposal.id = cur.lastrowid
        self._record_event(
            "proposed", proposal.name, f"Proposed new plugin: {proposal.description}"
        )
        return proposal

    def get_proposals(self, status: Optional[str] = None) -> List[PluginProposal]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            if status:
                rows = conn.execute(
                    "SELECT * FROM plugin_proposals WHERE status = ? ORDER BY timestamp DESC",
                    (status,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM plugin_proposals ORDER BY timestamp DESC"
                ).fetchall()
        return [self._row_to_proposal(r) for r in rows]

    def _row_to_proposal(self, row: sqlite3.Row) -> PluginProposal:
        return PluginProposal(
            id=row["id"],
            timestamp=row["timestamp"],
            name=row["name"],
            description=row["description"],
            module_type=row["module_type"],
            observed_need=row["observed_need"] or "",
            purpose=row["purpose"] or "",
            rationale=row["rationale"] or "",
            status=row["status"],
            reviewed_at=row["reviewed_at"],
            installed_at=row["installed_at"],
        )

    def approve_proposal(self, proposal_id: int) -> bool:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE plugin_proposals SET status = 'approved', reviewed_at = ? WHERE id = ?",
                (datetime.now().isoformat(), proposal_id),
            )
            conn.commit()
        self._record_event("approved", None, f"Approved proposal {proposal_id}")
        return True

    def reject_proposal(self, proposal_id: int) -> bool:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE plugin_proposals SET status = 'rejected', reviewed_at = ? WHERE id = ?",
                (datetime.now().isoformat(), proposal_id),
            )
            conn.commit()
        self._record_event("rejected", None, f"Rejected proposal {proposal_id}")
        return True

    def mark_installed(self, proposal_id: int, plugin_name: str) -> bool:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE plugin_proposals SET status = 'installed', installed_at = ? WHERE id = ?",
                (datetime.now().isoformat(), proposal_id),
            )
            conn.commit()
        self._record_event(
            "installed",
            plugin_name,
            f"Installed proposal {proposal_id} as {plugin_name}",
        )
        return True

    # ---- Validation ----

    @staticmethod
    def validate_code(code: str) -> tuple[bool, str]:
        """AST-validate generated plugin code for safety."""
        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            return False, f"Syntax error: {e}"

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root = alias.name.split(".")[0]
                    if root in FORBIDDEN_IMPORTS:
                        return False, f"Forbidden import: {alias.name}"
            elif isinstance(node, ast.ImportFrom):
                module = (node.module or "").split(".")[0]
                if module in FORBIDDEN_IMPORTS:
                    return False, f"Forbidden import from: {node.module}"
            elif isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    if node.func.id in ("eval", "exec", "compile"):
                        return False, f"Forbidden function call: {node.func.id}"
                elif isinstance(node.func, ast.Attribute):
                    if node.func.attr in ("__import__", "eval", "exec"):
                        return False, f"Forbidden method call: {node.func.attr}"
        return True, "OK"

    # ---- Reporting ----

    def get_architecture_report(self) -> str:
        lines = ["=== COGNITIVE ARCHITECTURE ===", ""]
        lines.append(f"Registered plugins: {len(self._plugins)}")
        lines.append(f"Enabled: {len(self.get_enabled_plugins())}")
        lines.append("")

        core = [
            p for p in self._plugins.values() if p.is_core or p.name in CORE_PLUGINS
        ]
        user = [p for p in self._plugins.values() if p.is_user_created]
        builtin = [
            p for p in self._plugins.values() if not p.is_core and not p.is_user_created
        ]

        if core:
            lines.append("Core (protected):")
            for p in core:
                lines.append(
                    f"  [{'ON' if p.enabled else 'OFF'}] {p.name} — {p.description[:60]}"
                )
        if builtin:
            lines.append("\nBuilt-in:")
            for p in builtin:
                lines.append(
                    f"  [{'ON' if p.enabled else 'OFF'}] {p.name} — {p.description[:60]}"
                )
        if user:
            lines.append("\nUser-created:")
            for p in user:
                lines.append(
                    f"  [{'ON' if p.enabled else 'OFF'}] {p.name} — {p.description[:60]}"
                )

        pending = len(self.get_proposals(status="pending"))
        if pending:
            lines.append(f"\nPending proposals: {pending}")

        return "\n".join(lines)

    def _record_event(
        self, event_type: str, plugin_name: Optional[str], description: str
    ):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO architecture_events (timestamp, event_type, plugin_name, description) VALUES (?, ?, ?, ?)",
                (datetime.now().isoformat(), event_type, plugin_name, description),
            )
            conn.commit()
