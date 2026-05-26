# Documentation

<p align="center">
  <picture>
    <source srcset="assets/drift-banner.webp" type="image/webp" />
    <img src="assets/drift-banner.jpg" alt="DRIFT" width="400" />
  </picture>
</p>

This folder is the canonical **secondary** navigation for PHI // DRIFT (INFJ Bot). Start at the repository [README](../README.md) for a short overview and install; use this index when you want depth, operations, or definitions.

---

## Choose your path

| If you… | Start here |
|--------|------------|
| Want to **run** the bot and configure keys | [README § Getting started](../README.md#getting-started) — then `.env.example` at repo root |
| Want to **understand one chat turn end-to-end** | [HOW_INFJ_BOT_WORKS.md](HOW_INFJ_BOT_WORKS.md) |
| Need details on a **specific subsystem** (shadow governance, task mutator, retry wrapper, hive mind, continuity vector triad) | [SUBSYSTEMS.md](SUBSYSTEMS.md) |
| Need to operate the **web interface / Observatory / Glyph / trial sandbox** | [WEB_INTERFACE.md](WEB_INTERFACE.md) |
| Review **secrets and reporting** | [SECURITY.md](../SECURITY.md) |
| Plan **hive / observatory work** | [HIVE_ROADMAP.md](HIVE_ROADMAP.md) |
| Browse **dependency roles** | [DEPENDENCIES.md](DEPENDENCIES.md) |
| Run **ablations** against the upgrade infrastructure | [README_UPGRADE.md](README_UPGRADE.md) → [FALSIFIABILITY.md](FALSIFIABILITY.md) |

---

## All guides (alphabetical)

| Document | Purpose |
|----------|---------|
| [AI_MORALITY_RULES.md](AI_MORALITY_RULES.md) | Behavioral rules embedded in prompts and guardrails. |
| [BASELINE_REPORT.md](BASELINE_REPORT.md) | Snapshot metrics from evaluations (when generated). |
| [DEPENDENCIES.md](DEPENDENCIES.md) | What major packages/runtime pieces are for. |
| [DMU_PEDI_TEST_PLAN.md](DMU_PEDI_TEST_PLAN.md) | Testing methodology for DMU re-ranking and the PEDI fluidity metric. |
| [DRIFT_UPGRADE_MAY_2024.md](DRIFT_UPGRADE_MAY_2024.md) | Archived: networking + Observatory upgrade notes. |
| [EDGE_PROTOCOL.md](EDGE_PROTOCOL.md) | Edge / failsafe protocol for the assistant. |
| [FALSIFIABILITY.md](FALSIFIABILITY.md) | Committed falsifiability statement — read before ablations. |
| [GLOSSARY.md](GLOSSARY.md) | Definitions for codebase-specific terms. |
| [HIVE_ROADMAP.md](HIVE_ROADMAP.md) | Direction for hive / observatory coordination features. |
| [HOW_INFJ_BOT_WORKS.md](HOW_INFJ_BOT_WORKS.md) | Architecture, data flow diagram, modules, env table, verification. |
| [README_UPGRADE.md](README_UPGRADE.md) | Pre-test execution guide for the upgrade infrastructure (DMU, continuity vector, ablations). |
| [SUBSYSTEMS.md](SUBSYSTEMS.md) | Shadow governance, task mutator, retry wrapper, hive mind, continuity vector triad. |
| [TEST_RISKS.md](TEST_RISKS.md) | Testing caveats and risk notes. |
| [UPGRADE_BACKLOG.md](UPGRADE_BACKLOG.md) | Planned improvements backlog. |
| [WEB_INTERFACE.md](WEB_INTERFACE.md) | Flask web app routes, Observatory SocketIO stream, glyph, trial sandbox, OpenAI/Ollama shims. |

---

## Recommended reading order

1. [README](../README.md) — scope, layers, quick start.
2. [HOW_INFJ_BOT_WORKS.md](HOW_INFJ_BOT_WORKS.md) — how prompts, memory, and plugins fit together.
3. [SUBSYSTEMS.md](SUBSYSTEMS.md) — the cognitive subsystems referenced from the chat-turn flow.
4. [WEB_INTERFACE.md](WEB_INTERFACE.md) — only if you're operating the web app, dashboard, or compatibility shims.
5. [SECURITY.md](../SECURITY.md) — before you expose any interface or share backups.
6. [GLOSSARY.md](GLOSSARY.md) — terms you will see in code and chats.
