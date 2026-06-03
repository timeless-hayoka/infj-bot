# DRIFT Progress Report — May 2026

**Prepared for:** Claude (paper-writing assistant)  
**Date:** 2026-05-22  
**Project:** DRIFT — Distributed Response & Integrated Functional Thought  
**Codebase:** ~18,500 lines Python across 55 core modules  
**Repo:** `github.com/timeless-hayoka/infj-bot`

---

## 1. What DRIFT Is

DRIFT is a **unified cognitive architecture** for a local AI companion bot. Instead of treating the LLM as a black box that "just answers," DRIFT builds a full-stack agent with:

- **Emotional state** (homeostasis needs, mood, energy, attachment)
- **Episodic memory** (ChromaDB vector store + SQLite metadata)
- **Shadow processing** (unconscious pattern detection, suppressed topics)
- **Global workspace** (conscious attention, salience scoring)
- **Metacognition** (self-evaluation, confidence scoring)
- **Reasoning traces** (logic chains that persist across turns)
- **Security defense** (prompt injection scanning, input sanitization)

The core thesis: *Distinct behavior comes from what is assembled into the prompt, what is retrieved from memory, and what structured state is updated before and after each turn.*

---

## 2. Architecture (Five-Layer Map)

| Layer | Key Modules | Purpose |
|-------|-------------|---------|
| **Interface** | `api.py`, `main.py`, `web_app.py`, `cli.py` | REST API (port 8765), CLI chat loop, Web UI |
| **Orchestration** | `cognitive_orchestrator.py`, `brain.py` | Prompt assembly, LLM routing (Gemini → Groq → Kimi → Ollama), tool execution |
| **Cognition** | `being.py`, `homeostasis.py`, `shadow.py`, `global_workspace.py`, `metacognition.py` | State modeling, needs, suppression, conscious awareness, self-reflection |
| **Memory** | `memory.py`, `unified_memory.py`, `logic_chain.py`, `embeddings.py` | Semantic + episodic recall, reasoning traces, 384-dim sentence-transformer embeddings |
| **Safety** | `security_defense.py`, `guardrails.py` | Input scanning, scope enforcement, secret scrubbing, 4 attack-class detection |

**LLM Routing:** Security Scan → Prompt Assembly → Gemini (primary) → Groq/Kimi (fallback) → Ollama `qwen3:4b` (offline, CPU)

---

## 3. Recent Major Features (May 2026)

### 3.1 Security Defense Layer
- Pre-generation scanner guards against 4 attack classes:
  - Prompt injection (role overrides, DAN mode, delimiter tricks)
  - Data exfiltration (API key extraction, memory dumps)
  - Tool misuse (unauthorized scans, destructive commands)
  - Memory manipulation (false memory injection, context poisoning)
- Scans at API boundary, CLI boundary, and pre-generation
- JSONL audit log: `security_audit.jsonl`
- **22/22 tests passing**

### 3.2 Logic Chain — Reasoning Trace System
- Query fingerprinting: similar questions match the same chain
- Approach tracking: each step records strategy, result, status
- Semantic overlap detection: catches reworded dead-end approaches
- Prompt injection: `[REASONING CHAIN]` blocks show previous attempts to the LLM
- Persistence across sessions via `DriftMemory`
- **25/25 tests passing**

### 3.3 Ablation Test Suite (6 Conditions)
A formal test harness that measures the impact of removing/replacing each cognitive subsystem:

| ID | Condition | What Was Changed |
|----|-----------|------------------|
| A | No Council | Elysium/Phi Council stubbed to no-op |
| B | No Shadow | Shadow background tick disabled |
| C | No Homeostasis | Homeostasis cycle disabled, needs flattened to 0.5 |
| D | Cosine-only RAG | DMU re-ranking removed (simple cosine recall) |
| E | Local LLM only | All cloud providers disabled, Ollama forced |
| F | Full Stack | Baseline — no modifications |

**Metrics collected per condition:** latency, fallback rate, completion rate, coherence (0–1 heuristic), sycophancy rate, formal/chill marker rates, emotion drift, token estimates, prompt structure analysis.

---

## 4. Current Testing Status (Live)

**As of 2026-05-22 17:30:**
- A **live ablation run** is in progress using real Ollama `qwen3:4b` inference on CPU
- 22/60 prompts completed (Conditions A ✓, B ✓, now on Condition C)
- Runtime: ~30 minutes so far; estimated total: ~70–90 minutes
- Prompt set: `--diverse 2` (2 prompts per category × 5 categories = 10 per condition)
- Categories covered: greeting, stress, deep/philosophical, tech/bug-bounty, creative

