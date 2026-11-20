"""ANCHOR CLI smoke tests — parser, help, and release commands."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_build_parser_has_anchor_commands():
    from drift.interfaces import build_parser as compatibility_parser
    from interfaces.cli import build_parser

    assert compatibility_parser().parse_args(["version"]).command == "version"
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
        env={
            "PYTHONPATH": str(ROOT),
            "PYTHONNOUSERSITE": "1",
            **dict(__import__("os").environ),
        },
        check=False,
    )
    assert proc.returncode == 0
    assert (
        "ANCHOR" in proc.stdout or "Trinity" in proc.stdout or "doctor" in proc.stdout
    )


def test_module_cli_help_has_no_runpy_runtime_warning():
    proc = subprocess.run(
        [
            sys.executable,
            "-W",
            "error::RuntimeWarning",
            "-m",
            "drift.interfaces.cli",
            "--help",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr


def test_doctor_json_shape(capsys, monkeypatch):
    from interfaces import cli
    from interfaces.cli import build_parser

    real_which = cli.shutil.which
    monkeypatch.setattr(
        cli.shutil,
        "which",
        lambda name: (
            sys.executable if name in {"anchor", "drift", "trin"} else real_which(name)
        ),
    )
    parser = build_parser()
    args = parser.parse_args(["doctor", "--json"])
    code = args.func(args)
    captured = capsys.readouterr()
    assert code == 0
    assert captured.out.strip().startswith("{")


def test_doctor_accepts_repo_local_launchers(tmp_path, capsys, monkeypatch):
    from interfaces import cli

    venv_bin = tmp_path / ".venv" / "bin"
    venv_bin.mkdir(parents=True)
    (venv_bin / "python").symlink_to(sys.executable)
    for name in ("drift", "anchor"):
        (venv_bin / name).write_text("#!/bin/sh\n", encoding="utf-8")

    monkeypatch.setattr(cli, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(cli.shutil, "which", lambda _name: None)

    args = cli.build_parser().parse_args(["doctor", "--json"])
    exit_code = cli.cmd_doctor(args)
    payload = json.loads(capsys.readouterr().out)
    checks = {check["name"]: check for check in payload["checks"]}

    assert exit_code == (0 if payload["status"] == "ok" else 1)
    assert checks["Launcher"]["ok"] is True
    assert checks["Anchor"]["ok"] is True
    assert checks["Launcher"]["detail"] == str(venv_bin / "drift")
    assert checks["Anchor"]["detail"] == str(venv_bin / "anchor")
