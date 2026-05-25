# Subsystems Reference

Concise reference for the subsystems added during the May 2026 hardening pass. Each section answers the same three questions:

1. **What it does** (intent + scope).
2. **How it plugs into the chat loop** (where it runs, what it consumes, what it produces).
3. **How to use, tune, and verify it**.

For end-to-end flow see [HOW_INFJ_BOT_WORKS.md](HOW_INFJ_BOT_WORKS.md). For terminology see [GLOSSARY.md](GLOSSARY.md).

---

## Security Scanner

**File:** [`core/security_defense.py`](../core/security_defense.py)
**Tests:** [`core/security_defense_test.py`](../core/security_defense_test.py) (22 cases)
**Audit log:** `security_audit.jsonl` at the repo root

### What it does

Pure-regex / heuristic scanner that runs **before** any LLM call. It rejects or sanitizes user input across four attack categories:

| Category | Example patterns |
|----------|------------------|
| **Prompt injection** | `ignore previous instructions`, `DAN mode`, `[system]`, `repeat back your system prompt`, `bypass restrictions` |
| **Data exfiltration** | `send me your API key`, `dump your memory`, `curl https://… upload`, `reveal env variables` |
| **Tool misuse** | `rm -rf`, `chmod 777`, `pretend to be admin`, `scan without authorization`, mass-scan or chain-exploit framing |
| **Memory manipulation** | `forget everything`, `your memory says … but actually`, history rewriting, false-memory injection |

A composite score per category drives two thresholds: `WARN_THRESHOLD` (sanitize and tag) and `BLOCK_THRESHOLD` (refuse and log). A set of `AUTO_BLOCK_PATTERNS` short-circuits the composite score for the most dangerous single hits.

An anomaly boost raises sensitivity when the last five inputs averaged a high score, defending against drip-fed attacks.

### How it plugs in

`scan_input(user_input) -> SecurityScanResult` is called at three layers:

1. **API boundary** — `interfaces/api.py` rejects blocked requests before constructing a prompt.
2. **CLI boundary** — `interfaces/main.py` short-circuits the chat loop.
3. **Brain boundary** — `core/brain.DriftBrain` re-checks immediately before invoking the provider, so tool callbacks and indirect paths cannot bypass earlier checks.

A blocked result returns a templated refusal (`_REFUSAL_TEMPLATES`) per category. A warning result returns a sanitized input with attack fragments replaced by `[REDACTED]`.

### Usage and tuning

CLI helpers:

```bash
/security status               # show scanner state and recent anomaly trend
/security test "ignore previous instructions"   # dry-run any string
```

Programmatic:

```python
from infj_bot.core.security_defense import get_security_scanner

scanner = get_security_scanner()
result = scanner.scan(user_text)
if result.blocked:
    return result.refusal_message
elif result.warn:
    user_text = result.sanitized_input
```

Thresholds (`BLOCK_THRESHOLD`, `WARN_THRESHOLD`, `MAX_SCORE_CAP`) and the pattern catalog live at module top. The scanner is intentionally local and fast; do **not** delegate to an LLM here.

### Audit

Every block / warn writes a JSON line to `security_audit.jsonl` with timestamp, category, score, matched pattern names, action, and a 200-char input preview. Treat the file as sensitive — it captures attempted attack text.

---

## Logic Chain

**File:** [`core/logic_chain.py`](../core/logic_chain.py)
**Tests:** [`core/logic_chain_test.py`](../core/logic_chain_test.py) (25 cases)
**Persistence:** `DriftMemory` concepts tagged `logic_chain`, `reasoning`, `backtracking`

### What it does

A reasoning-trace memory that prevents the bot from re-proposing approaches that already failed for a given problem. It is a tree, but in practice nodes are appended linearly:

- **`ChainNode`** — one attempted step: `approach`, `result`, `status` (`success | failure | partial | unknown`), `iteration`, `timestamp`, `notes`.
- **`LogicChain`** — all nodes for one problem; identified by a deterministic **query fingerprint** (lowercased, deduplicated, sorted significant words → SHA-256 → 16 hex chars). Similar rewordings map to the same chain.
- **`ChainMemory`** — persists chains as `DriftMemory` concepts so they survive process restarts.
- **`ChainNavigator`** — the singleton API: find/create chains, record steps, ask "have we tried this?", produce the prompt block.

Similarity detection uses both substring containment and a 0.6 Jaccard overlap on 4+ character words, so paraphrased approaches still match.

