INFJ Companion MCP
===================

This folder contains a simple MCP manifest and instructions to run the INFJ Companion as an MCP tool via stdio.

Quick start
-----------

1. (Optional) Activate the project's virtual environment:

```bash
source venv/bin/activate
```

2. Run the MCP server (unbuffered Python stdout/stderr):

```bash
./scripts/run_mcp.sh
```

Notes
-----
- The agent uses stdio transport by default. External MCP hosts or orchestrators can start the process and communicate over stdio.
- The manifest is `infj_mcp_agent.yaml` and describes the entrypoint and tools.
