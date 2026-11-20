from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_repository_metadata_consistently_declares_proprietary_license() -> None:
    python_metadata = tomllib.loads(
        (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    )["project"]
    npm_metadata = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
    npm_lock_metadata = json.loads(
        (ROOT / "package-lock.json").read_text(encoding="utf-8")
    )["packages"][""]
    license_notice = (ROOT / "LICENSE").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert python_metadata["license"] == "LicenseRef-Proprietary"
    assert npm_metadata["license"] == "UNLICENSED"
    assert npm_metadata["private"] is True
    assert npm_lock_metadata["license"] == "UNLICENSED"
    assert "PROPRIETARY LICENSE NOTICE" in license_notice
    assert "Proprietary / all rights reserved" in readme


def _normalized_requirement_name(requirement: str) -> str:
    return re.split(r"[<>=!~[]", requirement, maxsplit=1)[0].strip().lower()


def test_dev_extra_contains_local_quality_toolchain() -> None:
    config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    dev_requirements = config["project"]["optional-dependencies"]["dev"]
    names = {_normalized_requirement_name(item) for item in dev_requirements}

    assert {"ruff", "bandit", "detect-secrets", "mypy"} <= names


def test_shared_runtime_constraints_match_reproducible_requirements() -> None:
    config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    project_requirements = {
        _normalized_requirement_name(item): item
        for item in config["project"]["dependencies"]
    }
    dev_requirements = {
        _normalized_requirement_name(item): item
        for item in config["project"]["optional-dependencies"]["dev"]
    }
    locked_requirements = {
        _normalized_requirement_name(line): line.strip()
        for line in (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }

    for name in ("fastapi", "httpx"):
        assert project_requirements[name] == locked_requirements[name]
    assert dev_requirements["anyio"] == locked_requirements["anyio"]
