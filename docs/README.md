# Documentation

<p align="center">
  <picture>
    <source srcset="assets/drift-banner.webp" type="image/webp" />
    <img src="assets/drift-banner.jpg" alt="DRIFT" width="400" />
  </picture>
</p>

This folder is the canonical **secondary** navigation for DRIFT / INFJ Bot. Start at the repository [README](../README.md) for a short overview and install; use this index when you want depth, operations, or definitions.

---

## Choose your path

| If you… | Start here |
|--------|------------|
| Want to **run** the bot and configure keys | [README § Getting started](../README.md#getting-started) — then `.env.example` at repo root |
| Want to **understand one chat turn end-to-end** | [HOW_INFJ_BOT_WORKS.md](HOW_INFJ_BOT_WORKS.md) |
| **Deploy** via Docker or Hugging Face Spaces | [DEPLOYMENT.md](DEPLOYMENT.md) |
| Use the **`/bug` workflow** (Bugcrowd, recon, reports) | [BUG_BOT.md](BUG_BOT.md) |
| Wire up the **hive consensus engine** (`/hive propose`) | [HIVE_MIND.md](HIVE_MIND.md) |
| Tune **shadow / task mutator / retry wrapper** | [SHADOW_GOVERNANCE.md](SHADOW_GOVERNANCE.md) |
| Measure **behavioral continuity** | [CONTINUITY_VECTOR.md](CONTINUITY_VECTOR.md) |
| Understand the **falsifiability / measurement claims** | [FALSIFIABILITY.md](FALSIFIABILITY.md) |
| Review **secrets and reporting** | [SECURITY.md](../SECURITY.md) |
| Plan **hive / observatory work** | [HIVE_ROADMAP.md](HIVE_ROADMAP.md) |
| Browse **dependency roles** | [DEPENDENCIES.md](DEPENDENCIES.md) |

---

## All guides (alphabetical)

| Document | Purpose |
|----------|---------|
| [AI_MORALITY_RULES.md](AI_MORALITY_RULES.md) | Ethical constraints and refusal boundaries baked into the system. |
| [BASELINE_REPORT.md](BASELINE_REPORT.md) | Snapshot metrics from evaluations (when generated). |
| [BUG_BOT.md](BUG_BOT.md) | Bug-bounty workflow: `/bug` commands, Bugcrowd client, findings DB, reports. |
| [CONTINUITY_VECTOR.md](CONTINUITY_VECTOR.md) | Five-axis baseline continuity scoring + three-axis `[memory, state, novelty]` triad. |
| [DEPENDENCIES.md](DEPENDENCIES.md) | What major packages/runtime pieces are for. |
| [DEPLOYMENT.md](DEPLOYMENT.md) | Docker, Hugging Face Space, ports, HTTP routes, common pitfalls. |
| [DMU_PEDI_TEST_PLAN.md](DMU_PEDI_TEST_PLAN.md) | Test plan for DMU scoring and PEDI continuity validation. |
| [DRIFT_UPGRADE_MAY_2024.md](DRIFT_UPGRADE_MAY_2024.md) | Upgrade notes from the May 2024 hardening pass. |
| [EDGE_PROTOCOL.md](EDGE_PROTOCOL.md) | Edge-case handling and escalation protocol. |
| [FALSIFIABILITY.md](FALSIFIABILITY.md) | Falsifiable claims, measurement axes, and ablation discipline. |
| [GLOSSARY.md](GLOSSARY.md) | Definitions for all DRIFT-specific terms used in code and docs. |
| [HIVE_MIND.md](HIVE_MIND.md) | `hive_mind/` package: `ConsensusEngine`, `HiveOrchestrator`, DCP message format. |
| [HIVE_ROADMAP.md](HIVE_ROADMAP.md) | Direction for hive / observatory coordination features. |
| [HOW_INFJ_BOT_WORKS.md](HOW_INFJ_BOT_WORKS.md) | Architecture, data flow diagram, modules, env table, verification. |
| [README_UPGRADE.md](README_UPGRADE.md) | Guide for upgrading between DRIFT versions. |
| [SHADOW_GOVERNANCE.md](SHADOW_GOVERNANCE.md) | Shadow governance, task mutator, and retry wrapper. |
| [TEST_RISKS.md](TEST_RISKS.md) | Testing caveats and risk notes. |
| [UPGRADE_BACKLOG.md](UPGRADE_BACKLOG.md) | Planned improvements backlog. |

---

## Recommended reading order

1. [README](../README.md) — scope, layers, quick start
2. [HOW_INFJ_BOT_WORKS.md](HOW_INFJ_BOT_WORKS.md) — how prompts, memory, and plugins fit together
3. [SECURITY.md](../SECURITY.md) — before you expose any interface or share backups
4. [FALSIFIABILITY.md](FALSIFIABILITY.md) — what the architecture actually claims and how to verify it
5. [GLOSSARY.md](GLOSSARY.md) — terms you will see in code and chats

Internal cross-links inside `HOW_INFJ_BOT_WORKS.md` point to other files above when relevant.
