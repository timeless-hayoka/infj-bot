# HIVE Roadmap

Practical roadmap for turning `infj_bot + DRIFT + hive_mind` into a real multi-agent cognitive system instead of a collection of disconnected features.

This plan is ordered by compounding leverage. Each phase should leave behind a usable capability, tests, and at least one operator-visible surface.

## Principles

- Local-first by default: shared state should work on this machine without cloud dependencies.
- Auditable over magical: every proposal, critique, vote, and resolution should be inspectable.
- Memory with boundaries: store what helps, scrub what harms, and support forgetting.
- Safe autonomy: action flows need explicit scope, rollback, and policy-aware gates.
- Progressive federation: the single-node bot should still work well even if the full hive is partially offline.

## Phase 1: Hive Visibility and Control

Status: in progress

Goals:
- Surface hive state through CLI and API.
- Make node, bus, and bridge health visible from the main bot.
- Establish a stable operator vocabulary for threads, critiques, votes, and resolutions.

Shipped in this phase:
- `/hive` command for local hive status
- `/api/hive` endpoint
- Hive summary inside the cognitive system report

## Phase 2: First Consensus Loop

Status: shipped

Goals:
- Turn hive consensus into a usable feature from the main bot.
- Allow one proposal to trigger structured responses from role lanes.
- Persist the resulting thread to working memory and shared memory.

Capability:
- `/hive propose <idea>`
  - creates a thread
  - synthesizes role feedback from critic, architect, empath, and watcher lenses
  - casts votes
  - resolves to adopted, tabled, or needs more data
  - stores the thread outcome in hive memory

## Phase 5: Elysium — Persistent Distributed Frontal Lobe

Status: shipped — 2026-05-17

Goals:
- Transform the Hive into a true persistent distributed frontal lobe.
- Give DRIFT an explicit self-model (Nexus) that learns from every decision.
- Make Council members persistent identities with memory views and energy.

Shipped:
- `core/hive/elysium.py` — Nexus Loop engine
- `core/hive/nexus.py` — persistent self-model (goals, moral stance, narrative arc, tensions)
- `core/hive/council_member.py` — 7 persistent voices with fractal memory filters
- Commands: `/hive nexus decide <goal>`, `/hive reflect`, `/hive council status`
- Background reflection wired into consciousness loop
- Health check for Elysium coherence

## Phase 3: Memory Integrity Layer

Goals:
- Improve long-term reliability of hive memory.
- Add contradiction handling, validation, and retention classes.

Upgrades:
- Source-aware trust scoring
- Contradiction tagging between related memories
- Retention classes: ephemeral, durable, private, sanitized
- Forget/edit hooks from the main bot
- Better validator trails on shared memory entries

## Phase 4: Long-Horizon Planning

Goals:
- Let the hive carry goals across multiple turns and failures.
- Support milestones, progress tracking, and plan repair.

Upgrades:
- Goal threads in working memory
- Milestone objects with status transitions
- Failure classification and repair strategies
- Watcher-based disruption alerts

## Phase 5: Tool Orchestration Spine

Goals:
- Move from chat-centric reasoning to governed execution.
- Route high-risk actions through role-aware review.

Upgrades:
- Proposal types for tool execution, not just ideas
- Dry-run and rollback metadata
- Tool policy profiles by mode
- Shared action log across prompt, memory, and tool layers

## Phase 6: Personalization With Boundaries

Goals:
- Improve continuity without turning private context into permanent clutter.

Upgrades:
- Preference classes with expiry
- Sensitivity tags
- Explicit opt-in memory domains
- Local-first user model summaries

## Immediate Repo Backlog

1. Expose the first consensus loop in `commands.py` and the API.
2. Add tests for proposal, critique, watcher veto, and persistence behavior.
3. Add a lightweight thread summary view: `/hive thread <id>`.
4. Persist consensus outcomes with richer metadata for later retrieval.
5. Connect long-horizon goals to hive thread generation.

## Suggested Command Surface

- `/hive`
- `/hive propose <idea>`
- `/hive thread <thread_id>`
- `/hive stats`
- `/hive sync`

## Success Metric

The hive is worth keeping when it helps the main bot make better decisions than a single response would, and when the reasoning can be inspected afterward without guesswork.
