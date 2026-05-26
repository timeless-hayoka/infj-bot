"""
Developer Suite plugin for DRIFT.
Provides tools for workspace exploration, code analysis, and system interaction.
"""

import json
import logging
import os
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from infj_bot.core.config import PROJECT_ROOT

logger = logging.getLogger("drift")


@dataclass
class DeveloperSuiteState:
    active: bool = True
    last_run: Optional[str] = None
    working_dir: str = str(PROJECT_ROOT)


class DeveloperSuite:
    """
    Plugin allowing DRIFT to explore the workspace and use developer tools.
    """

    def __init__(self):
        self.state = DeveloperSuiteState()
        self.authorized_roots = [
            str(Path.home() / "drift"),
            str(Path.home() / "infj_bot"),
            str(Path.home() / "video_agent"),
            str(Path.home() / "hacker_hub"),
        ]

    def cycle(self, context) -> None:
        """Called by the consciousness loop."""
        self.state.last_run = datetime.now().isoformat()

    def format_prompt_snippet(self) -> str:
        """Return a string to inject into the chat prompt."""
        return (
            f"DEVELOPER SUITE: I have access to the workspace and coding tools.\n"
            f"I can read files, run linters (ruff), and use system utilities (uv, gh, duckdb).\n"
            f"I also have access to security tools (nuclei, amass) and Google CLIs (firebase, clasp).\n"
            f"Current working directory: {self.state.working_dir}"
        )

    # --- Tool Methods ---

    def list_files(self, path: str = ".") -> str:
        """List files in a directory."""
        target = (Path(self.state.working_dir) / path).resolve()
        if not self._is_authorized(target):
            return f"[error: unauthorized access to {target}]"

        try:
            items = os.listdir(target)
            return json.dumps(items, indent=2)
        except Exception as e:
            return f"[error: {e}]"

    def read_file(self, path: str) -> str:
        """Read content of a file."""
        target = (Path(self.state.working_dir) / path).resolve()
        if not self._is_authorized(target):
            return f"[error: unauthorized access to {target}]"

        try:
            with open(target, "r") as f:
                content = f.read()
            if len(content) > 10000:
                content = content[:10000] + "\n... [truncated]"
            return content
        except Exception as e:
            return f"[error: {e}]"

    def run_tool(self, command: List[str]) -> str:
        """Run a developer tool command."""
        allowed_tools = {
            "ruff",
            "pytest",
            "uv",
            "gh",
            "duckdb",
            "python3",
            "ls",
            "grep",
            "git",
            "nuclei",
            "sqlmap",
            "amass",
            "nmap",
            "ffuf",
            "httpx",
            "subfinder",
            "firebase",
            "clasp",
            "ng",
            "bazel",
            "kubectl",
            "skaffold",
            "minikube",
        }
        if not command or command[0] not in allowed_tools:
            return f"[error: command '{command[0]}' not in allowed toolset]"

        try:
            result = subprocess.run(
                command,
                cwd=self.state.working_dir,
                capture_output=True,
                text=True,
                timeout=30,
            )
            report = {
                "stdout": result.stdout,
                "stderr": result.stderr,
                "exit_code": result.returncode,
            }
            return json.dumps(report, indent=2)
        except Exception as e:
            return f"[error: {e}]"

    def _is_authorized(self, path: Path) -> bool:
        path_str = str(path)
        return any(path_str.startswith(root) for root in self.authorized_roots)


def _register():
    from infj_bot.core.cognitive_architecture import (
        CognitiveArchitecture,
        CognitivePlugin,
    )

    arch = CognitiveArchitecture()
    if "developer_suite" not in arch.list_plugins():
        arch.register(
            CognitivePlugin(
                name="developer_suite",
                description="Tools for workspace exploration, code analysis, and system interaction",
                module_path="plugins.developer_suite",
                instance_factory=DeveloperSuite,
                cycle_handler="cycle",
                cycle_frequency=2,
                cycle_priority=70,
                prompt_formatter="format_prompt_snippet",
                prompt_priority=70,
                prompt_section="context",
                commands={
                    "ls_workspace": "list_files",
                    "read_workspace_file": "read_file",
                    "run_dev_tool": "run_tool",
                },
            )
        )


if __name__ == "__main__":
    _register()
    print("Developer Suite plugin registered.")
