"""Isolated checks for MCP SDK selection and the stdio launcher."""

import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import sys
from types import ModuleType

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[1]


class RecordingServer:
    def __init__(self, name, instructions):
        self.name = name
        self.instructions = instructions
        self.tools = []

    def tool(self):
        def register(function):
            self.tools.append(function.__name__)
            return function
        return register


def stub_module(monkeypatch, name, **attributes):
    module = ModuleType(name)
    module.__dict__.update(attributes)
    monkeypatch.setitem(sys.modules, name, module)
    return module


@pytest.mark.parametrize("new_sdk", [True, False])
def test_server_selects_available_sdk_and_registers_manifest_tools(monkeypatch, new_sdk):
    class NewServer(RecordingServer):
        pass

    class OldServer(RecordingServer):
        pass

    stub_module(monkeypatch, "mcp", __path__=[])
    stub_module(monkeypatch, "mcp.server", __path__=[])
    if new_sdk:
        stub_module(monkeypatch, "mcp.server.mcpserver", MCPServer=NewServer)
    else:
        monkeypatch.setitem(sys.modules, "mcp.server.mcpserver", None)
    stub_module(monkeypatch, "mcp.server.fastmcp", FastMCP=OldServer)

    # Isolate the SDK selection from server dependencies and their startup side effects.
    stub_module(monkeypatch, "fastapi", FastAPI=object, HTTPException=Exception,
                Request=object, WebSocket=object, WebSocketDisconnect=Exception)
    stub_module(monkeypatch, "fastapi.responses", HTMLResponse=object)
    stub_module(monkeypatch, "fastapi.staticfiles", StaticFiles=object)
    stub_module(monkeypatch, "prometheus_client", Gauge=lambda *a: object(),
                Counter=lambda *a: object(), generate_latest=lambda: b"",
                CONTENT_TYPE_LATEST="text/plain")
    stub_module(monkeypatch, "uvicorn")
    for name, attributes in {
        "brain": {"DriftBrain": object},
        "being": {"get_being": lambda: None},
        "websocket_manager": {"manager": object()},
        "config": {"PROJECT_ROOT": ROOT},
        "cognition": {"map_dissonance": lambda *a: None},
        "plugins.documents": {"DocumentStore": object, "format_doc_results": lambda *a: None},
        "plugins.emotion": {"detect_emotion": lambda *a: None},
        "plugins.goals": {"GoalsDB": object},
        "memory": {"DriftMemory": object},
        "global_workspace": {"GlobalWorkspace": object},
    }.items():
        stub_module(monkeypatch, "drift.core." + name, **attributes)
    monkeypatch.setitem(sys.modules, "hive_mind.orchestrator", None)

    spec = importlib.util.spec_from_file_location("isolated_mcp_server", ROOT / "core/mcp_server.py")
    server_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(server_module)

    assert isinstance(server_module.mcp, NewServer if new_sdk else OldServer)
    assert server_module.mcp.name == "infj_companion"
    manifest = yaml.safe_load((ROOT / "mcp/infj_mcp_agent.yaml").read_text())
    assert {"hive_status", "workspace_snapshot"} <= set(server_module.mcp.tools)
    assert set(manifest["tools"]) == set(server_module.mcp.tools)
    assert len(manifest["tools"]) == len(server_module.mcp.tools)
    assert manifest["entrypoint"] == "scripts/run_mcp.sh"
    assert (ROOT / manifest["entrypoint"]).is_file()


@pytest.mark.parametrize(
    ("args", "mode", "transport", "expected_mode", "expected_transport"),
    [([], None, None, "local", ""), (["http"], "semantic", None, "semantic", "http"),
     ([], "local", "http", "local", "http")],
)
def test_launcher_uses_package_entrypoint_from_project_root(
    tmp_path, args, mode, transport, expected_mode, expected_transport
):
    scripts = tmp_path / "project" / "scripts"
    scripts.mkdir(parents=True)
    launcher = scripts / "run_mcp.sh"
    shutil.copy(ROOT / "scripts/run_mcp.sh", launcher)
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    python = fake_bin / "python"
    python.write_text('#!/bin/sh\nprintf "%s\\n" "$PWD" "$INFJ_EMBEDDING_MODE" "${MCP_TRANSPORT:-}" "$@"\n')
    python.chmod(0o755)
    env = os.environ.copy()
    env["PATH"] = str(fake_bin) + os.pathsep + env["PATH"]
    env.pop("INFJ_EMBEDDING_MODE", None)
    env.pop("MCP_TRANSPORT", None)
    if mode is not None:
        env["INFJ_EMBEDDING_MODE"] = mode
    if transport is not None:
        env["MCP_TRANSPORT"] = transport

    result = subprocess.run(["bash", str(launcher), *args], cwd=tmp_path, env=env,
                            capture_output=True, text=True, check=True, timeout=5)
    assert result.stdout.splitlines() == [str(scripts.parent), expected_mode, expected_transport,
                                         "-u", "-m", "drift.core.mcp_server"]
