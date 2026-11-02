# ruff: noqa: N999 - legacy public filename or repository compatibility shim
"""Allow running as `python -m drift`."""

from drift.interfaces.cli import main

if __name__ == "__main__":
    main()
