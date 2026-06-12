import os
import glob
from pathlib import Path

repo_dir = Path("/home/crexs/drift")

for p in repo_dir.rglob("*"):
    if p.is_file() and not ".git" in p.parts and not ".venv" in p.parts and not "node_modules" in p.parts:
        try:
            content = p.read_text("utf-8")
            if "drift" in content or "drift" in content:
                content = content.replace("drift", "drift").replace("drift", "drift")
                p.write_text(content, "utf-8")
        except Exception:
            pass

package_dir = repo_dir / "drift"
if package_dir.exists():
    package_dir.rename(repo_dir / "drift")

print("Renamed to drift successfully")
