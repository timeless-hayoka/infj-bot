"""Rich TUI for the INFJ companion bot.

Run with: python tui.py
"""
import queue
import sys
import threading

from rich.align import Align
from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.rule import Rule
from rich.text import Text

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))

from brain import InfjBrain
from commands import BotState, handle_command, is_command, parse_command
from config import DEFAULT_AUTHORIZED_TARGETS
from documents import DocumentStore
from goals import GoalsDB
from growth import growth_profile
from history import ChatHistory
from memory import InfjMemory
from prompt_builder import build_chat_prompt
from proactive import ProactiveState

console = Console()


class InfjTUI:
    def __init__(self):
        self.brain = InfjBrain()
        self.memory = InfjMemory()
        self.history = ChatHistory()
        self.state = BotState(authorized_targets=set(DEFAULT_AUTHORIZED_TARGETS))
        self.goals_db = GoalsDB()
        self.proactive_state = ProactiveState()
        self.doc_store = DocumentStore()

        self.messages = []
        self.input_queue = queue.Queue()
        self.running = True
        self._live = None

    def _make_header(self) -> Panel:
        text = Text()
        text.append("INFJ Companion Bot ", style="bold cyan")
        text.append("v1.3 ", style="dim")
        text.append(f"Mode: {self.state.mode}  ", style="green")
        text.append(f"Turns: {self.state.turns}", style="dim")
        return Panel(Align.left(text), height=3, style="on black")

    def _make_sidebar(self) -> Panel:
        lines = []
        # Health
        health = self.brain.health_check()
        lines.append(Text("Health", style="bold yellow"))
        g = "[green]●[/]" if health["gemini"]["ok"] else "[red]●[/]"
        l = "[green]●[/]" if health["local"]["ok"] else "[red]●[/]"
        lines.append(Text.from_markup(f"  Gemini {g}  Ollama {l}"))
        lines.append("")

        # Growth
        gp = growth_profile(self.memory, self.state.turns)
        lines.append(Text("Growth", style="bold yellow"))
        lines.append(Text.from_markup(f"  {gp['stage']} ({gp['points']} pts)"))
        lines.append("")

        # Memory
        lines.append(Text("Memory", style="bold yellow"))
        lines.append(Text(f"  {self.memory.count()} entries"))
        lines.append("")

        # Reminders
        lines.append(Text("Reminders", style="bold yellow"))
        tasks = self.state.scheduler.list_pending(limit=3)
        if tasks:
            for t in tasks:
                due = t.run_at.strftime("%H:%M")
                lines.append(Text(f"  • {due} {t.title[:24]}", style="dim"))
        else:
            lines.append(Text("  None", style="dim"))
        lines.append("")

        # Authorized
        if self.state.authorized_targets:
            lines.append(Text("Authorized", style="bold yellow"))
            for d in sorted(self.state.authorized_targets)[:5]:
                lines.append(Text(f"  • {d}", style="dim"))

        content = Text("\n").join(lines)
        return Panel(content, title="Status", border_style="blue", width=28)

    def _make_chat(self) -> Panel:
        if not self.messages:
            content = Align.center(Text("Start a conversation...", style="dim italic"), vertical="middle")
        else:
            parts = []
            for role, text in self.messages[-50:]:
                if role == "user":
                    parts.append(Text.from_markup(f"[bold blue]Jude[/]  {text[:300]}{'…' if len(text) > 300 else ''}"))
                elif role == "bot":
                    parts.append(Markdown(text))
                elif role == "system":
                    parts.append(Text.from_markup(f"[dim italic]{text}[/]"))
                parts.append("")
            content = Text("\n").join(parts)
        return Panel(content, title="Conversation", border_style="green")

    def _make_footer(self) -> Panel:
        return Panel(
            Text("Type /help for commands  •  exit to quit", style="dim"),
            height=3,
            style="on black",
        )

    def render(self) -> Layout:
        layout = Layout()
        layout.split_column(
            Layout(self._make_header(), size=3),
            Layout(name="main"),
            Layout(self._make_footer(), size=3),
        )
        layout["main"].split_row(
            Layout(self._make_chat(), name="chat"),
            Layout(self._make_sidebar(), name="sidebar", size=30),
        )
        return layout

    def add_message(self, role: str, text: str):
        self.messages.append((role, text))

    def _input_thread(self):
        """Read user input in a background thread."""
        while self.running:
            try:
                user_input = console.input("[bold blue]JUDE> [/]")
                self.input_queue.put(user_input)
            except (EOFError, KeyboardInterrupt):
                self.input_queue.put("exit")
                break

    def _process_input(self, user_input: str):
        if user_input.lower() in ("exit", "quit"):
            self.running = False
            return

        self.add_message("user", user_input)

        if is_command(user_input):
            command, args = parse_command(user_input)
            output = handle_command(
                command, args, self.state, self.brain, self.memory,
                self.history, self.goals_db, self.doc_store,
            )
            self.add_message("system", output)
            return

        prompt, emotion, dissonance = build_chat_prompt(
            user_input, self.state, self.memory,
            goals_db=self.goals_db, doc_store=self.doc_store, prefs=self.state.prefs,
        )
        output = self.brain.agent_turn(prompt, tools_enabled=True)
        try:
            self.brain.evaluate_last(prompt, output)
        except Exception:
            pass

        importance = min(0.95, 0.45 + emotion["intensity"] * 0.3 + dissonance["score"] * 0.15)
        self.memory.save_interaction(
            user_input, output, mode=self.state.mode,
            emotion=emotion, importance=importance, dissonance=dissonance,
        )
        self.history.append(user_input, output, self.state.mode, emotion, dissonance)
        self.state.turns += 1
        self.proactive_state.record_interaction(user_input, emotion, dissonance)

        self.add_message("bot", output)

    def run(self):
        console.clear()
        console.print(Rule("[bold cyan]INFJ Companion Bot v1.3[/]", style="cyan"))
        console.print("[dim]A mind that listens, remembers, and wonders.[/]\n")
        console.print("[dim]Type /help for commands, exit to quit.[/]\n")

        input_thread = threading.Thread(target=self._input_thread, daemon=True)
        input_thread.start()

        with Live(self.render(), console=console, refresh_per_second=4, screen=False) as live:
            self._live = live
            while self.running:
                try:
                    user_input = self.input_queue.get(timeout=0.5)
                except queue.Empty:
                    live.update(self.render())
                    continue

                if user_input.lower() in ("exit", "quit"):
                    self.running = False
                    break

                self._process_input(user_input)
                live.update(self.render())

        console.print("\n[dim]I'll be here in the quiet if you need me again. Goodbye, Jude.[/]")


if __name__ == "__main__":
    try:
        InfjTUI().run()
    except KeyboardInterrupt:
        console.print("\n[dim]Manual override. Powering down.[/]")
