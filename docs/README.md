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
| Understand the **attention workspace** (spotlight, preconscious, archive) | [TIERED_ATTENTION.md](TIERED_ATTENTION.md) |
| Wire into the **hive kernel** (DCP, consensus, nodes) | [HIVE_MIND.md](HIVE_MIND.md) |
| Integrate **Drift-named posture** via memory seeds only | [DRIFT_AI_INTEGRATION.md](DRIFT_AI_INTEGRATION.md) |
| Review **secrets and reporting** | [SECURITY.md](../SECURITY.md) |
| Plan **hive / observatory work** | [HIVE_ROADMAP.md](HIVE_ROADMAP.md) |
| Browse **dependency roles** | [DEPENDENCIES.md](DEPENDENCIES.md) |

---

## All guides (alphabetical)

| Document | Purpose |
|----------|---------|
| [BASELINE_REPORT.md](BASELINE_REPORT.md) | Snapshot metrics from evaluations (when generated). |
| [DELL_HANDOFF.md](DELL_HANDOFF.md) | Long-form ops notes: devices, workflows, quirks. |
| [DEPENDENCIES.md](DEPENDENCIES.md) | What major packages/runtime pieces are for. |
| [DRIFT_AI_INTEGRATION.md](DRIFT_AI_INTEGRATION.md) | How Drift-related concepts are seeded into memory—not a submodule. |
| [HIVE_MIND.md](HIVE_MIND.md) | Hive kernel: DCP protocol, `ConsensusEngine`, `HiveOrchestrator`, wiring into the bot. |
| [HIVE_ROADMAP.md](HIVE_ROADMAP.md) | Direction for hive / observatory coordination features. |
| [HOW_INFJ_BOT_WORKS.md](HOW_INFJ_BOT_WORKS.md) | Architecture, data flow diagram, modules, env table, verification. |
| [TIERED_ATTENTION.md](TIERED_ATTENTION.md) | Spotlight / Active / Preconscious / Archived attention workspace in `core/global_workspace.py`. |
| [REDDIT_REPLY_DRAFT.md](REDDIT_REPLY_DRAFT.md) | Draft external communication (historical/context). |
| [SHADOW_REDDIT_POST.md](SHADOW_REDDIT_POST.md) | Draft post material around shadow subsystem. |
| [TEST_RISKS.md](TEST_RISKS.md) | Testing caveats and risk notes. |
| [UPGRADE_BACKLOG.md](UPGRADE_BACKLOG.md) | Planned improvements backlog. |

---

## Recommended reading order

1. [README](../README.md) — scope, layers, quick start  
2. [HOW_INFJ_BOT_WORKS.md](HOW_INFJ_BOT_WORKS.md) — how prompts, memory, and plugins fit together  
3. [SECURITY.md](../SECURITY.md) — before you expose any interface or share backups  
4. [DRIFT_AI_INTEGRATION.md](DRIFT_AI_INTEGRATION.md) — if you customize “Drift” continuity  
5. [GLOSSARY.md](GLOSSARY.md) — terms you will see in code and chats  

Internal cross-links inside `HOW_INFJ_BOT_WORKS.md` point to other files above when relevant.
