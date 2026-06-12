# INFJ Bot — upgrade backlog

Living list of improvements worth making, grouped by area. Reorder or check off as you go. **Suggested priority** is called out in each section (P0 = highest leverage).

---

## 1. Memory and retrieval

| Priority | Upgrade | Notes |
|----------|---------|--------|
| **P0** | **Semantic embeddings** | `LocalEmbeddingFunction` in `memory.py` is hash-bucket based; recall is weak for paraphrases and long-tail context. Options: Chroma default embedding, local model (e.g. sentence-transformers / Ollama embeddings API), or API embeddings — pick one path and version the collection name if dimensionality changes. |
| **P0** | **DMU & PEDI integration** | ✅ **Done** — `memory/dmu.py` re-ranks by time-decay + emotional weight; `metrics/pedi.py` tracks state fluidity across context resets (`PediIndex`). Both wired into `cognitive_orchestrator.py`. A second, distinct identity-anchor PEDI now lives at `core/pedi_metrics.py` (`PEDIEngine`) — see [VAULT_STABILITY_NOTES.md](VAULT_STABILITY_NOTES.md). |
| **P0** | **Hybrid search** | Combine dense retrieval with keyword / recency / importance (you already store rich metadata). Reduces “almost right” misses. |
| **P1** | **Memory lifecycle** | Summarize or prune old interactions; deduplicate near-duplicate facts; optional “pinned” memories vs ephemeral chat. |
| **P1** | **Contradiction handling** | When new memory conflicts with retrieved chunks, resolve or surface uncertainty in `memory_context_block` / guardrails. |
| **P1** | **Scrubbing precision** | `SECRET_PATTERNS` can redact benign hex/IDs or miss edge-case secrets. Tune patterns; consider allowlists for code-heavy users. |
| **P2** | **User-visible memory UX** | “What do you remember?” with citations, edit/forget controls, export — builds trust and fixes bad entries. |

---

## 2. Prompt assembly and context budget

| Priority | Upgrade | Notes |
|----------|---------|--------|
| ~~P0~~ | ~~Token budget + trimming~~ | ✅ **Done** — `PromptBudget` enforces tiered limits; `trim_to_budget()` drops context → analysis → cognitive sections progressively. DMU/PEDI telemetry added. |
| **P1** | **De-duplicate instructions** | Multiple modules may repeat “be reflective” / values language; consolidate to reduce contradictions and save tokens. |
| **P1** | **Debug / trace mode** | One flag to dump final prompt sections (redacted) to a file or structured log — essential for “why did it say that?” |
| **P2** | **Structured system blocks** | e.g. XML or markdown headings the model reliably respects; eases future caching if the API supports prefix caching. |

---

## 3. Models, inference, and cost

| Priority | Upgrade | Notes |
|----------|---------|--------|
| **P0** | **Critic policy** | Not every turn needs full critic pass; gate by mode, risk signals, or random sample to cut latency/cost. |
| **P1** | **Streaming + UX** | If not already consistent across CLI/web, align streaming so long replies feel responsive. |
| **P1** | **Fallback behavior** | `INFJ_USE_LOCAL_FALLBACK` + Ollama: document failure modes; graceful degradation when API quota/rate limits hit. |
| **P2** | **Model abstraction** | Thin provider interface (Gemini / OpenAI-compatible / local) reduces lock-in and simplifies experiments. |

---

## 4. Safety and alignment

| Priority | Upgrade | Notes |
|----------|---------|--------|
| **P1** | **Beyond keyword rails** | `guardrails.py` cyber lists are helpers, not guarantees; combine with critic, optional second-stage classifier, and periodic red-team prompt sets. |
| **P1** | **Tool-induced risk** | Model + tools = larger attack surface; keep risky tools off by default for new installs; review tool descriptions for injection. |
| **P2** | **Self-harm / crisis paths** | Clarity mode touches this; ensure consistent escalation copy and links across surfaces (web/CLI). |

---

## 5. Tools and automation

