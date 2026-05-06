# Security

## Reporting

If you discover a security issue in this repository, please message the maintainer privately (do not open a public issue with exploit details).

## Secrets & Credentials

- **Never commit `.env`, API keys, tokens, private keys, or organization IDs.** Use `.env.example` as a template only.
- **Organization IDs are sensitive.** Treat `ANTHROPIC_ORG_ID` and similar identifiers with the same care as API keys. They can be used for access control and billing attribution.
- If a secret was ever committed, rotate it immediately in the provider console (even after removing it from git history, assume it was exposed).
- A pre-commit hook is installed in `.git/hooks/pre-commit` to block common secret patterns. If you bypass it with `--no-verify`, run `./scripts/check_secrets.sh` manually before pushing.

## Supported Providers

| Provider | Env Var | Notes |
|----------|---------|-------|
| Google Gemini | `API_KEY` / `GEMINI_API_KEY` / `GOOGLE_API_KEY` | Primary LLM |
| Anthropic Claude | `ANTHROPIC_API_KEY` / `CLAUDE_API_KEY` | Optional secondary provider |
| Anthropic Org | `ANTHROPIC_ORG_ID` | Sensitive org identifier |
| Ollama | `OLLAMA_HOST` | Local fallback, no secret needed |

## Related Codebases

- **`drift-engine`** is maintained as a **separate private** repository. This project does **not** submodule or vendor it; integration is limited to **seeded cognition concepts** and internal documentation. Do not publish or expect a public clone URL for Drift alongside this repo.

## Local Data

Runtime databases, Chroma stores, and `history.jsonl` are gitignored. Treat backups of those files as sensitive if they contain personal conversations.
