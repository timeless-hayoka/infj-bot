# Security

## Reporting

If you discover a security issue in this repository, please message the maintainer privately (do not open a public issue with exploit details).

## Secrets

- Never commit `.env`, API keys, tokens, or private keys. Use `.env.example` as a template only.
- If a secret was ever committed, rotate it immediately in the provider console (even after removing it from git history, assume it was exposed).

## Related codebases

- **`drift-engine`** is maintained as a **separate private** repository. This project does **not** submodule or vendor it; integration is limited to **seeded cognition concepts** and internal documentation. Do not publish or expect a public clone URL for Drift alongside this repo.

## Local data

Runtime databases, Chroma stores, and `history.jsonl` are gitignored. Treat backups of those files as sensitive if they contain personal conversations.
