# Documentation

<p align="center">
  <picture>
    <source srcset="assets/drift-banner.webp" type="image/webp" />
    <img src="assets/drift-banner.jpg" alt="DRIFT" width="400" />
  </picture>
</p>

This folder is the canonical **secondary** navigation for PHI // DRIFT
(`infj-bot`). Start at the repository [README](../README.md) for a short
overview and install; use this index when you want depth, operations,
definitions, or the formal falsifiability statement.

---

## Choose your path

| If you want to… | Start here |
|-----------------|------------|
| **Run** the bot and configure keys | [README § Getting Started](../README.md#getting-started) — then `.env.example` at repo root |
| **Understand one chat turn end-to-end** | [HOW_INFJ_BOT_WORKS.md](HOW_INFJ_BOT_WORKS.md) |
| **Use the Hive Mind / Elysium council** | [HIVE_MIND.md](HIVE_MIND.md) |
| **Plan hive feature work** | [HIVE_ROADMAP.md](HIVE_ROADMAP.md) |
| **Understand the safety / morality rails** | [AI_MORALITY_RULES.md](AI_MORALITY_RULES.md) · [../SECURITY.md](../SECURITY.md) |
| **Read the falsifiability commitments** | [FALSIFIABILITY.md](FALSIFIABILITY.md) |
| **See the DMU + PEDI evaluation plan** | [DMU_PEDI_TEST_PLAN.md](DMU_PEDI_TEST_PLAN.md) |
| **Browse dependency roles** | [DEPENDENCIES.md](DEPENDENCIES.md) |
| **Look up project-local terminology** | [GLOSSARY.md](GLOSSARY.md) |

---

## All guides (alphabetical)

| Document | Purpose |
|----------|---------|
| [AI_MORALITY_RULES.md](AI_MORALITY_RULES.md) | The six hard-coded morality rules baked into the system prompt. |
| [BASELINE_REPORT.md](BASELINE_REPORT.md) | Snapshot metrics from the most recent evaluation run. |
| [DEPENDENCIES.md](DEPENDENCIES.md) | What each major runtime package is for. |
| [DMU_PEDI_TEST_PLAN.md](DMU_PEDI_TEST_PLAN.md) | DMU and PEDI evaluation methodology. |
| [DRIFT_UPGRADE_MAY_2024.md](DRIFT_UPGRADE_MAY_2024.md) | **[archived]** Historical upgrade plan. Superseded by `UPGRADE_BACKLOG.md`. |
| [EDGE_PROTOCOL.md](EDGE_PROTOCOL.md) | The bot's own self-improvement weekly / daily / monthly rhythm. |
| [FALSIFIABILITY.md](FALSIFIABILITY.md) | Pre-ablation falsifiability statement (locked once baseline runs begin). |
| [GLOSSARY.md](GLOSSARY.md) | Project-local definitions for terms in code and docs. |
| [HIVE_MIND.md](HIVE_MIND.md) | Two-tier Hive Mind / Elysium guide — commands, API, Nexus Loop, SQLite state. |
| [HIVE_ROADMAP.md](HIVE_ROADMAP.md) | Phase-by-phase roadmap for distributed cognition. |
| [HOW_INFJ_BOT_WORKS.md](HOW_INFJ_BOT_WORKS.md) | End-to-end architecture, data flow, modules, env table, verification. |
| [README_UPGRADE.md](README_UPGRADE.md) | Pre-test execution guide for the DRIFT upgrade. |
| [TEST_RISKS.md](TEST_RISKS.md) | Known testing caveats and risks. |
| [UPGRADE_BACKLOG.md](UPGRADE_BACKLOG.md) | Current planned improvements backlog. |

---

## Recommended reading order

1. [README](../README.md) — scope, layers, quick start.
2. [HOW_INFJ_BOT_WORKS.md](HOW_INFJ_BOT_WORKS.md) — how prompts, memory, and plugins fit together.
3. [HIVE_MIND.md](HIVE_MIND.md) — distributed cognition, once you have the single-bot picture.
4. [../SECURITY.md](../SECURITY.md) — before you expose any interface or share backups.
5. [AI_MORALITY_RULES.md](AI_MORALITY_RULES.md) and [FALSIFIABILITY.md](FALSIFIABILITY.md) — the commitments behind behavior claims.
6. [GLOSSARY.md](GLOSSARY.md) — terms you will see in code and chat output.

Internal cross-links inside `HOW_INFJ_BOT_WORKS.md` point to the other files
above when relevant.
