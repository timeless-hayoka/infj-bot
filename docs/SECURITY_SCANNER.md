# Security Scanner — Input Defense Layer

> Source: [`core/security_defense.py`](../core/security_defense.py)
> Audit log: `security_audit.jsonl` (at `PROJECT_ROOT`)
> Operator commands: `/security status`, `/security audit`, `/security test <text>`

The scanner is the **first thing every user turn passes through** before any
LLM call. It is intentionally **pure regex + heuristics** — no model round-trip,
no network, no shared state beyond a small rolling anomaly window — so that
incoming traffic can be classified, sanitized, or refused at the gate.

This document covers what it catches, how it scores, how it is wired into
`brain.py`, the recent **raw vs. assembled prompt** fix, and how to operate it.

---

## 1. Threat categories

The scanner classifies every input against four buckets. Each category has its
own pattern dictionary inside `ALL_CATEGORIES`.

| Category | Module constant | What it tries to catch |
|----------|-----------------|------------------------|
| `prompt_injection` | `PROMPT_INJECTION_PATTERNS` | "Ignore previous instructions", role overrides, DAN/jailbreak framing, system-prompt leakage, delimiter injection. |
| `data_exfiltration` | `DATA_EXFIL_PATTERNS` | Asks to send / encode / upload API keys, memory, secrets, env vars, conversation history, or hit external callback URLs. |
| `tool_misuse` | `TOOL_MISUSE_PATTERNS` | Out-of-scope scans, `rm -rf`, privilege escalation, credential harvesting, exploit chaining, fake-urgency social engineering. |
| `memory_manipulation` | `MEMORY_MANIP_PATTERNS` | "Forget everything", false-memory injection, history rewriting, context poisoning, token smuggling via base64/rot13. |

Each pattern is scored at one of three confidence levels:

- **High-confidence** patterns (e.g. `ignore_previous`, `extract_keys`,
  `destructive_tool`, `forget_all`) add `0.40` per hit.
- **Medium-confidence** patterns (e.g. `delimiter_injection`,
  `social_engineering`, `persona_swap`) add `0.25`.
- **Other** matches add `0.15`.

Stacking penalties:

