#!/usr/bin/env python3
import argparse
import importlib.util
import json
import asyncio
import os
import shutil
import subprocess
import webbrowser
from pathlib import Path
import sys
import requests

from drift.config_adapter import PROJECT_ROOT

CLI_PROG = os.getenv("DRIFT_CLI_PROG", "drift")


def run_script(script_name, extra_env=None):
    env = os.environ.copy()
    if extra_env:
        env.update(extra_env)
    script = PROJECT_ROOT / "scripts" / script_name
    return subprocess.call([str(script)], cwd=str(PROJECT_ROOT), env=env)


def cmd_chat(_args):
    from drift.interfaces.main import main

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[*] Manual override. Powering down.")
        return 130
    return 0


def cmd_tui(_args):
    from drift.core.plugins.tui import DriftTUI

    try:
        DriftTUI().run()
    except KeyboardInterrupt:
        print("\n[*] Manual override. Powering down.")
        return 130
    return 0


def cmd_ask(args):
    from drift.core.brain import DriftBrain
    from drift.core.commands import BotState
    from drift.core.history import ChatHistory
    from drift.core.memory import DriftMemory
    from drift.core.prompt_builder import build_chat_prompt
    from drift.core.plugins.goals import GoalsDB
    from drift.core.plugins.documents import DocumentStore

    prompt = " ".join(args.prompt).strip()
    if not prompt:
        print(
            "Give me something to ask. Example: drift ask what should I focus on today?"
        )
        return 2

    from drift.core.config import DEFAULT_AUTHORIZED_TARGETS

    state = BotState(
        mode=args.mode,
        proactive_enabled=False,
        authorized_targets=set(DEFAULT_AUTHORIZED_TARGETS),
    )
    brain = DriftBrain()
    memory = DriftMemory()
    history = ChatHistory()
    
    # Phase 5: Wire deliberation bridge
    from drift.core.cognitive_orchestrator import CognitiveOrchestrator
    _orchestrator = CognitiveOrchestrator()
    _orchestrator.memory = memory
    _orchestrator.brain = brain

    # Phase 6: Unified Audit
    from drift.core.unified_audit import wire_orchestrator_audit
    wire_orchestrator_audit(_orchestrator)

    def deliberation_bridge(goal: str):
        """Synchronous bridge for CLI deliberation, avoiding deadlocks."""
        import asyncio
        from drift.core.hive.elysium import DeliberationResult
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
    from drift.core.being import get_being
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
        from drift.core.cognitive_orchestrator import IntentBlockedError
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
    from drift.core.plugins.meow_scanner import meow_hunt

    print(meow_hunt(str(PROJECT_ROOT)))
    return 0


def cmd_bridge(args):
    """Interface with the SSH bridge proxy."""
    url = "http://127.0.0.1:8000/run"
    subcmd = args.subcmd
    
    if subcmd == "run":
        cmd_text = " ".join(args.cmd_args)
        if not cmd_text:
            print("Error: No command provided to run.")
            return 1
        try:
            response = requests.post(url, json={"cmd": cmd_text})
            response.raise_for_status()
            data = response.json()
            if data["stdout"]:
                print(data["stdout"], end="")
            if data["stderr"]:
                print(f"STDERR: {data['stderr']}", file=sys.stderr)
            return 0 if data["status"] == "success" else 1
        except Exception as e:
            print(f"Bridge error: {e}")
            return 1
    elif subcmd == "shell":
        print("[*] Entering Bridge Shell. Type 'exit' to quit.")
        while True:
            try:
                cmd_text = input("infj-bridge> ").strip()
                if cmd_text.lower() in ["exit", "quit"]:
                    break
                if not cmd_text:
                    continue
                response = requests.post(url, json={"cmd": cmd_text})
                response.raise_for_status()
                data = response.json()
                if data["stdout"]:
                    print(data["stdout"], end="")
                if data["stderr"]:
                    print(f"STDERR: {data['stderr']}", file=sys.stderr)
            except KeyboardInterrupt:
                print()
                break
            except Exception as e:
                print(f"Bridge error: {e}")
        return 0
    else:
        print(f"Unknown bridge subcommand: {subcmd}. Use 'run' or 'shell'.")
        return 1


def cmd_bug(args):
    from drift.core.bug_bot import BugBot

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




def _trinity_ledger(args):
    return _trinity_ledger_entry(args)



def _trinity_result_to_text(result):
    scan = result.get('scan') or {}
    packet = result.get('packet') or {}
    lines = [
        f"Case: {result.get('case_id', 'unknown')}",
        f"Scanner format: {scan.get('format', 'unknown')}",
        f"Findings: {scan.get('finding_count', 0)}",
        f"Claim ID: {result.get('result', {}).get('claim_id') or result.get('claim_id') or 'unknown'}",
        f"Packet status: {packet.get('status', 'unknown')}",
        f"Report path: {result.get('report_path', 'unknown')}",
        f"Output dir: {result.get('output_dir', 'unknown')}",
    ]
    reproduction = packet.get('reproduction_command') or result.get('result', {}).get('reproduction_command')
    if reproduction:
        lines.append(f"Reproduction: {reproduction}")
    if packet.get('reasoning_summary'):
        lines.extend(['', 'Reasoning summary:', packet['reasoning_summary']])
    return '\n'.join(lines)


def _trinity_analyze_plan(scan, *, case_id, output_dir, no_packet):
    planned_output = str(output_dir) if output_dir else f"./trinity_cases/{case_id}"
    top_finding = (scan.get('findings') or [{}])[0] if scan.get('findings') else {}
    return {
        'case_id': case_id,
        'scanner_format': scan.get('format', 'unknown'),
        'finding_count': scan.get('finding_count', 0),
        'planned_output_dir': planned_output,
        'packet_will_write': not no_packet,
        'top_finding': {
            'title': top_finding.get('title'),
            'summary': top_finding.get('summary'),
            'evidence_ref': top_finding.get('evidence_ref'),
        },
    }


def _trinity_case_summary(bundle, case_root):
    claim = bundle.get('claim') or {}
    packet = bundle.get('packet') or bundle
    scan = bundle.get('scan') or {}
    lines = [
        f"Case: {bundle.get('case_id', claim.get('id', 'unknown'))}",
        f"Status: {packet.get('status', bundle.get('status', 'unknown'))}",
        f"Scanner format: {scan.get('format', claim.get('scanner', 'unknown'))}",
        f"Findings: {scan.get('finding_count', claim.get('finding_count', 0))}",
        f"Claim ID: {claim.get('id') or packet.get('claim', {}).get('id') or 'unknown'}",
        f"Output dir: {case_root}",
    ]
    reproduction = packet.get('reproduction_command') or bundle.get('reproduction_command') or claim.get('reproduction_command')
    if reproduction:
        lines.append(f"Reproduction: {reproduction}")
    return '\n'.join(lines)