| Priority | Upgrade | Notes |
|----------|---------|--------|
| **P0** | **Capability tiers** | e.g. `read_only` / `developer` / `bughunter`: explicit env flags so strangers never get shell without opting in. |
| **P1** | **Integration tests for sandbox** | Automated tests that paths cannot escape `SAFE_HOME` / `PROJECT_ROOT` and blocklisted shell patterns are rejected. |
| **P1** | **Audit log review UX** | `tool_audit.jsonl` exists; add a small viewer or summary command for “what ran\" when debugging. |
| **P2** | **Timeouts and cancellation** | Ensure long-running tools can be cancelled from web/CLI without zombie processes. |

---

## 6. Product, multi-user, and compliance

| Priority | Upgrade | Notes |
|----------|---------|--------|
| **P1** | **Configurable identity** | “Jude” / `CREXS` is baked into prompts and `save_interaction` labels; move to config for white-label or pilots. |
| **P1** | **Data isolation** | Per-user Chroma path + SQLite (`being.db`, etc.) when moving beyond single-user. |
| **P2** | **Export / delete** | GDPR-style “delete my data” and portable export of memories + history. |
| **P2** | **Auth for web** | If `web_app.py` / `api.py` are exposed beyond localhost, add real auth (even basic) and HTTPS guidance. |

---

## 7. Testing and evaluation

| Priority | Upgrade | Notes |
|----------|---------|--------|
| **P0** | **Multi-turn eval set** | Curated dialogs (10–50): memory recall, mode switch, dissonance, refusal cases; rerun after prompt/memory changes. |
| **P1** | **Regression rubric** | Simple scoring (human or LLM-judge) for tone, grounding, boundary compliance. |
| **P1** | **CI scope** | Run unit tests without GPU/heavy deps; mark optional integration (Playwright, local LLM) separately. |
| **P2** | **Property tests** | Where logic is deterministic (path safety, scrubbing), add fuzz/property cases. |

---

## 8. Reliability and operations

| Priority | Upgrade | Notes |
|----------|---------|--------|
| **P1** | **Backup / migration** | Document backup of `chroma_db/`, `being.db`, `history.jsonl`, configs; scripted restore. |
| **P1** | **Structured logging** | Correlation id per session; log mode, model, critic on/off, retrieval counts — not full prompts by default. |
| **P2** | **Health checks** | Extend offline checks: Chroma readable, disk space, API key present, optional Ollama ping. |
| **P2** | **Dependency hygiene** | `requirements.txt` pins many packages; consider grouping prod vs dev vs optional `[bughunter]` extras to slim default install. |

---

## 9. Codebase and architecture

| Priority | Upgrade | Notes |
|----------|---------|--------|
| **P1** | **Singleton / init churn** | Many cognitive classes instantiated per message (`EmotionalField()`, `ValueSystem()`, etc.); if they load DBs, consider shared instances or explicit lifecycle to avoid redundant I/O. |
| **P2** | **Type hints + API contracts** | Tighten types on public functions; Pydantic models for tool I/O where helpful. |
| **P2** | **Package layout** | As the project grows, `src/drift/` layout or clear subpackages (`cognition/`, `infra/`) reduce circular imports. |

---

## 10. Companion experience (feel, not just features)

| Priority | Upgrade | Notes |
|----------|---------|--------|
| **P1** | **Pacing** | Background `consciousness_loop` is rich; tune frequencies so it feels thoughtful, not noisy (user preference knob). |
| **P2** | **Proactive messaging policy** | Clear rules for when the bot initiates vs stays quiet; respects “quiet” mode and time-of-day if you add it. |
| **P2** | **Voice & multimodal** | You already pull in whisper/TTS deps in places; unify one supported path or document what is experimental. |

---

## Suggested sequencing (if doing one track at a time)

1. **Track A — Smarter memory:** semantic embeddings + hybrid retrieval + scrub tuning.  
2. **Track B — Controllable context:** token budget, trimming, prompt trace mode.  
3. **Track C — Safer shipping:** tool tiers, sandbox tests, multi-turn eval set.  
4. **Track D — Pilots:** identity config, isolation, export/delete, web auth if needed.

---

*Last updated: 2026-05-03 — adjust priorities as your roadmap shifts.*
