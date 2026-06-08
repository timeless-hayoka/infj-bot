#!/usr/bin/env python3
import argparse
import asyncio
import os
import subprocess
import sys

from infj_bot.config_adapter import PROJECT_ROOT


def run_script(script_name, extra_env=None):
    env = os.environ.copy()
    if extra_env:
        env.update(extra_env)
    script = PROJECT_ROOT / "scripts" / script_name
    return subprocess.call([str(script)], cwd=str(PROJECT_ROOT), env=env)


def cmd_chat(_args):
    from infj_bot.interfaces.main import main

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[*] Manual override. Powering down.")
        return 130
    return 0


def cmd_tui(_args):
    from tui import DriftTUI

    try:
        DriftTUI().run()
    except KeyboardInterrupt:
        print("\n[*] Manual override. Powering down.")
        return 130
    return 0


def cmd_ask(args):
    from infj_bot.core.brain import DriftBrain
    from infj_bot.core.commands import BotState
    from infj_bot.core.history import ChatHistory
    from infj_bot.core.memory import DriftMemory
    from infj_bot.core.prompt_builder import build_chat_prompt
    from infj_bot.core.plugins.goals import GoalsDB
    from infj_bot.core.plugins.documents import DocumentStore

    prompt = " ".join(args.prompt).strip()
    if not prompt:
        print(
            "Give me something to ask. Example: infj_bot ask what should I focus on today?"
        )
        return 2

    from infj_bot.core.config import DEFAULT_AUTHORIZED_TARGETS

    state = BotState(
        mode=args.mode,
        proactive_enabled=False,
        authorized_targets=set(DEFAULT_AUTHORIZED_TARGETS),
    )
    brain = DriftBrain()
    memory = DriftMemory()
    history = ChatHistory()
    
    # Phase 5: Wire deliberation bridge
    from infj_bot.core.cognitive_orchestrator import CognitiveOrchestrator
    _orchestrator = CognitiveOrchestrator()
    _orchestrator.memory = memory
    _orchestrator.brain = brain

    # Phase 6: Unified Audit
    from infj_bot.core.unified_audit import wire_orchestrator_audit
    wire_orchestrator_audit(_orchestrator)

    def deliberation_bridge(goal: str):
        """Synchronous bridge for CLI deliberation, avoiding deadlocks."""
        import asyncio
        from infj_bot.core.hive.elysium import DeliberationResult
        try:
            try:
                asyncio.get_running_loop()
                # Run in separate thread if loop exists
                from concurrent.futures import ThreadPoolExecutor
                with ThreadPoolExecutor() as executor:
                    def _run():
                        new_loop = asyncio.new_event_loop()
                        try:
                            return new_loop.run_until_complete(_orchestrator.deliberate(goal))
                        finally:
                            new_loop.close()
                    return executor.submit(_run).result()
            except RuntimeError:
                return asyncio.run(_orchestrator.deliberate(goal))
        except Exception as e:
            return DeliberationResult(goal=goal, resolution=f"BLOCK: deliberation failure ({e})", council_votes={}, winning_role="none", moral_weight=0.0, narrative_weight=0.0)

    brain.deliberation_callback = deliberation_bridge
    from infj_bot.core.being import get_being
    get_being().deliberation_callback = deliberation_bridge
    
    goals_db = GoalsDB()
    doc_store = DocumentStore()
    try:
        built_prompt, emotion, dissonance = build_chat_prompt(
            prompt,
            state,
            memory,
            goals_db=goals_db,
            doc_store=doc_store,
            tools_enabled=not args.no_tools,
            prefs=state.prefs,
        )
    except Exception as exc:
        # Catch Shadow Intent Enforcement blocks
        from infj_bot.core.cognitive_orchestrator import IntentBlockedError
        if isinstance(exc, IntentBlockedError):
            print(f"\n[SECURITY BLOCK]: {exc}")
            return 1
        print(f"Error during prompt assembly: {exc}")
        return 1

    try:
        output = brain.agent_turn(built_prompt, tools_enabled=not args.no_tools, raw_user_input=prompt)
        try:
            brain.evaluate_last(built_prompt, output)
        except Exception:
            pass
    except Exception as exc:
        print(f"Error generating response: {exc}")
        return 1
    print(output)

    if not args.no_save:
        importance = min(
            0.95, 0.45 + emotion["intensity"] * 0.3 + dissonance["score"] * 0.15
        )
        memory.save_interaction(
            prompt,
            output,
            mode=state.mode,
            emotion=emotion,
            importance=importance,
            dissonance=dissonance,
        )
        history.append(prompt, output, state.mode, emotion, dissonance)
    return 0


def cmd_web(_args):
    return run_script("run_web.sh")


