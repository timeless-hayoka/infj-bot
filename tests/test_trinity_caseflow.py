"""Tests for Trinity caseflow and CLI commands."""

from __future__ import annotations

import json
import asyncio
import subprocess
import sys

import pytest
from pathlib import Path
from types import SimpleNamespace

from drift.interfaces.cli import build_parser, cmd_archive_create, cmd_archive_list, cmd_archive_show, cmd_doctor, cmd_export_report, cmd_history, cmd_trinity_analyze, cmd_trinity_cases, cmd_trinity_demo, cmd_trinity_packet, cmd_trinity_report, cmd_upgrade, cmd_version
from httpx import ASGITransport, AsyncClient
from drift.trinity.caseflow import TrinityCaseLedger, load_case_bundle, parse_scanner_input, run_case_from_scan


def _write_slither_payload(path: Path) -> None:
    payload = {
        'results': {
            'detectors': [
                {
                    'check': 'reentrancy',
                    'impact': 'High',
                    'confidence': 'High',
                    'description': 'possible reentrancy path',
                    'elements': [
                        {
                            'source_mapping': {
                                'filename_relative': 'contracts/Vulnerable.sol',
                                'lines': [42],
                            }
                        }
                    ],
                    'reproduction_command': 'forge test --match-test test_reentrancy',
                }
            ]
        }
    }
    path.write_text(json.dumps(payload), encoding='utf-8')


def _write_foundry_payload(path: Path) -> None:
    payload = {
        'failures': [
            {
                'test': 'testUnauthorizedWithdraw',
                'reason': 'expected revert did not occur',
                'severity': 'high',
                'reproduction_command': 'forge test --match-test testUnauthorizedWithdraw',
            }
        ]
    }
    path.write_text(json.dumps(payload), encoding='utf-8')


def test_parse_scanner_input_and_run_case_writes_bundle(tmp_path):
    scan_path = tmp_path / 'sample_slither.json'
    case_dir = tmp_path / 'case_out'
    ledger_path = tmp_path / 'ledger.jsonl'
    _write_slither_payload(scan_path)

    scan = parse_scanner_input(scan_path)
    assert scan['format'] == 'slither'
    assert scan['finding_count'] == 1

    ledger = TrinityCaseLedger(ledger_path)
    result = run_case_from_scan(
        scan_path,
        output_dir=case_dir,
        ledger=ledger,
        reproduction_command='forge test --match-test test_reentrancy',
    )

    assert result['case_id'] == 'sample_slither'
    assert result['packet']['status'] in {
        'REPRODUCED_REAL',
        'NEEDS_HUMAN_REVIEW',
        'INSUFFICIENT_EVIDENCE',
        'REJECTED',
    }
    assert (case_dir / 'claim.json').exists()
    assert (case_dir / 'packet.json').exists()
    assert (case_dir / 'manifest.json').exists()
    assert (case_dir / 'export_report.md').exists()
    assert (case_dir / 'reasoning_summary.md').exists()
    assert (case_dir / 'rejected_hypotheses.json').exists()
    assert (case_dir / 'evidence' / 'tool_outputs').is_dir()
    assert ledger.recent(1)[0]['case_id'] == 'sample_slither'


def test_trinity_cli_analyze_and_case_listing(tmp_path, capsys):
    scan_path = tmp_path / 'sample_foundry.json'
    case_dir = tmp_path / 'bundle'
    ledger_path = tmp_path / 'ledger.jsonl'
    _write_foundry_payload(scan_path)

    analyze_args = SimpleNamespace(
        input=str(scan_path),
        format_hint='auto',
        output=str(case_dir),
        case_id=None,
        subject='authorized_audit_target',
        reproduction_command=None,
        ledger_path=str(ledger_path),
        format='text',
    )
    exit_code = cmd_trinity_analyze(analyze_args)
    assert exit_code == 0
    stdout = capsys.readouterr().out
    assert 'Case: sample_foundry' in stdout
    assert (case_dir / 'packet.json').exists()

    cases_args = SimpleNamespace(limit=5, ledger_path=str(ledger_path), format='json')
    exit_code = cmd_trinity_cases(cases_args)
    assert exit_code == 0
    cases = json.loads(capsys.readouterr().out)
    assert cases and cases[-1]['case_id'] == 'sample_foundry'


