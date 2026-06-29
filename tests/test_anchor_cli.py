"""ANCHOR CLI smoke tests — parser, help, and release commands."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_build_parser_has_anchor_commands():
    from interfaces.cli import build_parser

    parser = build_parser()
    commands = {action.dest for action in parser._actions if action.dest == "command"}
    assert "command" in commands or parser._subparsers is not None
    subs = parser._subparsers._group_actions[0].choices
    for name in ("doctor", "status", "trinity", "memory", "version"):
        assert name in subs, f"missing subcommand: {name}"


def test_cli_help_exits_zero():
    proc = subprocess.run(
        [sys.executable, "-m", "drift.interfaces.cli", "--help"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        env={**dict(**{"PYTHONPATH": str(ROOT), "PYTHONNOUSERSITE": "1"}), **dict(__import__("os").environ)},
    )
    assert proc.returncode == 0
    assert "ANCHOR" in proc.stdout or "Trinity" in proc.stdout or "doctor" in proc.stdout


def test_doctor_json_shape(capsys):
    from interfaces.cli import build_parser

    parser = build_parser()
    args = parser.parse_args(["doctor", "--json"])
    code = args.func(args)
    captured = capsys.readouterr()
    assert code == 0
    assert captured.out.strip().startswith("{")
