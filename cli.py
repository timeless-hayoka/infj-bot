#!/usr/bin/env python3
import argparse
import asyncio
import os
import subprocess
import sys

from config import PROJECT_ROOT


def run_script(script_name, extra_env=None):
    env = os.environ.copy()
    if extra_env:
        env.update(extra_env)
    script = PROJECT_ROOT / "scripts" / script_name
    return subprocess.call([str(script)], cwd=str(PROJECT_ROOT), env=env)


def cmd_chat(_args):
    from main import main

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[*] Manual override. Powering down.")
        return 130
    return 0


def cmd_tui(_args):
    from tui import InfjTUI

    try:
        InfjTUI().run()
    except KeyboardInterrupt:
        print("\n[*] Manual override. Powering down.")
        return 130
    return 0


def cmd_ask(args):
    from brain import InfjBrain
    from commands import BotState
    from history import ChatHistory
    from memory import InfjMemory
    from prompt_builder import build_chat_prompt
    from goals import GoalsDB
    from documents import DocumentStore

    prompt = " ".join(args.prompt).strip()
    if not prompt:
        print(
            "Give me something to ask. Example: infj_bot ask what should I focus on today?"
        )
        return 2

    from config import DEFAULT_AUTHORIZED_TARGETS

    state = BotState(
        mode=args.mode,
        proactive_enabled=False,
        authorized_targets=set(DEFAULT_AUTHORIZED_TARGETS),
    )
    brain = InfjBrain()
    memory = InfjMemory()
    history = ChatHistory()
    goals_db = GoalsDB()
    doc_store = DocumentStore()
    built_prompt, emotion, dissonance = build_chat_prompt(
        prompt,
        state,
        memory,
        goals_db=goals_db,
        doc_store=doc_store,
        tools_enabled=not args.no_tools,
        prefs=state.prefs,
    )
    try:
        output = brain.agent_turn(built_prompt, tools_enabled=not args.no_tools)
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

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    if not args.command:
        args = parser.parse_args(["chat"])
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
