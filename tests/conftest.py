import sys
import os
from pathlib import Path

# Add the parent of infj_bot (which is /home/crexs) to sys.path
# so that `import infj_bot.core...` works.
parent_dir = str(Path(__file__).resolve().parent.parent.parent)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

# Several core modules use legacy absolute imports relative to core/
# (e.g. ``from config import ...``, ``from cognition import ...``).
# Adding core/ to sys.path lets those imports resolve without rewriting
# the entire codebase.
core_dir = str(Path(__file__).resolve().parent.parent / "core")
if core_dir not in sys.path:
    sys.path.insert(0, core_dir)
