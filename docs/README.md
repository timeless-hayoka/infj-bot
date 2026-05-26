# Documentation

<p align="center">
  <picture>
    <source srcset="assets/drift-banner.webp" type="image/webp" />
    <img src="assets/drift-banner.jpg" alt="DRIFT" width="400" />
  </picture>
</p>

This folder is the canonical **secondary** navigation for PHI // DRIFT.
Start at the repository [README](../README.md) for the short overview and the
install steps; use this index when you want depth, operations, or definitions.

---

## Choose your path

| If you… | Start here |
|--------|------------|
| Want to **run** the bot and configure keys | [README § Getting Started](../README.md#getting-started) — then `.env.example` at repo root |
| Want to **understand one chat turn end-to-end** | [HOW_INFJ_BOT_WORKS.md](HOW_INFJ_BOT_WORKS.md) |
| Need to know how the **Global Workspace** decides what's in focus | [GLOBAL_WORKSPACE.md](GLOBAL_WORKSPACE.md) |
| Are integrating with the **Hive Mind** or `/hive` commands | [HIVE_MIND.md](HIVE_MIND.md) |
| Review **secrets and reporting** | [SECURITY.md](../SECURITY.md) |
| Plan **hive / observatory work** | [HIVE_ROADMAP.md](HIVE_ROADMAP.md) |
| Browse **dependency roles** | [DEPENDENCIES.md](DEPENDENCIES.md) |

---

## All guides (alphabetical)

| Document | Purpose |
|----------|---------|
| [AI_MORALITY_RULES.md](AI_MORALITY_RULES.md) | Operator-facing notes on the alignment / morality posture. |
| [BASELINE_REPORT.md](BASELINE_REPORT.md) | Snapshot metrics from evaluations (when generated). |
| [DEPENDENCIES.md](DEPENDENCIES.md) | What major packages/runtime pieces are for and which are slimmable. |
| [DMU_PEDI_TEST_PLAN.md](DMU_PEDI_TEST_PLAN.md) | Test plan for DMU scoring and the PEDI metric family. |
| [DRIFT_UPGRADE_MAY_2024.md](DRIFT_UPGRADE_MAY_2024.md) | Historical upgrade record: gevent, delta broadcasting, Groq, etc. |
| [EDGE_PROTOCOL.md](EDGE_PROTOCOL.md) | Edge-device deployment posture and constraints. |
| [FALSIFIABILITY.md](FALSIFIABILITY.md) | What this system *isn't* — claims that are testable vs. metaphorical. |
| [GLOBAL_WORKSPACE.md](GLOBAL_WORKSPACE.md) | Tiered attention system: spotlight → active → preconscious → archived. |
| [GLOSSARY.md](GLOSSARY.md) | Project-local definitions (Chroma, plugins, modes, etc.). |
| [HIVE_MIND.md](HIVE_MIND.md) | `hive_mind/` package: consensus engine, DCP protocol, node registry, `/hive` commands. |
| [HIVE_ROADMAP.md](HIVE_ROADMAP.md) | Phased plan for distributed cognition features. |
| [HOW_INFJ_BOT_WORKS.md](HOW_INFJ_BOT_WORKS.md) | Architecture, one-turn data flow, modules, env table, verification. |
| [README_UPGRADE.md](README_UPGRADE.md) | Notes on the DRIFT upgrade infrastructure (DMU, experiment control). |
| [TEST_RISKS.md](TEST_RISKS.md) | Testing caveats and risk notes. |
| [UPGRADE_BACKLOG.md](UPGRADE_BACKLOG.md) | Planned improvements backlog. |

---

## Recommended reading order

1. [README](../README.md) — scope, layers, quick start
2. [HOW_INFJ_BOT_WORKS.md](HOW_INFJ_BOT_WORKS.md) — how prompts, memory, and plugins fit together
3. [GLOBAL_WORKSPACE.md](GLOBAL_WORKSPACE.md) — the attention layer that gates what reaches every prompt
4. [HIVE_MIND.md](HIVE_MIND.md) — how distributed deliberation works and how to drive it from the CLI / API
5. [SECURITY.md](../SECURITY.md) — before you expose any interface or share backups
6. [GLOSSARY.md](GLOSSARY.md) — terms you will see in code and chats

Internal cross-links inside `HOW_INFJ_BOT_WORKS.md` point to other files above
when relevant.