def _trinity_export_bundle(case_root, output_dir):
    src = Path(case_root)
    dst = Path(output_dir)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src, dst, dirs_exist_ok=True)
    return dst


def _trinity_ledger_entry(args):
    from drift.trinity.caseflow import TRINITY_LEDGER_PATH, TrinityCaseLedger

    ledger_path = Path(getattr(args, 'ledger_path', '') or TRINITY_LEDGER_PATH)
    return TrinityCaseLedger(ledger_path)


def _trinity_case_root(case_ref, args=None):
    from drift.trinity.caseflow import resolve_case_root

    ledger = _trinity_ledger_entry(args) if args is not None else None
    return resolve_case_root(case_ref, ledger=ledger)



def cmd_trinity_case_list(args):
    return cmd_trinity_cases(args)


def cmd_trinity_case_show(args):
    from drift.trinity.caseflow import load_case_bundle

    ledger = _trinity_ledger(args)
    case_root = _trinity_case_root(args.case_ref, args)
    if case_root is None:
        print(f"Trinity case not found: {args.case_ref}", file=sys.stderr)
        return 1

    bundle = load_case_bundle(case_root)
    if args.format == 'json':
        print(json.dumps(bundle, indent=2, ensure_ascii=False))
    else:
        print(_trinity_case_summary(bundle, case_root))
    return 0


def cmd_trinity_case_report(args):
    return cmd_trinity_report(args)


def cmd_trinity_case_export(args):
    from drift.trinity.caseflow import load_case_bundle

    case_root = _trinity_case_root(args.case_ref, args)
    if case_root is None:
        print(f"Trinity case not found: {args.case_ref}", file=sys.stderr)
        return 1

    export_root = _trinity_export_bundle(case_root, args.output)
    bundle = load_case_bundle(case_root)
    if args.format == 'json':
        print(json.dumps({'case_ref': args.case_ref, 'export_dir': str(export_root), 'bundle': bundle}, indent=2, ensure_ascii=False))
    else:
        print(f"Exported Trinity case {bundle.get('case_id', args.case_ref)} to {export_root}")
    return 0


def cmd_trinity_packet_show(args):
    return cmd_trinity_packet(args)


def cmd_trinity_packet_export(args):
    from drift.trinity.caseflow import load_case_bundle

    case_root = _trinity_case_root(args.case_ref, args)
    if case_root is None:
        print(f"Trinity case not found: {args.case_ref}", file=sys.stderr)
        return 1

    export_root = _trinity_export_bundle(case_root, args.output)
    bundle = load_case_bundle(case_root)
    if args.format == 'json':
        print(json.dumps({'case_ref': args.case_ref, 'export_dir': str(export_root), 'bundle': bundle}, indent=2, ensure_ascii=False))
    else:
        print(f"Exported Trinity packet {bundle.get('case_id', args.case_ref)} to {export_root}")
    return 0


def cmd_trinity_ledger_list(args):
    return cmd_trinity_cases(args)


def cmd_trinity_ledger_show(args):
    ledger = _trinity_ledger(args)
    entry = ledger.find(args.case_ref)
    if entry is None:
        print(f"Trinity ledger entry not found: {args.case_ref}", file=sys.stderr)
        return 1
    if args.format == 'json':
        print(json.dumps(entry, indent=2, ensure_ascii=False))
    else:
        print(
            f"Case: {entry.get('case_id', 'unknown')}\n"
            f"Status: {entry.get('status', 'unknown')}\n"
            f"Scanner format: {entry.get('scanner_format', 'unknown')}\n"
            f"Findings: {entry.get('finding_count', 0)}\n"
            f"Output dir: {entry.get('output_dir', '')}"
        )
    return 0


def cmd_trinity_analyze(args):
    from drift.trinity.caseflow import build_case_context, parse_scanner_input, run_case_from_scan

    try:
        scan = parse_scanner_input(args.input, format_hint=args.format_hint)
        case_id = args.case_id or scan['case_id']
        if getattr(args, 'dry_run', False):
            plan = _trinity_analyze_plan(
                scan,
                case_id=case_id,
                output_dir=args.output,
                no_packet=getattr(args, 'no_packet', False),
            )
            if args.format == 'json':
                print(json.dumps(plan, indent=2, ensure_ascii=False))
            else:
                print('Trinity dry run.')
                print(f"Case: {plan['case_id']}")
                print(f"Scanner format: {plan['scanner_format']}")
                print(f"Findings: {plan['finding_count']}")
                print(f"Planned output dir: {plan['planned_output_dir']}")
                print(f"Would write packet: {'yes' if plan['packet_will_write'] else 'no'}")
                top = plan['top_finding']
                if top.get('title'):
                    print(f"Top finding: {top['title']}")
                if top.get('summary'):
                    print(f"Top summary: {top['summary']}")
            return 0

        ledger = _trinity_ledger(args)
        result = run_case_from_scan(
            args.input,
            format_hint=args.format_hint,
            output_dir=args.output,
            case_id=args.case_id,
            subject=args.subject,
            reproduction_command=args.reproduction_command,
            ledger=ledger,
            write_bundle=not getattr(args, 'no_packet', False),
        )
    except FileNotFoundError as exc:
        print(f"Trinity analyze error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Trinity analyze error: {exc}", file=sys.stderr)
        return 1

    if args.format == 'json':
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(_trinity_result_to_text(result))
        if getattr(args, 'no_packet', False):
            print('Packet bundle writing skipped by --no-packet.')
    return 0



def cmd_trinity_report(args):
    from drift.trinity.caseflow import load_case_bundle, load_case_report, resolve_case_root

    ledger = _trinity_ledger(args)
    case_root = resolve_case_root(args.case_ref, ledger=ledger)
    if case_root is None:
        print(f"Trinity case not found: {args.case_ref}", file=sys.stderr)
        return 1

    if args.format == 'json':
        bundle = load_case_bundle(case_root)
        bundle['report'] = load_case_report(case_root)
        print(json.dumps(bundle, indent=2, ensure_ascii=False))
    else:
        print(load_case_report(case_root))
    return 0



def cmd_trinity_packet(args):
    from drift.trinity.caseflow import load_case_bundle, load_case_report, resolve_case_root

    ledger = _trinity_ledger(args)
    case_root = resolve_case_root(args.case_ref, ledger=ledger)
    if case_root is None:
        print(f"Trinity case not found: {args.case_ref}", file=sys.stderr)
        return 1

    bundle = load_case_bundle(case_root)
    if args.format == 'markdown':
        print(load_case_report(case_root))
    else:
        print(json.dumps(bundle, indent=2, ensure_ascii=False))
    return 0