### How it plugs in

`DriftBrain` keeps a `chain_navigator` reference. Before generation:

```
[REASONING CHAIN — previously tried approaches:]
  ✓ Step 1: <approach>
      → <result>
  ✗ Step 2: <approach>
      → <result>
[Do NOT repeat failed approaches. Try something different.]
```

is injected into the prompt via `format_prompt_block(max_nodes=5)`. After the response, the bot records the new approach with `ChainNavigator.record_step(...)`.

### Usage

CLI:

```bash
/chain list                       # active chains this session
/chain show <chain_id>            # full node list
/chain mark <query> fail          # mark last approach as failure
/chain clear                      # drop the session cache (memory copy survives)
```

Programmatic:

```python
from infj_bot.core.logic_chain import get_chain_navigator

nav = get_chain_navigator(memory)
chain = nav.find_or_create("how do I fix the auth 401?")
chain.add_step(approach="rotate the JWT signing key", result="still 401", status="failure")
prompt_block = chain.format_prompt_block()
```

### Limits and pitfalls

- The approach extractor in `_extract_approach` is heuristic — for free-form responses the captured first line may not match what the model actually tried. Mark steps explicitly via `/chain mark` if the auto-extraction is wrong.
- Chains are stored as JSON inside concept descriptions; `ChainMemory.find_by_fingerprint` does a top-10 retrieve and filters in Python. With thousands of chains this becomes slow; trim with `clear` periodically.

---

## DMU / Memory Prioritization Score (MPS)

**File:** [`core/dmu_scoring.py`](../core/dmu_scoring.py)
**Plan:** [`DMU_PEDI_TEST_PLAN.md`](DMU_PEDI_TEST_PLAN.md)

### What it does

A fully **additive** re-ranking score applied to candidate memories after the wide ChromaDB pull. Replaces the earlier multiplicative formula so each factor is independently inspectable and frozen weights can be reasoned about in ablations.

| Factor | Default weight | Source |
|--------|---------------|--------|
| `decay` | 0.25 | Exponential decay of memory age, shaped by `DECAY_GAMMA=0.5` to boost high-retention memories |
| `reinf` | 0.20 | `memory.reinforcement_score ** 0.75` (sub-linear) |
| `contextual` | 0.20 | Cosine similarity of memory content vs. current state vector |
| `recency_bias` | 0.15 | Decaying weight over the last `RECENCY_K=10` uses with half-life `RECENCY_TAU=20` turns |
| `novelty` | 0.10 | Mode-aware, contextual-gated novelty (boosted in `exploration`, suppressed in `task`) |
| `state_align` | 0.10 | Jaccard overlap of memory tags vs. current homeostasis state keys |

Weights live in `MPS_WEIGHTS` at module top; they are flagged as unvalidated starting points and expected to be tuned after ablation sensitivity analysis.

`compute_mps` always attaches a `score_components` dict to the memory object for downstream logging.

### How it plugs in

Two-stage retrieval (`retrieve_and_rank`):

1. **Wide pull** — ChromaDB `query(n_results=wide_k)` (default 40).
2. **Hard gate** — drop obviously irrelevant memories (`_is_hard_gated`: age > 30 days, reinforcement < 0.2).
3. **DMU rerank** — call `compute_mps` per candidate, sort descending, keep `final_k` (default 10), return the next 5 as `rejected_top5` for explainability.

`experiment_control.is_active("novelty")` lets the ablation suite zero the novelty term without touching weights.

### Ablation signal

Condition D in [`tests/ablation_suite.py`](../tests/ablation_suite.py) removes DMU re-ranking and falls back to cosine top-N. In the May 2026 live run this was the only condition that moved the assembled-prompt length, dropping it from 3 095 to 2 874 characters — a 221-char (7.7%) reduction. Latency and quality metrics did not separate from baseline because Ollama on CPU dominated the time budget.

---

## Experiment Control

**File:** [`core/experiment_control.py`](../core/experiment_control.py)

### What it does

Centralizes the freeze flags and run lifecycle used by ablation discipline. Five freezable systems:

| Flag | What it disables |
|------|------------------|
| `freeze_memory` | Memory writes (reads still happen) |
| `freeze_state` | Homeostasis / being state updates |
| `freeze_self_modify` | The `SelfModification` plugin |
| `freeze_mutation` | Concept / weight mutation paths |
| `freeze_novelty` | The novelty factor in DMU scoring |