def test_trinity_demo_runs_full_loop(tmp_path, capsys):
    ledger_path = tmp_path / 'ledger.jsonl'
    output_dir = tmp_path / 'demo_bundle'
    args = SimpleNamespace(
        case_id='demo_reentrancy',
        output=str(output_dir),
        subject='authorized_audit_target',
        ledger_path=str(ledger_path),
        format='text',
    )

    exit_code = cmd_trinity_demo(args)
    assert exit_code == 0
    stdout = capsys.readouterr().out
    assert 'Trinity demo complete.' in stdout
    assert 'Bundle written to:' in stdout
    assert (output_dir / 'packet.json').exists()
    assert (output_dir / 'export_report.md').exists()


def test_trinity_report_and_packet_round_trip(tmp_path, capsys):
    scan_path = tmp_path / 'report_case.json'
    case_dir = tmp_path / 'report_bundle'
    ledger_path = tmp_path / 'ledger.jsonl'
    _write_slither_payload(scan_path)
    run_case_from_scan(scan_path, output_dir=case_dir, ledger=TrinityCaseLedger(ledger_path))

    report_args = SimpleNamespace(case_ref='report_case', ledger_path=str(ledger_path), format='markdown')
    assert cmd_trinity_report(report_args) == 0
    report_text = capsys.readouterr().out
    assert '# Trinity Evidence Packet' in report_text

    packet_args = SimpleNamespace(case_ref=str(case_dir), ledger_path=str(ledger_path), format='json')
    assert cmd_trinity_packet(packet_args) == 0
    packet = json.loads(capsys.readouterr().out)
    assert packet['claim']['id'] == 'report_case'
    assert packet['status']
    loaded = load_case_bundle(case_dir)
    assert loaded['claim']['id'] == 'report_case'


def test_trinity_grouped_cli_surface(tmp_path, capsys):
    scan_path = tmp_path / 'grouped_case.json'
    case_dir = tmp_path / 'grouped_bundle'
    ledger_path = tmp_path / 'ledger.jsonl'
    _write_slither_payload(scan_path)
    run_case_from_scan(scan_path, output_dir=case_dir, ledger=TrinityCaseLedger(ledger_path))

    parser = build_parser()

    case_show_args = parser.parse_args([
        'trinity',
        'case',
        'show',
        str(case_dir),
        '--ledger-path',
        str(ledger_path),
    ])
    assert case_show_args.func(case_show_args) == 0
    case_show_text = capsys.readouterr().out
    assert 'Case: grouped_case' in case_show_text
    assert 'Status:' in case_show_text

    packet_show_args = parser.parse_args([
        'trinity',
        'packet',
        'show',
        str(case_dir),
        '--ledger-path',
        str(ledger_path),
        '--format',
        'markdown',
    ])
    assert packet_show_args.func(packet_show_args) == 0
    packet_text = capsys.readouterr().out
    assert '# Trinity Evidence Packet' in packet_text

    case_list_args = parser.parse_args([
        'trinity',
        'case',
        'list',
        '--ledger-path',
        str(ledger_path),
        '--format',
        'json',
    ])
    assert case_list_args.func(case_list_args) == 0
    case_list = json.loads(capsys.readouterr().out)
    assert any(entry['case_id'] == 'grouped_case' for entry in case_list)