def cmd_trinity_cases(args):
    ledger = _trinity_ledger(args)
    entries = ledger.recent(limit=args.limit)

    if args.format == 'json':
        print(json.dumps(entries, indent=2, ensure_ascii=False))
        return 0

    if not entries:
        print('No Trinity cases recorded yet.')
        return 0

    for entry in reversed(entries):
        print(
            f"{entry.get('case_id', 'unknown')} | "
            f"{entry.get('status', 'unknown')} | "
            f"{entry.get('scanner_format', 'unknown')} | "
            f"findings={entry.get('finding_count', 0)} | "
            f"{entry.get('output_dir', '')}"
        )
    return 0


def _trinity_release_info():
    from drift.trinity.release import get_release_info

    return get_release_info()


def cmd_version(args):
    from drift.trinity.release import render_release_text

    release = _trinity_release_info()
    if getattr(args, 'json', False):
        print(json.dumps(release, indent=2, ensure_ascii=False))
    else:
        print(render_release_text(release))
    return 0


def cmd_manifest(args):
    from drift.trinity.release import RELEASE_MANIFEST_PATH, get_release_info

    release = get_release_info()
    manifest_path = Path(release.get("manifest_path", RELEASE_MANIFEST_PATH))
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            manifest = release
    else:
        manifest = release
    if getattr(args, 'json', False):
        print(json.dumps({"manifest": manifest, "release": release}, indent=2, ensure_ascii=False))
    else:
        tests = manifest.get('tests_passed')
        warnings = manifest.get('warnings')
        print(f"{manifest.get('product', 'ANCHOR')} {manifest.get('version', 'unknown')}")
        print(f"Status: {manifest.get('status', 'unknown')}")
        print("Powered by Trinity")
        print(f"Build Date: {manifest.get('build_date', manifest.get('build', 'unknown'))}")
        print(f"Build ID: {manifest.get('build_id', release.get('build_id', 'unknown'))}")
        print("")
        print("Components:")
        print(f"  Engine: {manifest.get('engine', 'Trinity')}")
        print("  Validation: Forge")
        print("  Governance: Council")
        print("")
        print("Tests:")
        print(f"  Passed: {tests if tests is not None else 'unknown'}")
        print(f"  Warnings: {warnings if warnings is not None else 'unknown'}")
        print("")
        health = 'PASS' if manifest.get('status') == 'release_candidate' else 'CHECK'
        print(f"Release Health: {health}")
        print(f"Manifest path: {manifest_path}")
    return 0


def cmd_history(args):
    from drift.trinity.release import load_history, render_history_text, summarize_history

    entries = load_history(
        limit=getattr(args, 'limit', 20),
        ledger_path=getattr(args, 'ledger_path', None),
        case_id=getattr(args, 'case_id', None),
        status=getattr(args, 'status', None),
        scanner_format=getattr(args, 'scanner_format', None),
    )
    if getattr(args, 'json', False):
        payload = {'summary': summarize_history(entries), 'entries': entries}
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(render_history_text(entries))
    return 0


def cmd_archive_create(args):
    from drift.trinity.release import create_archive

    try:
        result = create_archive(
            args.case_ref,
            output_dir=getattr(args, 'output', None),
            ledger_path=getattr(args, 'ledger_path', None),
            archive_ledger_path=getattr(args, 'archive_ledger_path', None),
            zip_output=getattr(args, 'zip', False),
        )
    except FileNotFoundError as exc:
        print(f'Trinity archive error: {exc}', file=sys.stderr)
        return 1
    if getattr(args, 'json', False):
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(f"Created archive {result['archive_id']} for case {result['case_id']}")
        print(f"Archive dir: {result['archive_dir']}")
        if result.get('zip_path'):
            print(f"Zip: {result['zip_path']}")
    return 0


def cmd_archive_list(args):
    from drift.trinity.release import list_archives

    records = list_archives(
        limit=getattr(args, 'limit', 20),
        archive_ledger_path=getattr(args, 'archive_ledger_path', None),
    )
    if getattr(args, 'json', False):
        print(json.dumps(records, indent=2, ensure_ascii=False))
    else:
        if not records:
            print('No Trinity archives recorded yet.')
        else:
            for record in reversed(records):
                print(
                    f"{record.get('archive_id', 'unknown')} | "
                    f"{record.get('case_id', 'unknown')} | "
                    f"{record.get('status', 'unknown')} | "
                    f"{record.get('archive_dir', '')}"
                )
    return 0


def cmd_archive_show(args):
    from drift.trinity.release import load_archive_record, render_archive_text

    try:
        record = load_archive_record(
            args.archive_ref,
            archive_ledger_path=getattr(args, 'archive_ledger_path', None),
        )
    except FileNotFoundError as exc:
        print(f'Trinity archive error: {exc}', file=sys.stderr)
        return 1
    if getattr(args, 'json', False):
        print(json.dumps(record, indent=2, ensure_ascii=False))
    else:
        print(render_archive_text(record))
    return 0


def cmd_export_report(args):
    from drift.trinity.release import brand_public_report_text, export_case_report

    try:
        result = export_case_report(
            args.case_ref,
            output=getattr(args, 'output', None),
            ledger_path=getattr(args, 'ledger_path', None),
        )
    except FileNotFoundError as exc:
        print(f'Trinity export error: {exc}', file=sys.stderr)
        return 1
    if getattr(args, 'json', False):
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(f"Exported report for {result['case_id']}")
        if result.get('output_path'):
            print(f"Report path: {result['output_path']}")
    return 0


def cmd_upgrade(args):
    from drift.trinity.release import build_upgrade_plan, render_upgrade_text

    plan = build_upgrade_plan(apply=getattr(args, 'apply', False))
    if getattr(args, 'json', False):
        print(json.dumps(plan, indent=2, ensure_ascii=False))
    else:
        print(render_upgrade_text(plan))
    return 0


