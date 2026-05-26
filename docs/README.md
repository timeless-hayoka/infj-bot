# Documentation

<p align="center">
  <picture>
    <source srcset="assets/drift-banner.webp" type="image/webp" />
    <img src="assets/drift-banner.jpg" alt="DRIFT" width="400" />
  </picture>
</p>

This folder is the canonical **secondary** navigation for PHI // DRIFT (a.k.a. INFJ Bot). Start at the repository [README](../README.md) for a short overview, install steps, and the May 2026 changelog. Use this index when you want depth, methodology, or terminology.

---

## Choose your path

| If you… | Start here |
|--------|------------|
| Want to **run** the bot and configure keys | [README § Getting started](../README.md#getting-started) — then `.env.example` at repo root |
| Want to **understand one chat turn end-to-end** | [HOW_INFJ_BOT_WORKS.md](HOW_INFJ_BOT_WORKS.md) |
| Want to know **how the security scanner and logic chain work** | [SECURITY_AND_LOGIC_CHAIN.md](SECURITY_AND_LOGIC_CHAIN.md) |
| Want to understand **DMU re-ranking and PEDI state-fluidity** | [DMU_PEDI_TEST_PLAN.md](DMU_PEDI_TEST_PLAN.md) |
| Want the **upgrade execution / experiment discipline** | [README_UPGRADE.md](README_UPGRADE.md) → [FALSIFIABILITY.md](FALSIFIABILITY.md) |
| Want **ethical posture & operational rails** | [AI_MORALITY_RULES.md](AI_MORALITY_RULES.md), [EDGE_PROTOCOL.md](EDGE_PROTOCOL.md) |
| Review **secrets and reporting** | [../SECURITY.md](../SECURITY.md) |
| Plan **hive / observatory work** | [HIVE_ROADMAP.md](HIVE_ROADMAP.md) |
| Browse **dependency roles** | [DEPENDENCIES.md](DEPENDENCIES.md) |

---

## All guides (alphabetical)

| Document | Purpose |
|----------|---------|
| [AI_MORALITY_RULES.md](AI_MORALITY_RULES.md) | Ethical posture and behavioral rails the bot is asked to honor. |
| [BASELINE_REPORT.md](BASELINE_REPORT.md) | Snapshot metrics from evaluations (when generated). |
| [DEPENDENCIES.md](DEPENDENCIES.md) | What major packages/runtime pieces are for and what is slimmable. |
| [DMU_PEDI_TEST_PLAN.md](DMU_PEDI_TEST_PLAN.md) | Testing methodology for the Dynamic Memory Unit and Performance/Efficiency Detection Index. |
| [DRIFT_UPGRADE_MAY_2024.md](DRIFT_UPGRADE_MAY_2024.md) | Background notes on the May 2024 networking/perf upgrade. |
| [EDGE_PROTOCOL.md](EDGE_PROTOCOL.md) | Tripwires and de-escalation paths for high-risk turns. |
| [FALSIFIABILITY.md](FALSIFIABILITY.md) | Committed falsifiability statement for the DRIFT upgrade — frozen once baseline is collected. |
| [GLOSSARY.md](GLOSSARY.md) | Project-local term definitions. |
| [HIVE_ROADMAP.md](HIVE_ROADMAP.md) | Direction for hive / Elysium / Council coordination features. |
| [HOW_INFJ_BOT_WORKS.md](HOW_INFJ_BOT_WORKS.md) | Architecture, data flow diagram, modules, env table, verification. |
| [README_UPGRADE.md](README_UPGRADE.md) | Ordered execution guide for wiring the upgrade infrastructure (run_logger, experiment_control, DMU scoring). |
| [SECURITY_AND_LOGIC_CHAIN.md](SECURITY_AND_LOGIC_CHAIN.md) | Security defense layer + logic-chain reasoning trace: design, integration points, audit log, slash commands. |
| [TEST_RISKS.md](TEST_RISKS.md) | Testing caveats and risk notes. |
| [UPGRADE_BACKLOG.md](UPGRADE_BACKLOG.md) | Planned improvements backlog. |

---

## Recommended reading order

1. [README](../README.md) — scope, layered map, what's new, quick start
2. [HOW_INFJ_BOT_WORKS.md](HOW_INFJ_BOT_WORKS.md) — how prompts, memory, and plugins fit together
3. [SECURITY_AND_LOGIC_CHAIN.md](SECURITY_AND_LOGIC_CHAIN.md) — the two newest pre-generation subsystems
4. [DMU_PEDI_TEST_PLAN.md](DMU_PEDI_TEST_PLAN.md) — what DMU re-ranking and PEDI continuity scoring actually measure
5. [../SECURITY.md](../SECURITY.md) — before you expose any interface or share backups
6. [GLOSSARY.md](GLOSSARY.md) — terms you will see in code and chats

Internal cross-links inside `HOW_INFJ_BOT_WORKS.md` point to the files above when relevant.
