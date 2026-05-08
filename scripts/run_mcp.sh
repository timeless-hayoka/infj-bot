#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${PROJECT_ROOT}"

# Activate virtualenv if present
if [ -f "venv/bin/activate" ]; then
  # shellcheck disable=SC1091
  source venv/bin/activate
fi

# Allow selecting transport: 'stdio' (default) or 'http'
if [ "${1:-}" = "http" ] || [ "${MCP_TRANSPORT:-}" = "http" ]; then
  export MCP_TRANSPORT=http
fi

export INFJ_EMBEDDING_MODE="${INFJ_EMBEDDING_MODE:-local}"

# Run the MCP server unbuffered so external orchestrators can read logs promptly
python -u mcp_server.py