def _trinity_completion_script(shell):
    common = "chat tui ask web bridge health backup restore path doctor status setup dashboard version manifest release history archive export-report upgrade help about trinity bug meow completion"
    trinity = "analyze case report cases packet ledger demo"
    case = "list show report export"
    packet = "show export"
    ledger = "list show"

    if shell == "bash":
        script = r'''_trin_complete() {
    local cur prev words cword
    _init_completion || return
    local cmds="__COMMON__"
    if [[ $cword -eq 1 ]]; then
        COMPREPLY=( $(compgen -W "$cmds" -- "$cur") )
        return
    fi
    if [[ ${words[1]} == trinity ]]; then
        if [[ $cword -eq 2 ]]; then
            COMPREPLY=( $(compgen -W "__TRINITY__" -- "$cur") )
            return
        fi
        case "${words[2]}" in
            case)
                [[ $cword -eq 3 ]] && COMPREPLY=( $(compgen -W "__CASE__" -- "$cur") )
                ;;
            packet)
                [[ $cword -eq 3 ]] && COMPREPLY=( $(compgen -W "__PACKET__" -- "$cur") )
                ;;
            ledger)
                [[ $cword -eq 3 ]] && COMPREPLY=( $(compgen -W "__LEDGER__" -- "$cur") )
                ;;
        esac
    fi
}
complete -F _trin_complete trin drift anchor
'''
        return (script.replace('__COMMON__', common)
                    .replace('__TRINITY__', trinity)
                    .replace('__CASE__', case)
                    .replace('__PACKET__', packet)
                    .replace('__LEDGER__', ledger))

    if shell == "zsh":
        return r'''#compdef trin drift anchor
_trin_complete() {
  local -a commands
  commands=(chat tui ask web bridge health backup restore path doctor status setup dashboard version manifest release history archive export-report upgrade help about trinity bug meow completion)
  if (( CURRENT == 2 )); then
    _describe 'command' commands
    return
  fi
  if [[ $words[2] == trinity ]]; then
    local -a subcommands
    subcommands=(analyze case report cases packet ledger demo)
    if (( CURRENT == 3 )); then
      _describe 'trinity command' subcommands
      return
    fi
  fi
}
compdef _trin_complete trin drift
'''

    if shell == "fish":
        return r'''complete -c trin -c drift -c anchor -f -a "chat tui ask web bridge health backup restore path doctor status setup dashboard version manifest release history archive export-report upgrade help about trinity bug meow completion"
complete -c trin -c drift -n '__fish_seen_subcommand_from trinity' -f -a "analyze case report cases packet ledger demo"
complete -c trin -c drift -n '__fish_seen_subcommand_from trinity; and __fish_seen_subcommand_from case' -f -a "list show report export"
complete -c trin -c drift -n '__fish_seen_subcommand_from trinity; and __fish_seen_subcommand_from packet' -f -a "show export"
complete -c trin -c drift -n '__fish_seen_subcommand_from trinity; and __fish_seen_subcommand_from ledger' -f -a "list show"
'''

    raise ValueError(f'Unsupported shell: {shell}')


def cmd_completion(args):
    try:
        print(_trinity_completion_script(args.shell))
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    return 0


def _append_unique_line(path: Path, line: str) -> bool:
    current = path.read_text() if path.exists() else ""
    if line in current:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        if current and not current.endswith("\n"):
            handle.write("\n")
        handle.write(line + "\n")
    return True

def _write_completion_install(shell: str) -> dict:
    if shell == "bash":
        dest = Path.home() / ".local/share/bash-completion/completions/trin"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(_trinity_completion_script("bash"), encoding="utf-8")
        hook = '[ -f "$HOME/.local/share/bash-completion/completions/trin" ] && source "$HOME/.local/share/bash-completion/completions/trin"'
        rc_path = Path.home() / ".bashrc"
        return {
            "shell": shell,
            "file": str(dest),
            "hook_added": _append_unique_line(rc_path, hook),
        }
    if shell == "zsh":
        dest = Path.home() / ".local/share/zsh/site-functions/_trin"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(_trinity_completion_script("zsh"), encoding="utf-8")
        hook = 'fpath+=("$HOME/.local/share/zsh/site-functions")'
        rc_path = Path.home() / ".zshrc"
        return {
            "shell": shell,
            "file": str(dest),
            "hook_added": _append_unique_line(rc_path, hook),
        }
    raise ValueError(f"Unsupported shell: {shell}")


def _trinity_status_summary() -> dict:
    status_script = PROJECT_ROOT / "scripts" / "trin_status.py"
    if status_script.exists():
        command = [sys.executable, str(status_script), "--json"]
        cwd = str(PROJECT_ROOT)
    else:
        command = [sys.executable, "-m", "interfaces.cli", "doctor", "--json"]
        cwd = str(PROJECT_ROOT)
    proc = subprocess.run(command, cwd=cwd, capture_output=True, text=True, check=False)
    output = proc.stdout.strip() or proc.stderr.strip()
    if not output:
        raise RuntimeError(f"trin status produced no output (exit code {proc.returncode})")
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"trin status did not return JSON: {exc}. Raw output: {output[:500]}") from exc


def cmd_status(args):
    try:
        summary = _trinity_status_summary()
    except Exception as exc:
        payload = {"healthy": False, "status": "error", "error": str(exc)}
        if getattr(args, "json", False):
            print(json.dumps(payload, indent=2, ensure_ascii=False))
        else:
            print("\n".join(_anchor_public_header()))
            print("ANCHOR STATUS")
            print("Evidence Before Belief")
            print(f"Health: FAIL")
            print(f"Error: {exc}")
        return 1

    if getattr(args, "json", False):
        print(json.dumps(summary, indent=2, ensure_ascii=False))
    else:
        doctor = summary.get("doctor", {})
        checks = doctor.get("checks", [])
        release = summary.get("release", {})
        print("\n".join(_anchor_public_header()))
        print("ANCHOR STATUS")
        print("Evidence Before Belief")
        print(f"Health: {'PASS' if summary.get('healthy') else 'FAIL'}")
        if release:
            print(
                f"Release: ANCHOR {release.get('version', 'unknown')} "
                f"({release.get('commit', 'unknown')})"
            )
        for check in checks:
            marker = "OK" if check.get("ok") else "FAIL"
            print(f"{check.get('name', 'Unknown')}: {marker}")
        fixes = summary.get("fixes", [])
        if fixes:
            print("Suggested fixes:")
            for idx, fix in enumerate(fixes, start=1):
                print(f"  {idx}. {fix.get('summary', fix.get('issue', 'unknown'))}")
    return 0 if summary.get("healthy") else 1


def cmd_setup(args):
    results = [_write_completion_install("bash"), _write_completion_install("zsh")]
    logs_dir = Path.home() / ".drift_os/logs"
    logs_dir.mkdir(parents=True, exist_ok=True)

    payload = {
        "status": "ok",
        "bootstrap": {
            "logs_dir": str(logs_dir),
            "completion_results": results,
        },
    }
    if getattr(args, "json", False):
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print("ANCHOR setup complete.")
        for result in results:
            state = "installed" if result.get("hook_added") else "already present"
            print(f"[{result['shell']}] {state}: {result['file']}")
        print(f"Logs directory ready: {logs_dir}")
    return 0