def test_trinity_release_and_archive_commands(tmp_path, capsys):
    scan_path = tmp_path / 'release_case.json'
    case_dir = tmp_path / 'release_bundle'
    ledger_path = tmp_path / 'ledger.jsonl'
    archive_dir = tmp_path / 'archive_out'
    archive_ledger_path = tmp_path / 'archive_ledger.jsonl'
    report_path = tmp_path / 'case_report.md'
    _write_slither_payload(scan_path)
    run_case_from_scan(scan_path, output_dir=case_dir, ledger=TrinityCaseLedger(ledger_path))

    parser = build_parser()

    version_args = parser.parse_args(['version', '--json'])
    assert version_args.func(version_args) == 0
    version_payload = json.loads(capsys.readouterr().out)
    assert version_payload['name'] == 'ANCHOR'
    assert version_payload['product'] == 'ANCHOR'
    assert 'version' in version_payload

    release_args = parser.parse_args(['release', '--json'])
    assert release_args.func(release_args) == 0
    release_payload = json.loads(capsys.readouterr().out)
    assert release_payload['manifest']['product'] == 'ANCHOR'
    assert release_payload['manifest']['status'] == 'release_candidate'
    assert release_payload['release']['build_id'].startswith('anchor-0.10.0-')

    history_args = parser.parse_args(['history', '--ledger-path', str(ledger_path), '--json'])
    assert history_args.func(history_args) == 0
    history_payload = json.loads(capsys.readouterr().out)
    assert history_payload['entries']
    assert history_payload['entries'][-1]['case_id'] == 'release_case'

    archive_create_args = parser.parse_args([
        'archive', 'create', str(case_dir),
        '--output', str(archive_dir),
        '--ledger-path', str(ledger_path),
        '--archive-ledger-path', str(archive_ledger_path),
        '--json',
    ])
    assert archive_create_args.func(archive_create_args) == 0
    archive_create_payload = json.loads(capsys.readouterr().out)
    assert archive_create_payload['case_id'] == 'release_case'
    assert Path(archive_create_payload['archive_dir']).exists()

    archive_list_args = parser.parse_args(['archive', 'list', '--archive-ledger-path', str(archive_ledger_path), '--json'])
    assert archive_list_args.func(archive_list_args) == 0
    archive_list_payload = json.loads(capsys.readouterr().out)
    assert archive_list_payload[-1]['case_id'] == 'release_case'

    archive_show_args = parser.parse_args(['archive', 'show', archive_create_payload['archive_dir'], '--json'])
    assert archive_show_args.func(archive_show_args) == 0
    archive_show_payload = json.loads(capsys.readouterr().out)
    assert archive_show_payload['case_id'] == 'release_case'

    report_args = parser.parse_args([
        'export-report',
        'release_case',
        '--output',
        str(report_path),
        '--ledger-path',
        str(ledger_path),
        '--json',
    ])
    assert report_args.func(report_args) == 0
    report_payload = json.loads(capsys.readouterr().out)
    assert report_payload['case_id'] == 'release_case'
    assert report_path.exists()
    report_text = report_path.read_text(encoding='utf-8')
    assert '# ANCHOR Investigation Report' in report_text
    assert 'Powered by Trinity' in report_text

    release_text_args = parser.parse_args(['release'])
    assert release_text_args.func(release_text_args) == 0
    release_text = capsys.readouterr().out
    assert 'ANCHOR 0.10.0' in release_text
    assert 'Release Health: PASS' in release_text

    upgrade_args = parser.parse_args(['upgrade'])
    assert upgrade_args.func(upgrade_args) == 0
    upgrade_text = capsys.readouterr().out
    assert 'TRINITY UPGRADE PLAN' in upgrade_text


def test_trinity_analyze_dry_run_skips_council_and_writes(tmp_path, capsys):
    scan_path = tmp_path / 'dry_run_slither.json'
    output_dir = tmp_path / 'dry_run_bundle'
    ledger_path = tmp_path / 'ledger.jsonl'
    _write_slither_payload(scan_path)

    args = SimpleNamespace(
        input=str(scan_path),
        format_hint='auto',
        output=str(output_dir),
        case_id=None,
        subject='authorized_audit_target',
        reproduction_command=None,
        ledger_path=str(ledger_path),
        format='text',
        dry_run=True,
        no_packet=False,
    )

    assert cmd_trinity_analyze(args) == 0
    stdout = capsys.readouterr().out
    assert 'Trinity dry run.' in stdout
    assert 'Would write packet: yes' in stdout
    assert not output_dir.exists()
    assert not ledger_path.exists()


def test_trinity_analyze_no_packet_skips_bundle_writing(tmp_path, capsys):
    scan_path = tmp_path / 'no_packet_slither.json'
    output_dir = tmp_path / 'no_packet_bundle'
    ledger_path = tmp_path / 'ledger.jsonl'
    _write_slither_payload(scan_path)

    args = SimpleNamespace(
        input=str(scan_path),
        format_hint='auto',
        output=str(output_dir),
        case_id=None,
        subject='authorized_audit_target',
        reproduction_command=None,
        ledger_path=str(ledger_path),
        format='text',
        dry_run=False,
        no_packet=True,
    )

    assert cmd_trinity_analyze(args) == 0
    stdout = capsys.readouterr().out
    assert 'Packet bundle writing skipped by --no-packet.' in stdout
    assert not (output_dir / 'claim.json').exists()
    assert ledger_path.exists()




