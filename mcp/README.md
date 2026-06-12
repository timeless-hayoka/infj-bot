INFJ Companion MCP
===================

This folder contains a simple MCP manifest and instructions to run the INFJ Companion as an MCP tool via stdio.

MCP, in plain terms: the host app is the place you talk to an AI, and the MCP
server is a small tool provider the host can start. They speak JSON-RPC over a
transport such as stdio, then the host asks for the tool list and calls tools by
name with structured arguments.

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

3. Register it with Codex:

```bash
codex mcp add infj-companion -- /home/crexs/drift/scripts/run_mcp.sh
```

Check the registration:

```bash
codex mcp list
codex mcp get infj-companion --json
```

Notes
-----
- The agent uses stdio transport by default. External MCP hosts or orchestrators can start the process and communicate over stdio.
- The manifest is `infj_mcp_agent.yaml` and describes the entrypoint and tools.
- `scripts/run_mcp.sh` changes into the project root before launching, so MCP hosts can start it from any working directory.
- The launcher defaults `INFJ_EMBEDDING_MODE=local` for reliable offline startup. Set `INFJ_EMBEDDING_MODE=semantic` before launching if the semantic model is installed and you want semantic retrieval.