def cmd_dashboard(args):
    dashboard_url = getattr(args, "url", "http://127.0.0.1:8765")
    script = PROJECT_ROOT / "scripts" / "run_web.sh"
    proc = subprocess.Popen([str(script)], cwd=str(PROJECT_ROOT))
    if not getattr(args, "no_open", False):
        try:
            webbrowser.open(dashboard_url)
        except Exception:
            pass
    print("\n".join(_anchor_public_header()))
    print(f"ANCHOR dashboard starting at {dashboard_url} (pid {proc.pid})")
    print("Evidence Before Belief")
    return 0


def _anchor_public_header() -> list[str]:
    return [
        'ANCHOR',
        'Evidence Before Belief',
        '',
        'Powered by Trinity',
        '',
    ]


def cmd_help(args):
    parser = build_parser()
    print('\n'.join(_anchor_public_header()) + parser.format_help())
    return 0


def cmd_about(args):
    lines = [
        'ANCHOR',
        'Public Platform',
        '',
        'DRIFT      - Cognitive Engine',
        'TRINITY    - Reasoning Architecture',
        'FORGE      - Validation Engine',
        'COUNCIL    - Claim Adjudication',
        '',
        'Powered by Trinity',
    ]
    print('\n'.join(lines))
    return 0


def _doctor_check(checks, name, ok, detail, critical=False):
    checks.append(
        {
            "name": name,
            "ok": bool(ok),
            "detail": detail,
            "critical": bool(critical),
        }
    )


def _doctor_fixes(checks, critical_missing, warn_missing):
    fixes = []
    if any(check["name"] == "Launcher" and not check["ok"] for check in checks):
        fixes.append(
            {
                "issue": "launcher",
                "summary": "Reinstall or relink the `trin` launcher so it points at /home/crexs/infj_bot/.venv/bin/python -m interfaces.cli (and keep `anchor` synced).",
                "command": "ln -sf /home/crexs/.local/bin/drift /home/crexs/.local/bin/trin && ln -sf /home/crexs/.local/bin/trin /home/crexs/.local/bin/anchor",
            }
        )
    if any(check["name"] == "Python" and not check["ok"] for check in checks):
        fixes.append(
            {
                "issue": "python",
                "summary": "Use the repo virtualenv at /home/crexs/infj_bot/.venv or recreate it with the project setup flow.",
                "command": "cd /home/crexs/infj_bot && python3 -m venv .venv && .venv/bin/python -m pip install -e .",
            }
        )
    if critical_missing:
        fixes.append(
            {
                "issue": "modules",
                "summary": "Install the missing Trinity modules in the repo venv.",
                "command": "cd /home/crexs/infj_bot && .venv/bin/python -m pip install -e .",
            }
        )
    if "prometheus_client" in warn_missing:
        fixes.append(
            {
                "issue": "prometheus_client",
                "summary": "Install prometheus-client in the repo venv.",
                "command": "cd /home/crexs/infj_bot && .venv/bin/python -m pip install prometheus-client",
            }
        )

    completion_ok = any(check["name"] == "Bash completion" and check["ok"] for check in checks)
    if not completion_ok:
        fixes.append(
            {
                "issue": "bash_completion",
                "summary": "Install bash completion by sourcing /home/crexs/.local/share/bash-completion/completions/trin from ~/.bashrc.",
                "command": "grep -qxF '[ -f \"$HOME/.local/share/bash-completion/completions/trin\" ] && source \"$HOME/.local/share/bash-completion/completions/trin\"' ~/.bashrc || printf '%s\n' '[ -f \"$HOME/.local/share/bash-completion/completions/trin\" ] && source \"$HOME/.local/share/bash-completion/completions/trin\"' >> ~/.bashrc",
            }
        )

    zsh_completion = Path.home() / ".local/share/zsh/site-functions/_trin"
    zshrc = Path.home() / ".zshrc"
    zsh_fpath_line = 'fpath+=("$HOME/.local/share/zsh/site-functions")'
    zshrc_text = zshrc.read_text() if zshrc.exists() else ""
    zsh_completion_ok = zsh_completion.exists() and zsh_fpath_line in zshrc_text
    _doctor_check(
        checks,
        "Zsh completion",
        zsh_completion_ok,
        f"file={zsh_completion.exists()} sourced={zsh_fpath_line in zshrc_text}",
        critical=False,
    )

    if not zsh_completion_ok:
        fixes.append(
            {
                "issue": "zsh_completion",
                "summary": "Install zsh completion and add the Trinity completions directory to ~/.zshrc.",
                "command": "mkdir -p ~/.local/share/zsh/site-functions && trin completion zsh > ~/.local/share/zsh/site-functions/_trin && grep -qxF 'fpath+=(\"$HOME/.local/share/zsh/site-functions\")' ~/.zshrc || printf '%s\n' 'fpath+=(\"$HOME/.local/share/zsh/site-functions\")' >> ~/.zshrc",
            }
        )

    db_check = next((check for check in checks if check["name"] == "Database"), None)
    if db_check and not db_check["ok"]:
        fixes.append(
            {
                "issue": "database",
                "summary": "Make the Trinity log directory writable or set TRINITY_DB_PATH to a writable location.",
                "command": 'mkdir -p ~/.drift_os/logs && touch ~/.drift_os/logs/trinity.db',
            }
        )

    return fixes


