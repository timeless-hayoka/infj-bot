# Private ChatGPT tunnel

This stdio gateway is intentionally separate from the general-purpose DRIFT MCP server. The default tool is drift_health. Set DRIFT_MCP_MEMORY_READ=1 only for a dedicated, reviewed memory corpus explicitly authorized for ChatGPT. Memory writes, commands, autonomy and inference are not exposed. The gateway uses the local authenticated Compose adapter; it cannot choose arbitrary upstream hosts or follow redirects.

1. Start the private Compose adapter following docs/private-adapter-compose.md, using an isolated state volume for the initial trial.
2. Install the project's Python dependencies into a local virtual environment (python -m pip install -e .). Keep DRIFT_PLUGIN_TOKEN in the local environment, matching the adapter; set DRIFT_PORT if not 8000.
3. Create or reuse a tunnel in https://platform.openai.com/settings/organization/tunnels and a restricted runtime API key with Tunnels Read + Use. Associate the intended ChatGPT workspace where supported.
4. Install the official tunnel-client from https://github.com/openai/tunnel-client/releases/latest and run tunnel-client help quickstart. Enter the runtime key locally as CONTROL_PLANE_API_KEY, never in Git or chat.
5. Configure a local stdio profile using your actual tunnel ID and absolute virtualenv Python path:

```sh
tunnel-client init --sample sample_mcp_stdio_local --profile drift-private --tunnel-id "$DRIFT_TUNNEL_ID" --mcp-command "/absolute/path/to/.venv/bin/python -m drift.core.private_mcp"
tunnel-client doctor --profile drift-private --explain
tunnel-client run --profile drift-private
```

6. In ChatGPT web, Plugins > + > Add custom MCP server > Tunnel, if enabled for your plan/workspace. Select the authorized tunnel, review the tools and create the private connection. Call drift_health first. Do not enable memory reads until the target corpus is approved.
7. If ChatGPT custom MCP access is unavailable, the Responses API can use the tunnel_id directly subject to API permissions and billing.

CI validates actual MCP stdio initialization, exact tool allowlist, authenticated health, rejected wrong token, denied unknown tool, input bounds and retrieval of a synthetic marker persisted across container recreation. A successful CI run is not evidence of a live OpenAI tunnel or ChatGPT invocation.
