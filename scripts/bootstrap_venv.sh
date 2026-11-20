#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

PYTHON_BIN="${PYTHON_BIN:-python3}"
VENV_DIR="${VENV_DIR:-.venv}"
VENV_PY="$VENV_DIR/bin/python"

# A shared or system-site-enabled environment can satisfy dependencies with
# incompatible distro packages. Preserve it, then build a project-local venv.
if [[ -L "$VENV_DIR" ]] || {
    [[ -f "$VENV_DIR/pyvenv.cfg" ]] &&
        grep -Eq '^include-system-site-packages[[:space:]]*=[[:space:]]*true$' "$VENV_DIR/pyvenv.cfg"
}; then
    backup="$VENV_DIR.pre-isolation"
    suffix=1
    while [[ -e "$backup" || -L "$backup" ]]; do
        backup="$VENV_DIR.pre-isolation.$suffix"
        suffix=$((suffix + 1))
    done
    mv "$VENV_DIR" "$backup"
    echo "Preserved non-isolated environment at $backup"
fi

if [[ ! -x "$VENV_PY" ]]; then
    "$PYTHON_BIN" -m venv "$VENV_DIR"
fi

if grep -Eq '^include-system-site-packages[[:space:]]*=[[:space:]]*true$' "$VENV_DIR/pyvenv.cfg"; then
    echo "Refusing to install into a system-site-enabled virtualenv: $VENV_DIR" >&2
    exit 2
fi

"$VENV_PY" -m pip install --timeout 120 --upgrade pip setuptools wheel

# PyPI's Linux torch package can pull a full CUDA toolchain even on machines
# with no NVIDIA GPU. Preinstall the CPU build so the project requirement is
# already satisfied when the remaining dependency graph is resolved.
if ! command -v nvidia-smi >/dev/null 2>&1; then
    "$VENV_PY" -m pip install --timeout 120 "torch>=2.11" \
        --index-url https://download.pytorch.org/whl/cpu
fi

"$VENV_PY" -m pip install --timeout 120 --resume-retries 12 -e ".[dev]"

echo "Bootstrap complete: $VENV_PY"
