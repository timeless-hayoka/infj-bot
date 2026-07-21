#!/usr/bin/env python3
"""
Sync DRIFT JSONL logs from the inference droplet to your local machine.

The droplet's job is serve-and-log. Analysis runs offline on your laptop.
This script is a thin wrapper around ``rsync`` (preferred) or ``scp``.

Usage:
    # One-shot pull (default)
    python scripts/sync_logs.py --host drift.example.com --user root

    # Watch mode — keep pulling every 60 s (good for live tail locally)
    python scripts/sync_logs.py --host drift.example.com --user root --watch 60

    # Pull only specific logs
    python scripts/sync_logs.py --host drift.example.com --user root \
        --remote /home/drift/logs --local ./logs

Environment:
    DROPLET_HOST, DROPLET_USER, DROPLET_KEY can be set instead of flags.
"""

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

DEFAULT_REMOTE_DIR = "/opt/drift/logs"
DEFAULT_LOCAL_DIR = "./logs"
DEFAULT_LOG_GLOB = "*.jsonl*"


def _ssh_opts(key: str | None) -> list[str]:
    opts = ["-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=/dev/null"]
    if key:
        opts += ["-i", key]
    return opts


def rsync_pull(
    host: str, user: str, remote_dir: str, local_dir: str, key: str | None
) -> bool:
    src = f"{user}@{host}:{remote_dir}/{DEFAULT_LOG_GLOB}"
    dst = Path(local_dir)
    dst.mkdir(parents=True, exist_ok=True)
    cmd = ["rsync", "-avz", "--progress"] + _ssh_opts(key) + [src, str(dst) + "/"]
    print(" ".join(cmd))
    result = subprocess.run(cmd)
    return result.returncode == 0


def scp_pull(
    host: str, user: str, remote_dir: str, local_dir: str, key: str | None
) -> bool:
    src = f"{user}@{host}:{remote_dir}/{DEFAULT_LOG_GLOB}"
    dst = Path(local_dir)
    dst.mkdir(parents=True, exist_ok=True)
    cmd = ["scp"] + _ssh_opts(key) + [src, str(dst) + "/"]
    print(" ".join(cmd))
    result = subprocess.run(cmd)
    return result.returncode == 0


def pull_once(
    host: str,
    user: str,
    remote_dir: str,
    local_dir: str,
    key: str | None,
    force_scp: bool,
) -> bool:
    if not force_scp:
        # Prefer rsync if available
        if subprocess.run(["which", "rsync"], capture_output=True).returncode == 0:
            return rsync_pull(host, user, remote_dir, local_dir, key)
    return scp_pull(host, user, remote_dir, local_dir, key)


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync DRIFT JSONL logs from droplet")
    parser.add_argument(
        "--host", default=os.getenv("DROPLET_HOST"), help="Droplet IP or hostname"
    )
    parser.add_argument(
        "--user", default=os.getenv("DROPLET_USER", "root"), help="SSH user"
    )
    parser.add_argument(
        "--key", default=os.getenv("DROPLET_KEY"), help="SSH private key path"
    )
    parser.add_argument(
        "--remote", default=DEFAULT_REMOTE_DIR, help="Remote log directory"
    )
    parser.add_argument(
        "--local", default=DEFAULT_LOCAL_DIR, help="Local download directory"
    )
    parser.add_argument(
        "--watch", type=int, metavar="SECONDS", help="Poll interval (watch mode)"
    )
    parser.add_argument("--scp", action="store_true", help="Force scp instead of rsync")
    args = parser.parse_args()

    if not args.host:
        print(
            "Error: --host is required (or set DROPLET_HOST env var).", file=sys.stderr
        )
        sys.exit(1)

    if args.watch:
        print(f"Watch mode: pulling every {args.watch}s. Ctrl-C to stop.")
        while True:
            ok = pull_once(
                args.host, args.user, args.remote, args.local, args.key, args.scp
            )
            if not ok:
                print("Pull failed, retrying...", file=sys.stderr)
            time.sleep(args.watch)
    else:
        ok = pull_once(
            args.host, args.user, args.remote, args.local, args.key, args.scp
        )
        sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
