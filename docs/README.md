# Documentation

<p align="center">
  <picture>
    <source srcset="assets/drift-banner.webp" type="image/webp" />
    <img src="assets/drift-banner.jpg" alt="PHI // DRIFT" width="400" />
  </picture>
</p>

This folder is the canonical **secondary** navigation for **PHI // DRIFT**.
Start at the repository [README](../README.md) for a quick overview and install steps; use this index when you want depth, operations, or definitions.

---

## Choose your path

| If you… | Start here |
|--------|------------|
| Want to **run** the bot and configure keys | [README § Getting Started](../README.md#getting-started) — then `.env.example` at repo root |
| Want to **understand one chat turn end-to-end** | [HOW_INFJ_BOT_WORKS.md](HOW_INFJ_BOT_WORKS.md) |
| Need a reference for **newer subsystems** (security scanner, logic chain, DMU, council, continuity vector) | [SUBSYSTEMS.md](SUBSYSTEMS.md) |
| Look up **codebase-specific terminology** | [GLOSSARY.md](GLOSSARY.md) |
| Audit **secrets and reporting** | [../SECURITY.md](../SECURITY.md) |
| Plan **hive / observatory work** | [HIVE_ROADMAP.md](HIVE_ROADMAP.md) |
| Browse **dependency roles** | [DEPENDENCIES.md](DEPENDENCIES.md) |
| Understand the **research claim** | [FALSIFIABILITY.md](FALSIFIABILITY.md) |

---

## All guides (alphabetical)

| Document | Purpose |
|----------|---------|
| [AI_MORALITY_RULES.md](AI_MORALITY_RULES.md) | Behavioral rails the bot is expected to follow. |
| [BASELINE_REPORT.md](BASELINE_REPORT.md) | Snapshot metrics from evaluation runs. |
| [DEPENDENCIES.md](DEPENDENCIES.md) | What the major Python packages are for, plus a slim-install recipe. |
| [DMU_PEDI_TEST_PLAN.md](DMU_PEDI_TEST_PLAN.md) | Test plan for the DMU (Memory Prioritization Score) and PEDI evaluator. |
| [DRIFT_UPGRADE_MAY_2024.md](DRIFT_UPGRADE_MAY_2024.md) | Historical upgrade notes (gevent web stack, hybrid inference). |
| [EDGE_PROTOCOL.md](EDGE_PROTOCOL.md) | The bot's weekly / daily / monthly self-improvement rhythm. |
| [FALSIFIABILITY.md](FALSIFIABILITY.md) | The DRIFT research claim and how it could be falsified. |
| [GLOSSARY.md](GLOSSARY.md) | Definitions for codebase-specific terms. |
| [HIVE_ROADMAP.md](HIVE_ROADMAP.md) | Direction for hive / observatory coordination features. |
| [HOW_INFJ_BOT_WORKS.md](HOW_INFJ_BOT_WORKS.md) | End-to-end chat-turn flow, modules, env table, verification. |
| [README_UPGRADE.md](README_UPGRADE.md) | Notes that accompanied a previous README rewrite. |
| [SUBSYSTEMS.md](SUBSYSTEMS.md) | Concise reference for security scanner, logic chain, DMU scoring, experiment control, continuity vector, PHI Council, Phi Proxy. |
| [TEST_RISKS.md](TEST_RISKS.md) | Testing caveats and risk notes. |
| [UPGRADE_BACKLOG.md](UPGRADE_BACKLOG.md) | Planned improvements backlog. |

---

## Recommended reading order

1. [README](../README.md) — scope, layered map, quick start.
2. [HOW_INFJ_BOT_WORKS.md](HOW_INFJ_BOT_WORKS.md) — how prompts, memory, and plugins fit together.
3. [SUBSYSTEMS.md](SUBSYSTEMS.md) — what was added in the recent security / reasoning-chain / DMU upgrades.
4. [GLOSSARY.md](GLOSSARY.md) — terminology you will see in code and chats.
5. [../SECURITY.md](../SECURITY.md) — before you expose any interface or share backups.
6. [FALSIFIABILITY.md](FALSIFIABILITY.md) — the experimental claim and what would refute it.

Cross-links inside `HOW_INFJ_BOT_WORKS.md` point to the other files above when relevant.
