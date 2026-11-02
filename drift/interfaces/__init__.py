# ruff: noqa: N999 - legacy public filename or repository compatibility shim
from pathlib import Path

# Match drift.core's source-checkout compatibility path, including the API.
__path__ = [str(Path(__file__).resolve().parents[2] / "interfaces")]

# Preserve historical package exports in source and installed environments.
from .cli import *