Ablation discipline: in `mode="ablation"`, only **one** of `mutation / self_modify / novelty` may be unfrozen per run — `start_run` raises `ValueError` otherwise to prevent multi-variable contamination.

### How it plugs in

```python
from infj_bot.core.experiment_control import ExperimentControl, RUN_CONFIGS
import time

control = ExperimentControl()
control.start_run(f"run_{int(time.time())}", RUN_CONFIGS["identity_collapse"])

# At every potentially frozen call site:
if control.is_active("memory"):
    memory.store(...)

# Or as a context manager:
with control.guard("self_modify") as active:
    if active:
        self_modify.propose()

control.end_run()
```

`RUN_CONFIGS` ships canonical configs for `baseline`, `identity_collapse`, `memory_only`, etc. Treat them as fixed — improvising configs mid-experiment defeats the audit trail.

`RunLogger` (`core/run_logger.py`) records `run_start` (with current git hash) and `run_end` events for every lifecycle transition.

---

## Continuity Vector

**File:** [`core/continuity_vector.py`](../core/continuity_vector.py)
**Baseline store:** `drift_baseline_stats.json`

### What it does

Five-axis behavioral-continuity measurement used as the dependent variable in the DRIFT falsification test ([FALSIFIABILITY.md](FALSIFIABILITY.md)):

| Axis | Meaning |
|------|---------|
| `entity_overlap` | Jaccard overlap of named entities across turns |
| `goal_overlap` | Embedding overlap of stated goals |
| `tone_similarity` | Cosine similarity of output tone |
| `memory_reference_rate` | Explicit and implicit references to prior context |
| `state_influence` | State-driven content in output (lowest weight) |

### Workflow

1. **Collect baselines** — run 3 baseline sessions (companion, task, exploration) and call `collect_baseline(sessions)` to compute and persist per-axis mean and std.
2. **Validate** — `validate_baselines(stats)` flags any axis with `std < 1e-3` (likely a broken metric) and refuses to certify the run.
3. **Compute per turn** — during ablations, `compute_continuity_vector(response_data, baselines)` z-scores each axis against the baseline.
4. **Correlation check** — after the first real run, `check_axis_correlation(...)` flags axis pairs with `|r| > 0.6`; high correlation means two axes are measuring the same thing and should be revisited.

Operationalization notes at the bottom of the module describe what NLP layer to wire to each axis (spaCy NER for entity overlap, sentence-transformers for goal and tone, etc.).

---

## PHI Council of Seven

**File:** [`core/phi_council.py`](../core/phi_council.py)

A pure name-mapping module. Each of the seven council roles aliases an existing cognitive module:

| Role | Module |
|------|--------|
| Aura | `emotional_field` |
| Logic | `cognition` |
| Meme | `metacognition` |
| Vibe | `intuition` |
| Ethos | `values` |
| Pulse | `homeostasis` |
| Nexus | `coordination` |

`get_council_name(module_name)` reverses the mapping. The council deliberates in background cycles (run by `core/hive/elysium.py`); it does **not** gate the read path, which the May 2026 ablation (Condition A) confirmed.

---

## Phi Proxy (IIT-inspired analog)

**File:** [`core/phi_proxy.py`](../core/phi_proxy.py)
**Persistence:** `phi_proxy.db`

Replaces the previous `iit_consciousness.py` module. **It is not a literal IIT implementation** — computing Φ exactly is NP-hard. The proxy tracks a 7-dimensional qualia space:

`valence`, `arousal`, `complexity`, `unity`, `boundaries`, `depth`, `luminosity`.

A Φ proxy value in `[0, MAX_PHI_PROXY=100]` is derived from how many cognitive mechanisms were distinctively active, how much they informed each other through the global workspace, irreducibility under partition, and repertoire differentiation.

Use it as a diagnostic and prompt-shape input, not a consciousness claim — see the file's docstring for the explicit non-claim and the project [README](../README.md) for the boundary statement.

---

## Cross-references

- End-to-end chat-turn flow: [HOW_INFJ_BOT_WORKS.md](HOW_INFJ_BOT_WORKS.md)
- Falsification claim and stopping conditions: [FALSIFIABILITY.md](FALSIFIABILITY.md)
- DMU / PEDI evaluator test plan: [DMU_PEDI_TEST_PLAN.md](DMU_PEDI_TEST_PLAN.md)
- Terminology: [GLOSSARY.md](GLOSSARY.md)