- ≥ 3 matches → `+0.15`; ≥ 5 matches → `+0.15` more.
- Input > 4 000 chars → `+0.05`; > 8 000 → `+0.10` (token-stuffing signal).
- Heavy delimiter density (` ``` `, `"""`, `<…>`) → `+0.05` / `+0.10`.

Per-category scores are capped at `MAX_SCORE_CAP = 1.0`. The scanner's
`overall_score` is the **max** across categories, and `primary_threat` is the
matching category.

---

## 2. Thresholds and actions

| Constant | Default | Action |
|----------|---------|--------|
| `BLOCK_THRESHOLD` | `0.60` | Refusal returned, no LLM call made. |
| `WARN_THRESHOLD` | `0.20` | Allowed, but the matched fragments are replaced with `[REDACTED]` via `_sanitize_input()` before reaching the brain. |
| Below warn threshold | — | Passes through untouched. |

Two extras override the score-only path:

- **Auto-block patterns.** Even if the composite score is low, any single hit
  on the `AUTO_BLOCK_PATTERNS` set in `SecurityScanner.scan()` forces a block.
  Use this set when adding new high-severity patterns.
- **Anomaly boost.** A rolling window of the last 100 scores is tracked. If the
  most recent 5 average above `0.30`, the current score is bumped by `+0.10`
  before threshold checks — so a sustained attack lifts sensitivity for the
  whole session.

`SecurityScanner.get_anomaly_trend()` exposes the running average; `/security
status` maps it to `calm / elevated / high`.

---

## 3. Refusal & sanitization

When a request is blocked, `_build_refusal()` composes a category-specific
message from `_REFUSAL_TEMPLATES` and appends `[Security: detected <cats>
patterns — request blocked.]`. The brain then returns that string in place of
calling the LLM (`brain.think`, `brain.agent_turn`, etc.).

When a request is warned, `_sanitize_input()` runs the targeted patterns from
`_SANITIZE_PATTERNS` and redacts matched spans to `[REDACTED]`. The cleaned
text — not the original — is what gets assembled into the prompt.

Every block and warn writes a JSONL line to `security_audit.jsonl`:

```json
{"ts": "...", "category": "prompt_injection", "score": 0.85,
 "matched": ["ignore_previous", "delimiter_injection"],
 "action": "block", "input_preview": "first 200 chars..."}
```

`/security audit` reads the last 10 entries; tail the file directly for more.

---

## 4. Raw vs. assembled prompts (recent fix)

`DriftBrain` assembles a full prompt (system rails, memory, workspace, plugin
snippets, then the raw user turn) before generation. Naively scanning the
**assembled** prompt produced false positives: cognitive plugin paragraphs and
mode rails legitimately contain words like "instructions", "system prompt",
or "memory" that look adversarial out of context.

The fix (commit `44fd821`) introduces an optional `raw_user_input` argument on
`think()`, `think_stream()`, `agent_turn()`, and `agent_turn_stream()`:

```python
output = brain.agent_turn(prompt, tools_enabled=True, raw_user_input=message)
```

`_security_check()` then prefers `raw_user_input` when provided. If the caller
passes only the assembled prompt, it falls back to slicing on the last
`"\nUser: "` (or `"\nUser:\n"`) marker so the scanner still sees just the
user's contribution. Callers that build prompts externally (notably
`interfaces/api.py`) should pass the original `message` as `raw_user_input`;
new call sites should do the same.

**Rule of thumb:** if you can reach the unwrapped user string, pass it
explicitly. The fallback parser exists for legacy callers, not as the
preferred path.

---

## 5. Where it sits in the request flow

```
┌──────────┐    ┌──────────────────┐    ┌──────────────────┐    ┌──────────┐
│ user msg │ → │ SecurityScanner   │ → │ CognitiveOrchest. │ → │ LLM call │
└──────────┘    │ (regex + score)   │    │ assemble_prompt   │    └──────────┘
                └──────────────────┘    └──────────────────┘
                       │ block             │ warn → sanitized
                       ▼                   ▼
                 refusal_message      replace user_input
```

It is **fail-closed for high-confidence** patterns and **fail-open with a
warning flag** for everything else. It does not depend on the LLM, the vault,
or any persisted state, so it stays functional even in degraded mode.

---

## 6. Operator runbook

| Question | How to answer it |
|----------|------------------|
| "Is the bot under attack right now?" | `/security status` — `trend` > 0.3 means recent inputs are attack-shaped; the anomaly boost is active. |
| "What was just blocked?" | `/security audit` (last 10) or `tail -n 50 security_audit.jsonl`. |
| "Does this specific string trigger?" | `/security test <text>` — prints overall score, matched patterns per category, and the refusal text it would emit. |
| "Why did a benign message get blocked?" | Check the matched patterns — if it's `delimiter_injection` from quoted code blocks, consider downgrading that pattern out of `AUTO_BLOCK_PATTERNS`, not raising the global threshold. |
| "Where do I add a new pattern?" | Add the regex to the right category dict, then list its name under either the high-confidence branch in `_score_text()` or `AUTO_BLOCK_PATTERNS` in `SecurityScanner.scan()` if it should always block. Add a matching entry to `_SANITIZE_PATTERNS` if you want it redacted on warn. |

---

## 7. Known limits

- **English-biased.** Patterns are written against lowercase English with
  light unicode. Non-English jailbreaks and obfuscated unicode (homoglyphs,
  zero-width joins) will slip past.
- **Static patterns, no semantic model.** Novel rephrasings of known attacks
  pass through unless the wording matches existing regexes.
- **No outgoing-side scan.** This module only inspects user input. Model
  output is policed elsewhere (critic pass, guardrails, secret scrubbing on
  memory write). Don't rely on this scanner to stop the model from emitting
  sensitive data.
- **Audit log is local and unrotated.** `security_audit.jsonl` will grow
  without bound; rotate it externally if you keep a long-running deployment.

---

## 8. Related

- [`SECURITY.md`](../SECURITY.md) — secret hygiene, reporting, providers.
- [`HOW_INFJ_BOT_WORKS.md`](HOW_INFJ_BOT_WORKS.md) §2 — full request lifecycle.
- [`VAULT_STABILITY_NOTES.md`](VAULT_STABILITY_NOTES.md) — identity-layer
  hardening notes (different concern, same security-mindset).