**Why Ollama and not cloud?** Groq free-tier rate limits (20 RPM) blocked sustained testing. Gemini fallback calls hung indefinitely (>120s) with no timeout. Ollama on CPU is slow (~30–75s/prompt) but reliable and unlimited.

**Critic loop is skipped** during ablation to halve API calls — this is logged as a methodology choice.

**Fix log maintained at:** `ABLATION_RESULTS/ABLATION_FIX_LOG.md`

---

## 5. Memory & Knowledge Base

### 5.1 Unified Memory Spine
- **Episodic:** SQLite + ChromaDB (`infj_unified_memory` collection)
- **Document RAG:** ChromaDB (`infj_documents` collection)
- **Embeddings:** `sentence-transformers/all-MiniLM-L6-v2` (384-dim, CPU)
- **Chunking:** 800-char paragraphs with 100-char overlap

### 5.2 Recent Ingestion: Obsidian Vault Library
On 2026-05-22, the bot ingested **9 full books** from the user's Obsidian vault:

| Book | Author | Chunks |
|------|--------|--------|
| The Republic | Plato | 1,318 |
| Critique of Pure Reason | Kant | 1,227 |
| Frankenstein | Shelley | 600 |
| The Art of War | Sunzi | 450 |
| Kynällä ja kiväärillä | Railo | 431 |
| Alice's Adventures in Wonderland | Carroll | 264 |
| The Life of Flavius Josephus | Josephus | 135 |
| The Mirror of Literature, Vol. 19 | Various | 119 |
| Main Street, and Other Poems | Kilmer | 90 |

**Total:** 4,634 chunks now queryable via `/docs <query>` or automatic RAG retrieval.

---

## 6. Technical Challenges & Solutions

| Challenge | Solution |
|-----------|----------|
| **CPU Ollama too slow** (~4 min/prompt) | Critic skip + model keepalive reduced to ~30–75s/prompt |
| **Groq 429 rate limits** | Added exponential backoff retry; eventually fell back to Ollama-only for reliability |
| **Gemini fallback hung forever** | Patched ablation suite to set `API_KEY = ""` — forces Ollama fallback instead of Gemini |
| **Brain module constants not patching** | Learned that `from config import X` caches values at import time; must patch `brain_module.X` directly |
| **Ollama model unloading** | Model auto-unloads after 5 min idle; first prompt after idle takes extra load time |

---

## 7. Scale & Performance

- **Core codebase:** 18,471 lines Python (55 modules in `core/`)
- **Tests:** 285+ unit tests passing (security, logic chain, stress, temporal, metacognition, PEDI, etc.)
- **Memory collections:** `infj_unified_memory` (episodic), `infj_documents` (RAG)
- **Embedding model:** all-MiniLM-L6-v2 (local, no API dependency)
- **Local LLM:** qwen3:4b (2.5GB quantized, 3.5GB loaded, CPU-bound)
- **API server:** FastAPI on port 8765

---

## 8. Open Questions / Next Steps

1. **GPU acceleration** — Ollama inference is CPU-bound. A GPU would cut latency from ~60s to ~2–5s per prompt, enabling full 300-prompt ablations in minutes.
2. **Groq rate-limit handling** — Need token-bucket rate limiting or paid-tier upgrade for sustained cloud testing.
3. **Live ablation completion** — Awaiting the current Ollama-only run to finish; will generate comparative charts and update README.
4. **Continuity vector validation** — `continuity_vector.py` and `experiment_control.py` exist but need baseline data collection before memory-ablation tests (identity collapse, scrambled memory) can run.
5. **Paper metrics** — Need to quantify: emotional drift variance, memory relevance scores, council/shadow/homeostasis impact on response quality (human evaluation or automated rubric).

---

## 9. Files to Reference

- `README.md` — public-facing overview with architecture diagrams
- `ABLATION_RESULTS/ABLATION_FIX_LOG.md` — full engineering log of test fixes
- `docs/HOW_INFJ_BOT_WORKS.md` — internal mechanics
- `docs/GLOSSARY.md` — terminology
- `tests/ablation_suite.py` — test harness source
- `core/brain.py` — LLM routing + generation pipeline
- `core/cognitive_orchestrator.py` — prompt assembly
- `core/security_defense.py` — input scanning
- `core/logic_chain.py` — reasoning traces

---

*Report compiled by Kimi Code CLI on 2026-05-22. Live ablation test v7 is running in background (task: `bash-uzs3gbbz`).*