def test_trinity_fastapi_router_round_trip(tmp_path, monkeypatch):
    caseflow_mod = __import__('drift.trinity.caseflow', fromlist=['TRINITY_CASES_DIR'])
    http_api = __import__('drift.trinity.http_api', fromlist=['build_trinity_app'])

    cases_dir = tmp_path / 'trinity_cases'
    ledger_path = tmp_path / 'trinity_ledger.jsonl'
    db_path = tmp_path / 'trinity.db'
    monkeypatch.setattr(caseflow_mod, 'TRINITY_CASES_DIR', cases_dir)
    monkeypatch.setattr(caseflow_mod, 'TRINITY_LEDGER_PATH', ledger_path)
    monkeypatch.setattr(http_api, 'TRINITY_CASES_DIR', cases_dir)
    monkeypatch.setattr(http_api, 'TRINITY_LEDGER_PATH', ledger_path)
    http_api.trinity_db.db_path = db_path
    http_api.trinity_db._init_db()

    async def _run():
        transport = ASGITransport(app=http_api.build_trinity_app())
        async with AsyncClient(transport=transport, base_url='http://test') as client:
            payload_path = tmp_path / 'sample_slither.json'
            _write_slither_payload(payload_path)

            health = await client.get('/api/trinity/health')
            assert health.status_code == 200
            assert health.json()['status'] == 'ok'

            analyze = await client.post(
                '/api/trinity/analyze',
                json={
                    'input_path': str(payload_path),
                    'format_hint': 'slither',
                    'output_dir': str(tmp_path / 'bundle'),
                    'write_bundle': True,
                },
            )
            assert analyze.status_code == 200
            body = analyze.json()
            assert body['case_id'] == 'sample_slither'
            assert Path(body['output_dir']).exists()

            cases = await client.get('/api/trinity/cases')
            assert cases.status_code == 200
            assert any(item['case_id'] == 'sample_slither' for item in cases.json()['cases'])

            history = await client.get('/api/trinity/history?limit=5')
            assert history.status_code == 200
            history_body = history.json()
            assert history_body['count'] >= 1
            assert history_body['runs']
            assert history_body['runs'][0]['case_id'] == 'sample_slither'
            assert 'accepted_count' in history_body['runs'][0]
            assert 'rejected_count' in history_body['runs'][0]

            metrics = await client.get('/api/trinity/metrics')
            assert metrics.status_code == 200
            metrics_body = metrics.json()
            assert metrics_body['claims_generated'] >= 1
            assert metrics_body['claims_accepted'] >= 0
            assert metrics_body['claims_rejected'] >= 0
            assert 'reproduction_rate' in metrics_body

            vault = await client.get('/api/trinity/vault')
            assert vault.status_code == 200
            vault_body = vault.json()
            assert vault_body['vault_root'].endswith('AnchorVault')
            assert vault_body['status'] in {'ready', 'missing'}
            assert 'news_briefs' in vault_body
            assert 'news_snapshots' in vault_body
            assert 'history_records' in vault_body
            assert 'bug_classes' in vault_body
            assert 'triage_templates' in vault_body
            assert 'decision_trees' in vault_body

            contributions = await client.get('/api/trinity/contributions')
            assert contributions.status_code == 200
            contrib_body = contributions.json()
            assert 'open_prs' in contrib_body
            assert 'merged_prs' in contrib_body
            assert 'issues_filed' in contrib_body
            assert 'source' in contrib_body

            report = await client.get('/api/trinity/cases/sample_slither/report')
            assert report.status_code == 200
            assert '# Trinity Evidence Packet' in report.text

            summary = await client.get('/api/trinity/cases/sample_slither/summary')
            assert summary.status_code == 200
            assert summary.json()['case_id'] == 'sample_slither'

            findings = await client.get('/api/trinity/findings')
            assert findings.status_code == 200
            assert 'findings' in findings.json()

            latest = await client.get('/api/trinity/benchmarks/latest')
            assert latest.status_code in {200, 404}

    asyncio.run(_run())


