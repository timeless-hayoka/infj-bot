# ruff: noqa: N999 - legacy public filename or repository compatibility shim
from importlib import import_module
from pathlib import Path
from typing import Any

# Match drift.core's source-checkout compatibility path, including the API.
__path__ = [str(Path(__file__).resolve().parents[2] / "interfaces")]


def __getattr__(name: str) -> Any:
    """Lazily preserve historical CLI exports without preloading ``.cli``."""
    cli = import_module(f"{__name__}.cli")
    try:
        return getattr(cli, name)
    except AttributeError as exc:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from exc
