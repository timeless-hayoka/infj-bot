# Documentation

<p align="center">
  <picture>
    <source srcset="assets/drift-banner.webp" type="image/webp" />
    <img src="assets/drift-banner.jpg" alt="DRIFT" width="400" />
  </picture>
</p>

This folder is the canonical **secondary** navigation for PHI // DRIFT / INFJ Bot. Start at the repository [README](../README.md) for a short overview and install; use this index when you want depth, operations, or definitions.

---

## Choose your path

| If you… | Start here |
|--------|------------|
| Want to **run** the bot and configure keys | [README § Getting Started](../README.md#getting-started) — then `.env.example` at repo root |
| Want to **understand one chat turn end-to-end** | [HOW_INFJ_BOT_WORKS.md](HOW_INFJ_BOT_WORKS.md) |
| Need a **term defined** the way the code uses it | [GLOSSARY.md](GLOSSARY.md) |
| Review **secrets and reporting** | [SECURITY.md](../SECURITY.md) |
| Look up **what each dependency does** | [DEPENDENCIES.md](DEPENDENCIES.md) |
| Want to know **what the bot will and won't do** | [AI_MORALITY_RULES.md](AI_MORALITY_RULES.md) |
| Audit the **experimental claims** | [FALSIFIABILITY.md](FALSIFIABILITY.md), [BASELINE_REPORT.md](BASELINE_REPORT.md), [DMU_PEDI_TEST_PLAN.md](DMU_PEDI_TEST_PLAN.md) |
| Plan **hive / observatory work** | [HIVE_ROADMAP.md](HIVE_ROADMAP.md) |

---

## All guides (alphabetical)

| Document | Purpose |
|----------|---------|
| [AI_MORALITY_RULES.md](AI_MORALITY_RULES.md) | The 6 hard-coded morality rules baked into the system prompt — written to be testable, not vague. |
| [BASELINE_REPORT.md](BASELINE_REPORT.md) | Pre-ablation baseline metrics snapshot, used as the comparison floor for upgrade evaluations. |
| [DEPENDENCIES.md](DEPENDENCIES.md) | What each major package and runtime piece in `requirements.txt` is actually used for. |
| [DMU_PEDI_TEST_PLAN.md](DMU_PEDI_TEST_PLAN.md) | Testing methodology for the Dynamic Memory Unit (DMU) re-ranker and Personality / Emotional / Drift Integration (PEDI) coupling. |
| [DRIFT_UPGRADE_MAY_2024.md](DRIFT_UPGRADE_MAY_2024.md) | **[Archived]** Historical record of the May 2024 upgrade pass — kept for context, superseded by [UPGRADE_BACKLOG.md](UPGRADE_BACKLOG.md). |
| [EDGE_PROTOCOL.md](EDGE_PROTOCOL.md) | The weekly / daily / monthly self-improvement rhythm the bot runs against itself. |
| [FALSIFIABILITY.md](FALSIFIABILITY.md) | The locked, pre-ablation falsifiability statement — what claims the experiments can and cannot disprove. |
| [GLOSSARY.md](GLOSSARY.md) | Project-local definitions: how this codebase names things (not universal AI/neuroscience terms). |
| [HIVE_ROADMAP.md](HIVE_ROADMAP.md) | Direction for hive / observatory coordination features. |
| [HOW_INFJ_BOT_WORKS.md](HOW_INFJ_BOT_WORKS.md) | End-to-end architecture: one chat turn from input to memory write, with a Mermaid flow and module map. |
| [README_UPGRADE.md](README_UPGRADE.md) | Pre-test execution guide for the DRIFT upgrade pass — ordered steps, no improvising. |
| [TEST_RISKS.md](TEST_RISKS.md) | Testing caveats, known-flaky areas, and risk notes for evaluation runs. |
| [UPGRADE_BACKLOG.md](UPGRADE_BACKLOG.md) | Planned improvements backlog (active roadmap). |

---

## Recommended reading order

1. [README](../README.md) — scope, five-layer map, quick start, May 2026 highlights
2. [HOW_INFJ_BOT_WORKS.md](HOW_INFJ_BOT_WORKS.md) — how prompts, memory, and plugins fit together in one turn
3. [GLOSSARY.md](GLOSSARY.md) — terms you will see in code, commits, and chats
4. [AI_MORALITY_RULES.md](AI_MORALITY_RULES.md) — the hard rails before you customize behavior
5. [SECURITY.md](../SECURITY.md) — before you expose any interface or share backups
6. [FALSIFIABILITY.md](FALSIFIABILITY.md) → [BASELINE_REPORT.md](BASELINE_REPORT.md) → [DMU_PEDI_TEST_PLAN.md](DMU_PEDI_TEST_PLAN.md) — if you are reproducing or auditing the published results

Internal cross-links inside [HOW_INFJ_BOT_WORKS.md](HOW_INFJ_BOT_WORKS.md) point to other files above when relevant.