def cmd_doctor(args):
    checks = []
    output_format = "json" if getattr(args, "json", False) else getattr(args, "format", "text")
    root = PROJECT_ROOT
    launcher = shutil.which(CLI_PROG) or shutil.which("anchor") or shutil.which("drift") or shutil.which("trin")
    launcher_path = Path(launcher) if launcher else None
    _doctor_check(
        checks,
        "Launcher",
        launcher_path is not None and launcher_path.exists(),
        str(launcher_path) if launcher_path else "not found on PATH",
        critical=True,
    )

    python_path = Path(sys.executable)
    expected_pythons = [root / ".venv" / "bin" / "python", root / "venv" / "bin" / "python"]
    python_ok = python_path.exists()
    env_match = any(p.exists() and p.resolve() == python_path.resolve() for p in expected_pythons)
    python_detail = str(python_path)
    if not env_match:
        python_detail += " (not the repo venv)"
    _doctor_check(checks, "Python", python_ok, python_detail, critical=True)

    _doctor_check(
        checks,
        "Virtualenv",
        any(p.exists() for p in expected_pythons),
        ", ".join(str(p.parent) for p in expected_pythons if p.exists()) or "missing",
        critical=True,
    )

    anchor_path = shutil.which("anchor")
    _doctor_check(
        checks,
        "Anchor",
        anchor_path is not None and Path(anchor_path).exists(),
        str(anchor_path) if anchor_path else "not found on PATH",
        critical=True,
    )

    module_names = [
        "drift.trinity.caseflow",
        "drift.trinity.http_api",
        "drift.trinity.database",
        "fastapi",
        "mcp",
        "prometheus_client",
    ]
    module_states = []
    critical_missing = []
    warn_missing = []
    for module in module_names:
        present = importlib.util.find_spec(module) is not None
        module_states.append(f"{module}={'yes' if present else 'no'}")
        if module in {"drift.trinity.caseflow", "drift.trinity.http_api", "drift.trinity.database", "fastapi", "mcp"}:
            if not present:
                critical_missing.append(module)
        elif not present:
            warn_missing.append(module)
    _doctor_check(
        checks,
        "Modules",
        not critical_missing,
        ", ".join(module_states),
        critical=bool(critical_missing),
    )

    bash_completion = Path.home() / ".local/share/bash-completion/completions/trin"
    bashrc = Path.home() / ".bashrc"
    sourced_line = '[ -f "$HOME/.local/share/bash-completion/completions/trin" ] && source "$HOME/.local/share/bash-completion/completions/trin"'
    bashrc_text = bashrc.read_text() if bashrc.exists() else ""
    completion_ok = bash_completion.exists() and sourced_line in bashrc_text
    completion_detail = f"file={bash_completion.exists()} sourced={sourced_line in bashrc_text}"

    zsh_completion = Path.home() / ".local/share/zsh/site-functions/_trin"
    zshrc = Path.home() / ".zshrc"
    zsh_fpath_line = 'fpath+=("$HOME/.local/share/zsh/site-functions")'
    zshrc_text = zshrc.read_text() if zshrc.exists() else ""
    zsh_completion_ok = zsh_completion.exists() and zsh_fpath_line in zshrc_text
    _doctor_check(
        checks,
        "Zsh completion",
        zsh_completion_ok,
        f"file={zsh_completion.exists()} sourced={zsh_fpath_line in zshrc_text}",
        critical=False,
    )

    try:
        from drift.trinity.database import db as trinity_db

        db_path = Path(trinity_db.db_path)
        db_ok = db_path.parent.exists() and os.access(db_path.parent, os.W_OK)
        _doctor_check(
            checks,
            "Database",
            db_ok,
            str(db_path),
            critical=True,
        )
    except Exception as exc:
        _doctor_check(checks, "Database", False, str(exc), critical=True)

    smoke_checks = [
        (
            "Archive create smoke",
            [sys.executable, "-m", "interfaces.cli", "archive", "create", "--help"],
        ),
        (
            "Export report smoke",
            [sys.executable, "-m", "interfaces.cli", "export-report", "--help"],
        ),
    ]
    for name, command in smoke_checks:
        proc = subprocess.run(command, cwd=str(PROJECT_ROOT), capture_output=True, text=True, check=False)
        ok = proc.returncode == 0 and bool(proc.stdout.strip())
        detail = proc.stdout.strip().splitlines()[0] if proc.stdout.strip() else proc.stderr.strip().splitlines()[0] if proc.stderr.strip() else f"exit={proc.returncode}"
        _doctor_check(checks, name, ok, detail, critical=False)

    fixes = _doctor_fixes(checks, critical_missing, warn_missing) if getattr(args, "fix", False) else []

    if output_format == "json":
        payload = {
            "status": "ok" if not any(c["critical"] and not c["ok"] for c in checks) else "degraded",
            "checks": checks,
            "critical_missing_modules": critical_missing,
            "warning_missing_modules": warn_missing,
            "fixes": fixes,
        }
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print("\n".join(_anchor_public_header()))
        print("ANCHOR doctor")
        print("Evidence Before Belief")
        for check in checks:
            marker = "[✓]" if check["ok"] else ("[!]" if check["critical"] else "[-]")
            print(f"{marker} {check['name']}: {check['detail']}")
        if critical_missing:
            print(f"[!] Critical missing modules: {', '.join(critical_missing)}")
        if warn_missing:
            print(f"[-] Optional missing modules: {', '.join(warn_missing)}")
        if fixes:
            print("Suggested fixes:")
            print("Run these in order:")
            for idx, fix in enumerate(fixes, start=1):
                print(f"{idx}. {fix['summary']}")
                print(f"   $ {fix['command']}")
        if any(c["critical"] and not c["ok"] for c in checks):
            print("[!] ANCHOR needs attention.")
        else:
            print("[✓] No critical issues detected.")
    return 0 if not any(c["critical"] and not c["ok"] for c in checks) else 1


def cmd_trinity_demo(args):
    from drift.trinity.caseflow import run_demo_case

    try:
        ledger = _trinity_ledger(args)
        result = run_demo_case(
            output_dir=args.output,
            ledger=ledger,
            case_id=args.case_id,
            subject=args.subject,
        )
    except Exception as exc:
        print(f"Trinity demo error: {exc}", file=sys.stderr)
        return 1

    if args.format == 'json':
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print('Trinity demo complete.')
        print(_trinity_result_to_text(result))
        print(f"Bundle written to: {result.get('output_dir', 'unknown')}")
    return 0