def test_trinity_doctor_reports_health(capsys):
    args = SimpleNamespace(format='text', json=False)

    exit_code = cmd_doctor(args)
    assert exit_code == 0
    output = capsys.readouterr().out
    assert 'ANCHOR doctor' in output
    assert 'Launcher:' in output
    assert 'Python:' in output


def test_trinity_doctor_json_reports_health(capsys):
    args = SimpleNamespace(format='text', json=True, fix=False)

    exit_code = cmd_doctor(args)
    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload['status'] == 'ok'
    assert any(check['name'] == 'Launcher' for check in payload['checks'])
    assert any(check['name'] == 'Database' for check in payload['checks'])


def test_trinity_doctor_fix_mode_reports_actions(monkeypatch, capsys):
    monkeypatch.setattr('interfaces.cli.shutil.which', lambda _name: None)

    def fake_find_spec(name):
        return None if name == 'prometheus_client' else True

    monkeypatch.setattr('interfaces.cli.importlib.util.find_spec', fake_find_spec)

    args = SimpleNamespace(format='text', json=False, fix=True)

    exit_code = cmd_doctor(args)
    assert exit_code == 1
    output = capsys.readouterr().out
    assert 'Suggested fixes:' in output
    assert 'Run these in order:' in output
    assert '1. Reinstall or relink the `trin` launcher' in output
    assert '$ ln -sf /home/crexs/.local/bin/drift /home/crexs/.local/bin/trin' in output
    assert '$ cd /home/crexs/infj_bot && .venv/bin/python -m pip install prometheus-client' in output


def test_trinity_doctor_reports_zsh_completion_fix(monkeypatch, tmp_path, capsys):
    home = tmp_path
    monkeypatch.setattr('interfaces.cli.Path.home', lambda: home)

    bash_completion_dir = home / '.local/share/bash-completion/completions'
    bash_completion_dir.mkdir(parents=True, exist_ok=True)
    (bash_completion_dir / 'trin').write_text('# bash completion placeholder\n', encoding='utf-8')
    (home / '.bashrc').write_text(
        '[ -f "$HOME/.local/share/bash-completion/completions/trin" ] && source "$HOME/.local/share/bash-completion/completions/trin"\n',
        encoding='utf-8',
    )

    args = SimpleNamespace(format='text', json=False, fix=True)

    exit_code = cmd_doctor(args)
    assert exit_code == 0
    output = capsys.readouterr().out
    assert 'Zsh completion' in output
    assert 'Install zsh completion and add the Trinity completions directory to ~/.zshrc.' in output
    assert 'trin completion zsh > ~/.local/share/zsh/site-functions/_trin' in output
    assert 'fpath+=("$HOME/.local/share/zsh/site-functions")' in output


def test_trinity_status_command_reports_summary(monkeypatch, capsys):
    monkeypatch.setattr(
        'interfaces.cli._trinity_status_summary',
        lambda: {
            'healthy': True,
            'doctor': {
                'status': 'ok',
                'checks': [
                    {'name': 'Launcher', 'ok': True},
                    {'name': 'Python', 'ok': True},
                    {'name': 'Virtualenv', 'ok': True},
                    {'name': 'Database', 'ok': True},
                    {'name': 'Zsh completion', 'ok': True},
                    {'name': 'Bash completion', 'ok': True},
                ],
            },
            'fixes': [],
        },
    )

    exit_code = __import__('interfaces.cli', fromlist=['cmd_status']).cmd_status(SimpleNamespace(json=False))
    assert exit_code == 0
    output = capsys.readouterr().out
    assert 'ANCHOR STATUS' in output
    assert 'Health: PASS' in output
    assert 'Zsh completion: OK' in output


