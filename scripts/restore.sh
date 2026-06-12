#!/usr/bin/env bash
set -euo pipefail

if [ $# -lt 1 ]; then
  echo "Usage: $0 <backup_dir> [target_dir]" >&2
  exit 2
fi

source_dir="$1"
stamp="$(date +%Y%m%d-%H%M%S)"
target_dir="${2:-$HOME/drift-restored-$stamp}"

if [ ! -d "$source_dir" ]; then
  echo "Backup directory not found: $source_dir" >&2
  exit 1
fi

mkdir -p "$target_dir"

rsync -a \
  --exclude='drift_venv_linux_x86_64.tar.gz' \
  "$source_dir"/ \
  "$target_dir"/

venv_archive="$source_dir/drift_venv_linux_x86_64.tar.gz"
if [ -f "$venv_archive" ]; then
  tar -C "$target_dir" -xzf "$venv_archive"
fi

echo "restored=$target_dir"
echo "source=$source_dir"
echo "NOTE: if the backup stored a .env file, review it before use; otherwise copy credentials from a secure source."
