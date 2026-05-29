#!/usr/bin/env python3
"""Incremental HF Space sync — upload only changed files.

Avoids the 50k+ file scan that breaks `hf upload . .` on large repos.
"""

import argparse
import subprocess
import sys
from pathlib import Path

REPO_ID = "crexs/phi-drift"
REPO_TYPE = "space"

# Paths that should never be uploaded to HF
SKIP_PATHS = {
    "venv",
    ".venv",
    "__pycache__",
    ".git",
    ".pytest_cache",
    ".idea",
    ".obsidian",
    "ABLATION_RESULTS",
    "BLKKNIGHT_RECOVERY",
    "LIVE_ABLATION_RESULTS",
    ".mouse_vanguard",
    ".agents",
    "outreach",
    "chroma_db",
    "voices",
    "data",
    "logs",
    ".cache",
    "scratch",
}

# Exact filenames or suffixes to block
SKIP_FILES = {
    "being.db",
    "svalbard_ledger.jsonl",
}
SKIP_SUFFIXES = {
    ".pyc",
}
SKIP_PREFIXES = {
    ".env",
}


def _should_skip(path: str) -> bool:
    parts = Path(path).parts
    if any(p in SKIP_PATHS for p in parts):
        return True
    name = Path(path).name
    if name in SKIP_FILES:
        return True
    if any(name.endswith(suffix) for suffix in SKIP_SUFFIXES):
        return True
    if any(name.startswith(prefix) for prefix in SKIP_PREFIXES):
        return True
    return False


def _run(cmd: list[str], check: bool = True) -> str:
    result = subprocess.run(cmd, capture_output=True, text=True, check=check)
    return result.stdout.strip()


def get_changed_files(base: str = "origin/master") -> tuple[list[str], list[str]]:
    """Return (upload_files, delete_files) relative to base."""
    status = _run(["git", "diff", "--name-status", base])
    upload_files: list[str] = []
    delete_files: list[str] = []
    for line in status.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        code = parts[0]
        if code.startswith("R"):  # Renamed
            upload_files.append(parts[2])
            delete_files.append(parts[1])
        elif code == "D":
            delete_files.append(parts[1])
        elif code in ("M", "A"):
            upload_files.append(parts[1])
        else:
            # Unknown status — treat as upload to be safe
            upload_files.append(parts[1])
    return upload_files, delete_files


def upload_file(path: str, dry_run: bool) -> None:
    if _should_skip(path):
        print(f"  SKIP (blocklist): {path}")
        return
    local = Path(path)
    if not local.exists():
        print(f"  SKIP (missing): {path}")
        return
    if dry_run:
        print(f"  UPLOAD (dry-run): {path}")
        return
    cmd = [
        "hf", "upload",
        REPO_ID,
        str(local),
        path,
        "--repo-type", REPO_TYPE,
        "--commit-message", f"sync: update {path}",
        "--quiet",
    ]
    print(f"  UPLOAD: {path}")
    _run(cmd)


def delete_file(path: str, dry_run: bool) -> None:
    if _should_skip(path):
        print(f"  SKIP DELETE (blocklist): {path}")
        return
    if dry_run:
        print(f"  DELETE (dry-run): {path}")
        return
    # huggingface_hub API deletion requires Python; fallback to git push
    print(f"  DELETE: {path}")
    from huggingface_hub import HfApi, CommitOperationDelete
    api = HfApi()
    api.create_commit(
        repo_id=REPO_ID,
        repo_type=REPO_TYPE,
        operations=[CommitOperationDelete(path_in_repo=path)],
        commit_message=f"sync: delete {path}",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync changed files to HF Space")
    parser.add_argument(
        "--base",
        default="origin/master",
        help="Git ref to diff against (default: origin/master)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be uploaded/deleted without doing it",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Upload all tracked files (full reset)",
    )
    args = parser.parse_args()

    if args.all:
        files = _run(["git", "ls-files"]).splitlines()
        upload_files = [f for f in files if not _should_skip(f)]
        delete_files = []
    else:
        upload_files, delete_files = get_changed_files(args.base)

    if not upload_files and not delete_files:
        print("No changes to sync.")
        return 0

    print(f"Changes against {args.base}:")
    print(f"  Upload: {len(upload_files)} file(s)")
    print(f"  Delete: {len(delete_files)} file(s)")

    if args.dry_run:
        print("\nDry-run mode — no changes will be made.")

    for path in upload_files:
        try:
            upload_file(path, args.dry_run)
        except subprocess.CalledProcessError as exc:
            print(f"  ERROR uploading {path}: {exc.stderr}", file=sys.stderr)
            return 1

    for path in delete_files:
        try:
            delete_file(path, args.dry_run)
        except Exception as exc:
            print(f"  ERROR deleting {path}: {exc}", file=sys.stderr)
            return 1

    print("\nSync complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
