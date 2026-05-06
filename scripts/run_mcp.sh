#!/usr/bin/env bash
set -euo pipefail

# Activate virtualenv if present
if [ -f "venv/bin/activate" ]; then
  # shellcheck disable=SC1091
  source venv/bin/activate
fi

# Allow selecting transport: 'stdio' (default) or 'http'
if [ "${1:-}" = "http" ] || [ "${MCP_TRANSPORT:-}" = "http" ]; then
  export MCP_TRANSPORT=http
fi

# Run the MCP server unbuffered so external orchestrators can read logs promptly
python -u mcp_server.py