def build_parser():
    parser = argparse.ArgumentParser(
        prog=CLI_PROG,
        description="ANCHOR / Trinity command-line interface.",
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

    status = sub.add_parser("status", help="Print a machine-readable ANCHOR/Trinity status summary.")
    status.add_argument(
        "--json",
        action="store_true",
        help="Emit JSON for automation.",
    )
    status.set_defaults(func=cmd_status)

    setup = sub.add_parser("setup", help="Bootstrap local ANCHOR/Trinity shell integration and directories.")
    setup.add_argument(
        "--json",
        action="store_true",
        help="Emit JSON for automation.",
    )
    setup.set_defaults(func=cmd_setup)

    dashboard = sub.add_parser("dashboard", help="Launch the ANCHOR/Trinity dashboard in your browser.")
    dashboard.add_argument(
        "--url",
        default="http://127.0.0.1:8765",
        help="Dashboard URL to open.",
    )
    dashboard.add_argument(
        "--no-open",
        action="store_true",
        help="Do not open a browser window automatically.",
    )
    dashboard.set_defaults(func=cmd_dashboard)

    bridge_parser = sub.add_parser("bridge", help="Interface with the SSH bridge.")
    bridge_parser.add_argument("subcmd", choices=["run", "shell"], help="run | shell")
    bridge_parser.add_argument("cmd_args", nargs=argparse.REMAINDER, help="Command to run (for 'run' subcmd)")
    bridge_parser.set_defaults(func=cmd_bridge)

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

    doctor = sub.add_parser("doctor", help="Check ANCHOR/Trinity launcher, deps, and local setup.")
    doctor.add_argument(
        "--json",
        action="store_true",
        help="Shortcut for --format json.",
    )
    doctor.add_argument(
        "--format",
        default="text",
        choices=["text", "json"],
        help="Output format for the health report.",
    )
    doctor.add_argument(
        "--fix",
        action="store_true",
        help="Show suggested fixes for any failing checks.",
    )
    doctor.set_defaults(func=cmd_doctor)

    version = sub.add_parser("version", help="Print the ANCHOR release version and build metadata.")
    version.add_argument(
        "--json",
        action="store_true",
        help="Emit JSON for automation.",
    )
    version.set_defaults(func=cmd_version)

    manifest = sub.add_parser("manifest", help="Show the ANCHOR release manifest.")
    manifest.add_argument(
        "--json",
        action="store_true",
        help="Emit JSON for automation.",
    )
    manifest.set_defaults(func=cmd_manifest)

    release_cmd = sub.add_parser("release", help="Show the ANCHOR release manifest.")
    release_cmd.add_argument(
        "--json",
        action="store_true",
        help="Emit JSON for automation.",
    )
    release_cmd.set_defaults(func=cmd_manifest)

    history = sub.add_parser("history", help="Show Trinity run history.")
    history.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Number of recent runs to show.",
    )
    history.add_argument(
        "--case-id",
        help="Optional case id filter.",
    )
    history.add_argument(
        "--status",
        help="Optional status filter.",
    )
    history.add_argument(
        "--scanner-format",
        help="Optional scanner format filter.",
    )
    history.add_argument(
        "--ledger-path",
        help="Optional Trinity case ledger path.",
    )
    history.add_argument(
        "--json",
        action="store_true",
        help="Emit JSON for automation.",
    )
    history.set_defaults(func=cmd_history)

    archive = sub.add_parser("archive", help="Create, list, or inspect Trinity archives.")
    archive_sub = archive.add_subparsers(dest="archive_command")
    archive.set_defaults(func=lambda _args, _parser=archive: (_parser.print_help() or 2))

    archive_create = archive_sub.add_parser(
        "create",
        help="Create an archive from a Trinity case bundle.",
    )
    archive_create.add_argument("case_ref", help="Case id or bundle directory.")
    archive_create.add_argument(
        "--output",
        help="Optional output directory for the archive root.",
    )
    archive_create.add_argument(
        "--ledger-path",
        help="Optional Trinity case ledger path.",
    )
    archive_create.add_argument(
        "--archive-ledger-path",
        help="Optional Trinity archive ledger path.",
    )
    archive_create.add_argument(
        "--zip",
        action="store_true",
        help="Also create a zip file beside the archive root.",
    )
    archive_create.add_argument(
        "--json",
        action="store_true",
        help="Emit JSON for automation.",
    )
    archive_create.set_defaults(func=cmd_archive_create)

    archive_list = archive_sub.add_parser(
        "list",
        help="List recent Trinity archives.",
    )
    archive_list.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Number of recent archives to show.",
    )
    archive_list.add_argument(
        "--archive-ledger-path",
        help="Optional Trinity archive ledger path.",
    )
    archive_list.add_argument(
        "--json",
        action="store_true",
        help="Emit JSON for automation.",
    )
    archive_list.set_defaults(func=cmd_archive_list)

    archive_show = archive_sub.add_parser(
        "show",
        help="Show a single Trinity archive record.",
    )
    archive_show.add_argument("archive_ref", help="Archive id or archive directory.")
    archive_show.add_argument(
        "--archive-ledger-path",
        help="Optional Trinity archive ledger path.",
    )
    archive_show.add_argument(
        "--json",
        action="store_true",
        help="Emit JSON for automation.",
    )
    archive_show.set_defaults(func=cmd_archive_show)

    export_report = sub.add_parser("export-report", help="Export an ANCHOR case report to a file.")
    export_report.add_argument("case_ref", help="Case id or bundle directory.")
    export_report.add_argument(
        "--output",
        help="Optional report output file.",
    )
    export_report.add_argument(
        "--ledger-path",
        help="Optional Trinity case ledger path.",
    )
    export_report.add_argument(
        "--json",
        action="store_true",
        help="Emit JSON for automation.",
    )
    export_report.set_defaults(func=cmd_export_report)

    upgrade = sub.add_parser("upgrade", help="Show or apply Trinity release upgrade steps.")
    upgrade.add_argument(
        "--apply",
        action="store_true",
        help="Run the upgrade commands instead of only printing them.",
    )
    upgrade.add_argument(
        "--json",
        action="store_true",
        help="Emit JSON for automation.",
    )
    upgrade.set_defaults(func=cmd_upgrade)

    help_cmd = sub.add_parser("help", help="Show the ANCHOR public command surface.")
    help_cmd.set_defaults(func=cmd_help)

    about = sub.add_parser("about", help="Show ANCHOR platform identity and role mapping.")
    about.set_defaults(func=cmd_about)

    trinity = sub.add_parser(
        "trinity",
        help="ANCHOR evidence-packet workflow and case history commands.",
    )
    trinity_sub = trinity.add_subparsers(dest="trinity_command")

    trinity.set_defaults(func=lambda _args, _parser=trinity: (_parser.print_help() or 2))

    trinity_analyze = trinity_sub.add_parser(
        "analyze",
        help="Run an ANCHOR council round from a scanner or test output file.",
    )
    trinity_analyze.add_argument("input", help="Scanner input file path.")
    trinity_analyze.add_argument(
        "--format-hint",
        default="auto",
        choices=["auto", "slither", "foundry", "generic"],
        help="Hint the parser toward a specific scanner format.",
    )
    trinity_analyze.add_argument(
        "--output",
        help="Optional output directory for the case bundle.",
    )
    trinity_analyze.add_argument(
        "--case-id",
        help="Optional case id to use instead of the scanner file stem.",
    )
    trinity_analyze.add_argument(
        "--subject",
        default="authorized_audit_target",
        help="Claim subject for the council round.",
    )
    trinity_analyze.add_argument(
        "--reproduction-command",
        help="Reproduction command to record in the packet.",
    )
    trinity_analyze.add_argument(
        "--ledger-path",
        help="Optional Trinity case ledger path.",
    )
    trinity_analyze.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse input and show the planned analysis without running council or writing files.",
    )
    trinity_analyze.add_argument(
        "--no-packet",
        action="store_true",
        help="Run the council round but skip writing the evidence packet bundle.",
    )
    trinity_analyze.add_argument(
        "--format",
        default="text",
        choices=["text", "json"],
        help="Output format for the command result.",
    )
    trinity_analyze.set_defaults(func=cmd_trinity_analyze)

    case = trinity_sub.add_parser(
        "case",
        help="Manage ANCHOR cases.",
    )
    case_sub = case.add_subparsers(dest="case_command")
    case.set_defaults(func=lambda _args, _parser=case: (_parser.print_help() or 2))

    case_list = case_sub.add_parser(
        "list",
        help="List recent ANCHOR cases from the ledger.",
    )
    case_list.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Number of recent cases to show.",
    )
    case_list.add_argument(
        "--ledger-path",
        help="Optional Trinity case ledger path.",
    )
    case_list.add_argument(
        "--format",
        default="text",
        choices=["text", "json"],
        help="Output format for the case listing.",
    )
    case_list.set_defaults(func=cmd_trinity_case_list)

    case_show = case_sub.add_parser(
        "show",
        help="Show a concise summary for a case bundle.",
    )
    case_show.add_argument("case_ref", help="Case id or bundle directory.")
    case_show.add_argument(
        "--ledger-path",
        help="Optional Trinity case ledger path.",
    )
    case_show.add_argument(
        "--format",
        default="text",
        choices=["text", "json"],
        help="Output format for the case summary.",
    )
    case_show.set_defaults(func=cmd_trinity_case_show)

    case_report = case_sub.add_parser(
        "report",
        help="Show the full ANCHOR evidence packet report.",
    )
    case_report.add_argument("case_ref", help="Case id or bundle directory.")
    case_report.add_argument(
        "--ledger-path",
        help="Optional Trinity case ledger path.",
    )
    case_report.add_argument(
        "--format",
        default="markdown",
        choices=["markdown", "json"],
        help="Output format for the report.",
    )
    case_report.set_defaults(func=cmd_trinity_case_report)

    case_export = case_sub.add_parser(
        "export",
        help="Export a case bundle to another directory.",
    )
    case_export.add_argument("case_ref", help="Case id or bundle directory.")
    case_export.add_argument("output", help="Directory to export the bundle to.")
    case_export.add_argument(
        "--ledger-path",
        help="Optional Trinity case ledger path.",
    )
    case_export.add_argument(
        "--format",
        default="text",
        choices=["text", "json"],
        help="Output format for the export summary.",
    )
    case_export.set_defaults(func=cmd_trinity_case_export)

    packet = trinity_sub.add_parser(
        "packet",
        help="Inspect or export ANCHOR evidence packets.",
    )
    packet_sub = packet.add_subparsers(dest="packet_command")
    packet.set_defaults(func=lambda _args, _parser=packet: (_parser.print_help() or 2))

    packet_show = packet_sub.add_parser(
        "show",
        help="Show the structured evidence packet for a case.",
    )
    packet_show.add_argument("case_ref", help="Case id or bundle directory.")
    packet_show.add_argument(
        "--ledger-path",
        help="Optional Trinity case ledger path.",
    )
    packet_show.add_argument(
        "--format",
        default="json",
        choices=["json", "markdown"],
        help="Output format for the packet view.",
    )
    packet_show.set_defaults(func=cmd_trinity_packet_show)

    packet_export = packet_sub.add_parser(
        "export",
        help="Export the packet bundle to another directory.",
    )
    packet_export.add_argument("case_ref", help="Case id or bundle directory.")
    packet_export.add_argument("output", help="Directory to export the bundle to.")
    packet_export.add_argument(
        "--ledger-path",
        help="Optional Trinity case ledger path.",
    )
    packet_export.add_argument(
        "--format",
        default="text",
        choices=["text", "json"],
        help="Output format for the export summary.",
    )
    packet_export.set_defaults(func=cmd_trinity_packet_export)

    ledger = trinity_sub.add_parser(
        "ledger",
        help="View ANCHOR run history.",
    )
    ledger_sub = ledger.add_subparsers(dest="ledger_command")
    ledger.set_defaults(func=lambda _args, _parser=ledger: (_parser.print_help() or 2))

    ledger_list = ledger_sub.add_parser(
        "list",
        help="List recent Trinity ledger entries.",
    )
    ledger_list.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Number of recent entries to show.",
    )
    ledger_list.add_argument(
        "--ledger-path",
        help="Optional Trinity case ledger path.",
    )
    ledger_list.add_argument(
        "--format",
        default="text",
        choices=["text", "json"],
        help="Output format for the ledger listing.",
    )
    ledger_list.set_defaults(func=cmd_trinity_ledger_list)

    ledger_show = ledger_sub.add_parser(
        "show",
        help="Show a single Trinity ledger entry.",
    )
    ledger_show.add_argument("case_ref", help="Case id to inspect.")
    ledger_show.add_argument(
        "--ledger-path",
        help="Optional Trinity case ledger path.",
    )
    ledger_show.add_argument(
        "--format",
        default="text",
        choices=["text", "json"],
        help="Output format for the ledger entry.",
    )
    ledger_show.set_defaults(func=cmd_trinity_ledger_show)

    trinity_report = trinity_sub.add_parser(
        "report",
        help="Legacy alias for trinity case report.",
    )
    trinity_report.add_argument("case_ref", help="Case id or bundle directory.")
    trinity_report.add_argument(
        "--ledger-path",
        help="Optional Trinity case ledger path.",
    )
    trinity_report.add_argument(
        "--format",
        default="markdown",
        choices=["markdown", "json"],
        help="Output format for the report.",
    )
    trinity_report.set_defaults(func=cmd_trinity_report)

    trinity_cases = trinity_sub.add_parser(
        "cases",
        help="Legacy alias for trinity case list.",
    )
    trinity_cases.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Number of recent cases to show.",
    )
    trinity_cases.add_argument(
        "--ledger-path",
        help="Optional Trinity case ledger path.",
    )
    trinity_cases.add_argument(
        "--format",
        default="text",
        choices=["text", "json"],
        help="Output format for the case listing.",
    )
    trinity_cases.set_defaults(func=cmd_trinity_cases)

    trinity_demo = trinity_sub.add_parser(
        "demo",
        help="Run a built-in ANCHOR sample case through the full evidence loop.",
    )
    trinity_demo.add_argument(
        "--case-id",
        default="demo_reentrancy",
        help="Case id to store in the demo bundle and ledger.",
    )
    trinity_demo.add_argument(
        "--output",
        help="Optional output directory for the demo bundle.",
    )
    trinity_demo.add_argument(
        "--subject",
        default="authorized_audit_target",
        help="Claim subject for the demo round.",
    )
    trinity_demo.add_argument(
        "--ledger-path",
        help="Optional Trinity case ledger path.",
    )
    trinity_demo.add_argument(
        "--format",
        default="text",
        choices=["text", "json"],
        help="Output format for the demo result.",
    )
    trinity_demo.set_defaults(func=cmd_trinity_demo)

    completion = sub.add_parser(
        "completion",
        help="Print shell completion for trin/drift.",
    )
    completion.add_argument(
        "shell",
        nargs="?",
        default="bash",
        choices=["bash", "zsh", "fish"],
        help="Shell type to generate completion for.",
    )
    completion.set_defaults(func=cmd_completion)

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
    if not hasattr(args, "func"):
        parser.print_help()
        return 2
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
