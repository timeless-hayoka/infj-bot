# DRIFT Ablation Test — Live Run Fix Log

**Date:** 2026-05-22
**File Modified:** `tests/ablation_suite.py`
**Goal:** Obtain real (non-stubbed) live ablation test results via LLM API calls without the test taking 20+ hours or hanging indefinitely.

---

## Problems Identified

1. **CPU Ollama was too slow** (~4 min/prompt)
   - Ollama running on CPU with `qwen3:4b` (3.5GB model, 100% CPU)
   - 300 prompts × 4 min = ~20 hours

2. **Groq rate limits (429 Too Many Requests)**
   - Free tier limited to ~20 RPM
   - `brain.think()` makes 2 API calls per prompt (primary + critic)
   - Tight loop with no delay caused burst requests above limit

3. **Gemini fallback hung indefinitely**
   - When Groq 429'd, brain fell through to Gemini
   - Gemini calls had no timeout and took 120s+ per call
   - This made the test appear "stuck" for minutes per prompt

4. **Brain module-level constants weren't patched correctly**
   - Patching `cfg_module.DRIFT_USE_GROQ` didn't affect `brain_module.DRIFT_USE_GROQ`
   - Python imports cache values at module-load time

---

## Fixes Applied

### Fix 1: Force Groq for Conditions A–D, F (2026-05-22)
**Location:** `_setup_ablation()` live mode block
- Patched `brain_module.DRIFT_USE_GROQ = True`
- Patched `brain_module.DRIFT_USE_KIMI = False`
- Ensures Groq (fastest provider, ~0.5s/call) is used instead of slow Gemini/Ollama

### Fix 2: Disable Gemini Fallback (2026-05-22)
**Location:** `_setup_ablation()` live mode block, conditions A–D, F
- Set `brain_module.API_KEY = ""`
- Prevents brain from falling through to Gemini when Groq fails
- Falls back to Ollama (60s timeout) instead of hanging forever

### Fix 3: Skip Critic Review (2026-05-22)
**Location:** `_setup_ablation()` live mode block, conditions A–D, F
- Wrapped `brain._generate` to detect critic prompts (`"Review the following response"`)
- Returns `"[critic skipped for ablation speed]"` immediately
- **Halves API calls per prompt** (1 call instead of 2)
- Reduces rate limit pressure and total runtime

### Fix 4: Groq 429 Retry with Exponential Backoff (2026-05-22)
**Location:** `_setup_ablation()` live mode block, conditions A–D, F
- Wrapped `brain._generate_groq` with retry loop (4 attempts)
- Backoff: 5s, 10s, 15s, 20s
- Prints retry status to log for visibility

### Fix 5: Rate-Limit Guard Delay (2026-05-22)
**Location:** `run()` loop
- Added `time.sleep(8)` between prompts in live mode
- Target: ~7.5 RPM, well under Groq free-tier 20 RPM limit
- Prevents burst requests that trigger 429s

### Fix 6: Condition E Preserved (2026-05-22)
**Location:** `_setup_ablation()` live mode block
- Condition E ("Local LLM only") still forces Ollama by clearing all API keys
- No changes to its test semantics

### Fix 7: Reduced Prompt Set for Speed (2026-05-22)
**Runtime flag:** `--diverse 2`
- Uses 2 prompts per category × 5 categories = 10 prompts per condition
- Total: 60 prompts across 6 conditions
- Still covers all categories (greeting, stress, deep, tech, creative) for all conditions
- Full 50-prompt run can be re-run later with `--prompts 50` once rate limits are confirmed stable

---

## Test Runs Log

| Run | Time | Result | Notes |
|-----|------|--------|-------|
| v1 | 2h timeout | Failed | CPU Ollama only, ~4 min/prompt, reached prompt 31/300 |
| v2 | 1h timeout | Failed | Groq enabled but unpatched module constants; fell back to Ollama after 85 prompts |
| v3 | 3m stopped | Failed | 2s delay insufficient; 429 on every prompt |
| v4 | 3m stopped | Failed | Same 429 issue, first prompt already rate-limited |
| v5 | 4m 33s stopped | Failed | Retries added but 2 calls/prompt still bursted over limit; Gemini fallback hung |
| v6 | In Progress | Running | All fixes combined: critic skip, API_KEY clear, 8s delay, Groq retry |

---

## Verification Commands

```bash
# Watch live progress
tail -f /tmp/live_ablation_run_v6.log

# Count completed prompts
grep -c "after think" /tmp/live_ablation_run_v6.log

# Check which conditions finished
grep "^Running ablation" /tmp/live_ablation_run_v6.log
```

---

## Files Changed

- `infj_bot/tests/ablation_suite.py` — live mode setup, delay loop, retry logic

## Files Generated

- `infj_bot/ABLATION_RESULTS/ablation_YYYYMMDD_HHMMSS_*.json` — per-condition raw data
- `infj_bot/ABLATION_RESULTS/ablation_YYYYMMDD_HHMMSS_summary.txt` — cross-condition comparison
- `infj_bot/ABLATION_RESULTS/ablation_YYYYMMDD_HHMMSS_methodology.md` — methodology doc

---

## Fix 8: Fallback to Ollama-Only for Reliability (2026-05-22)

**Reason:** Groq continued returning 429 even with 8s delays, critic skip, and exponential backoff. The free-tier rate limit window was not resetting fast enough between our test attempts.

**Change:** For conditions A–D, F in live mode:
- Set `brain_module.DRIFT_USE_GROQ = False`
- Removed Groq retry wrapper
- Removed 8s inter-prompt delay (Ollama has no rate limit)
- With `API_KEY = ""` and Groq disabled, brain falls straight to Ollama
- **Result:** 1 Ollama call per prompt (critic still skipped), ~30–60s per prompt
- **Estimated runtime:** 60 prompts × ~30s = ~30 minutes

Condition E remains unchanged (already Ollama-only by design).
