# Documentation

<p align="center">
  <picture>
    <source srcset="assets/drift-banner.webp" type="image/webp" />
    <img src="assets/drift-banner.jpg" alt="DRIFT" width="400" />
  </picture>
</p>

This folder is the canonical **secondary** navigation for DRIFT / INFJ Bot.
Start at the repository [README](../README.md) for the short overview and
quick start. Use this index when you want depth, operations, deployment, or
definitions.

---

## Choose your path

| If you… | Start here |
|---------|------------|
| Want to **run** the bot and configure keys | [README § Getting started](../README.md#getting-started) — then `.env.example` at repo root |
| Want to **understand one chat turn end-to-end** | [HOW_INFJ_BOT_WORKS.md](HOW_INFJ_BOT_WORKS.md) |
| Want to **deploy** (Docker / Hugging Face Spaces) | [DEPLOYMENT.md](DEPLOYMENT.md) |
| Review **secrets and reporting** | [../SECURITY.md](../SECURITY.md) |
| Plan **hive / observatory work** | [HIVE_ROADMAP.md](HIVE_ROADMAP.md) |
| Browse **dependency roles** | [DEPENDENCIES.md](DEPENDENCIES.md) |
| Look up a term | [GLOSSARY.md](GLOSSARY.md) |

---

## All guides (alphabetical)

| Document | Purpose |
|----------|---------|
| [AI_MORALITY_RULES.md](AI_MORALITY_RULES.md) | Ethical rails and behavioral guarantees the bot is held to. |
| [BASELINE_REPORT.md](BASELINE_REPORT.md) | Snapshot metrics from evaluation runs. |
| [DEPENDENCIES.md](DEPENDENCIES.md) | Major packages, what each is for, and how to slim them. |
| [DEPLOYMENT.md](DEPLOYMENT.md) | Docker build, Hugging Face Spaces deploy, ports, and runtime env. |
| [DMU_PEDI_TEST_PLAN.md](DMU_PEDI_TEST_PLAN.md) | Dynamic Memory Unit / PEDI re-ranking test plan. |
| [DRIFT_UPGRADE_MAY_2024.md](DRIFT_UPGRADE_MAY_2024.md) | Performance & networking upgrade notes (gevent, delta-state, hybrid inference). |
| [EDGE_PROTOCOL.md](EDGE_PROTOCOL.md) | Edge / boundary protocol for sensitive operations. |
| [FALSIFIABILITY.md](FALSIFIABILITY.md) | What claims about the architecture are falsifiable, and how. |
| [GLOSSARY.md](GLOSSARY.md) | Project-local terms used across code and chats. |
| [HIVE_ROADMAP.md](HIVE_ROADMAP.md) | Direction for hive / observatory coordination features. |
| [HOW_INFJ_BOT_WORKS.md](HOW_INFJ_BOT_WORKS.md) | Architecture, data flow, modules, env table, verification. |
| [README_UPGRADE.md](README_UPGRADE.md) | Notes from a prior README rewrite cycle. |
| [TEST_RISKS.md](TEST_RISKS.md) | Testing caveats and risk notes. |
| [UPGRADE_BACKLOG.md](UPGRADE_BACKLOG.md) | Planned improvements backlog. |

---

## Recommended reading order

1. [README](../README.md) — scope, layered map, quick start.
2. [HOW_INFJ_BOT_WORKS.md](HOW_INFJ_BOT_WORKS.md) — how prompts, memory, and plugins fit together.
3. [DEPLOYMENT.md](DEPLOYMENT.md) — Docker / HF Spaces ops + LLM provider routing.
4. [../SECURITY.md](../SECURITY.md) — before exposing any interface or sharing backups.
5. [GLOSSARY.md](GLOSSARY.md) — terms you will see in code and chats.

Internal cross-links inside `HOW_INFJ_BOT_WORKS.md` point to the files above
when relevant.