def cmd_health(args):
    env = {"LIVE_API_CHECK": "1"} if args.live else None
    return run_script("health_check.sh", env)


def cmd_backup(args):
    command = [str(PROJECT_ROOT / "scripts" / "backup.sh")]
    if args.output:
        command.append(args.output)
    return subprocess.call(command, cwd=str(PROJECT_ROOT))


def cmd_restore(args):
    command = [str(PROJECT_ROOT / "scripts" / "restore.sh"), args.source]
    if args.target:
        command.append(args.target)
    return subprocess.call(command, cwd=str(PROJECT_ROOT))


def cmd_path(_args):
    print(PROJECT_ROOT)
    return 0


def cmd_meow(_args):
    from infj_bot.core.plugins.meow_scanner import meow_hunt

    print(meow_hunt(str(PROJECT_ROOT)))
    return 0


def cmd_bug(args):
    from infj_bot.core.bug_bot import BugBot

    bot = BugBot()
    subcmd = args.subcmd or "health"
    if subcmd == "sync":
        print(bot.sync_programs())
    elif subcmd == "programs":
        print(bot.list_programs())
    elif subcmd == "recon":
        print(bot.recon(args.program, args.tool))
    elif subcmd == "list":
        print(bot.list_findings(program_id=args.program, status=args.status))
    elif subcmd == "get":
        print(bot.get_finding(args.id))
    elif subcmd == "report":
        print(bot.generate_report(args.id))
    elif subcmd == "preview":
        print(bot.preview_report(args.id))
    elif subcmd == "submit":
        print(bot.submit(args.id))
    elif subcmd == "stats":
        print(bot.stats())
    elif subcmd == "health":
        print(bot.health())
    else:
        print(f"Unknown bug subcommand: {subcmd}")
        return 1
    return 0


def build_parser():
    parser = argparse.ArgumentParser(
        prog="infj_bot",
        description="CLI launcher for the local INFJ companion bot.",
    )
    sub = parser.add_subparsers(dest="command")

    chat = sub.add_parser("chat", help="Start the interactive terminal chat.")
    chat.set_defaults(func=cmd_chat)

    tui = sub.add_parser("tui", help="Start the rich TUI interface.")
    tui.set_defaults(func=cmd_tui)

    ask = sub.add_parser("ask", help="Ask a one-shot prompt and print the response.")
    ask.add_argument(
        "--mode",
        default="companion",
        choices=[
            "companion",
            "engineer",
            "critic",
            "coach",
            "clarity",
            "researcher",
            "bughunter",
            "drift",
            "quiet",
        ],
    )
    ask.add_argument(
        "--no-save",
        action="store_true",
        help="Do not save this one-shot exchange to memory/history.",
    )
    ask.add_argument(
        "--no-tools", action="store_true", help="Disable tool-use for this one-shot."
    )
    ask.add_argument("prompt", nargs=argparse.REMAINDER)
    ask.set_defaults(func=cmd_ask)

    web = sub.add_parser("web", help="Start the web UI on 127.0.0.1:8765.")
    web.set_defaults(func=cmd_web)

    health = sub.add_parser("health", help="Run the local health check.")
    health.add_argument(
        "--live",
        action="store_true",
        help="Also call the configured Gemini model once.",
    )
    health.set_defaults(func=cmd_health)

    backup = sub.add_parser("backup", help="Create a backup archive.")
    backup.add_argument("output", nargs="?", help="Optional output tar.gz path.")
    backup.set_defaults(func=cmd_backup)

    restore = sub.add_parser("restore", help="Restore from a backup directory.")
    restore.add_argument(
        "source", help="Backup directory, such as the PortableSSD handoff path."
    )
    restore.add_argument("target", nargs="?", help="Optional restore target directory.")
    restore.set_defaults(func=cmd_restore)

    path = sub.add_parser("path", help="Print the bot project path.")
    path.set_defaults(func=cmd_path)

    bug = sub.add_parser(
        "bug", help="Bug bounty engine — sync, recon, findings, reports."
    )
    bug.add_argument(
        "subcmd",
        nargs="?",
        help="sync | programs | recon | list | get | report | preview | submit | stats | health",
    )
    bug.add_argument("--program", "-p", default="", help="Program ID for recon/list.")
    bug.add_argument(
        "--tool",
        "-t",
        default="all",
        help="Recon tool: all | subdomains | nuclei | fuzz",
    )
    bug.add_argument("--status", "-s", default="", help="Filter findings by status.")
    bug.add_argument(
        "--id", "-i", default="", help="Finding ID for get/report/preview/submit."
    )
    bug.set_defaults(func=cmd_bug)

    meow = sub.add_parser("meow", help="Run the chaos gremlin code scanner.")
    meow.set_defaults(func=cmd_meow)

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    if not args.command:
        args = parser.parse_args(["chat"])
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