def test_trinity_setup_bootstraps_completions(monkeypatch, tmp_path, capsys):
    home = tmp_path
    monkeypatch.setattr('interfaces.cli.Path.home', lambda: home)

    exit_code = __import__('interfaces.cli', fromlist=['cmd_setup']).cmd_setup(SimpleNamespace(json=False))
    assert exit_code == 0
    output = capsys.readouterr().out
    assert 'ANCHOR setup complete.' in output

    bash_completion = home / '.local/share/bash-completion/completions/trin'
    zsh_completion = home / '.local/share/zsh/site-functions/_trin'
    assert bash_completion.exists()
    assert zsh_completion.exists()
    assert 'status' in bash_completion.read_text(encoding='utf-8')
    assert 'dashboard' in zsh_completion.read_text(encoding='utf-8')
    assert (home / '.bashrc').exists()
    assert (home / '.zshrc').exists()


def test_trinity_dashboard_launches_browser_and_server(monkeypatch, capsys):
    started = {}

    class FakeProc:
        pid = 4321

    def fake_popen(command, cwd=None, stdout=None, stderr=None):
        started['command'] = command
        started['cwd'] = cwd
        started['stdout'] = stdout
        started['stderr'] = stderr
        return FakeProc()

    opened = []
    cli = __import__('interfaces.cli', fromlist=['cmd_dashboard'])
    monkeypatch.setattr(cli.subprocess, 'Popen', fake_popen)
    monkeypatch.setattr(cli, '_dashboard_is_live', lambda url: False)
    monkeypatch.delenv('DISPLAY', raising=False)
    monkeypatch.delenv('WAYLAND_DISPLAY', raising=False)
    monkeypatch.setattr(cli.webbrowser, 'open', lambda url: opened.append(url) or True)

    exit_code = cli.cmd_dashboard(SimpleNamespace(url='http://127.0.0.1:8765', no_open=False))
    assert exit_code == 0
    output = capsys.readouterr().out
    assert 'ANCHOR dashboard starting at http://127.0.0.1:8765' in output
    assert opened == ['http://127.0.0.1:8765']
    assert started['cwd'] == str(Path(__file__).resolve().parents[1])


def test_trinity_dashboard_reuses_live_server(monkeypatch, capsys):
    started = []

    class FakeProc:
        pid = 4321

    def fake_popen(command, cwd=None, stdout=None, stderr=None):
        started.append((command, cwd, stdout, stderr))
        return FakeProc()

    opened = []
    cli = __import__('interfaces.cli', fromlist=['cmd_dashboard'])
    monkeypatch.setattr(cli.subprocess, 'Popen', fake_popen)
    monkeypatch.setattr(cli, '_dashboard_is_live', lambda url: True)
    monkeypatch.delenv('DISPLAY', raising=False)
    monkeypatch.delenv('WAYLAND_DISPLAY', raising=False)
    monkeypatch.setattr(cli.webbrowser, 'open', lambda url: opened.append(url) or True)

    exit_code = cli.cmd_dashboard(SimpleNamespace(url='http://127.0.0.1:8765', no_open=True))
    assert exit_code == 0
    output = capsys.readouterr().out
    assert 'ANCHOR dashboard already running at http://127.0.0.1:8765' in output
    assert not started
    assert not opened


def test_trinity_status_helper_wraps_doctor_json(tmp_path):
    script = Path(__file__).resolve().parents[1] / 'scripts' / 'trin_status.py'
    proc = subprocess.run(
        [sys.executable, str(script), '--json'],
        cwd=str(Path(__file__).resolve().parents[1]),
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0
    payload = json.loads(proc.stdout)
    assert payload['healthy'] is True
    assert payload['doctor']['status'] == 'ok'
    assert 'fixes' in payload
    assert 'command' in payload


def test_main_fastapi_app_exposes_trinity_routes():
    import interfaces.api as main_api

    async def _run():
        transport = ASGITransport(app=main_api.app)
        async with AsyncClient(transport=transport, base_url='http://test') as client:
            root = await client.get('/')
            assert root.status_code == 200
            assert 'Command Drift...' in root.text
            assert 'ANCHOR' in root.text

            anchor = await client.get('/anchor')
            assert anchor.status_code == 200
            assert 'Evidence Before Belief' in anchor.text
            assert 'Workbench' in anchor.text
            assert 'Release' in anchor.text
            assert 'History' in anchor.text
            assert 'Archive' in anchor.text
            assert any(route.path == '/api/trinity/health' for route in main_api.app.routes)

    asyncio.run(_run())
