"""CLI entry — re-exports canonical interfaces.cli for drift.interfaces.cli imports."""

from interfaces.cli import *  # noqa: F403
from interfaces.cli import main

if __name__ == "__main__":
    import sys

    sys.exit(main())
