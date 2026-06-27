from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Prefer project venv site-packages over system dist-packages (avoids attrs/jsonschema conflicts).
_venv_site = ROOT / ".venv" / "lib" / f"python{sys.version_info.major}.{sys.version_info.minor}" / "site-packages"
if _venv_site.is_dir():
    site_str = str(_venv_site)
    if site_str not in sys.path:
        sys.path.insert(0, site_str)
