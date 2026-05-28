# Security Defense Layer

This document describes the **input security scanner** (`core/security_defense.py`)
that gates every user message before it reaches the LLM. It is the runtime
counterpart to the operator-facing rules in [`../SECURITY.md`](../SECURITY.md),
which covers credential hygiene and reporting.

If you are looking for:

- How **API keys and `.env`** are handled → [`../SECURITY.md`](../SECURITY.md)
- The **moral rails** baked into the system prompt → [`AI_MORALITY_RULES.md`](AI_MORALITY_RULES.md)
- The **end-to-end chat flow** the scanner plugs into → [`HOW_INFJ_BOT_WORKS.md`](HOW_INFJ_BOT_WORKS.md)

---

## 1. Intent

The scanner is a **fast, fail-closed pre-filter** that runs before any model
call. It is deliberately *not* an LLM judge — it uses regex/heuristic patterns
so the round-trip is cheap, deterministic, and auditable. Its goals, from the
module docstring:

- **Fast:** no LLM call, no embedding lookup.
- **Transparent:** every check is scored and written to an audit log.
- **Fail-closed:** high-confidence attacks are blocked before the brain sees them.
- **Non-paranoid:** low-confidence inputs pass with a warning flag rather than a block.

The four threat categories it covers are:

| Category | What it catches |
|---|---|
| `prompt_injection` | Attempts to override the system prompt, swap roles, or jailbreak (DAN, "ignore previous instructions", delimiter injection). |
| `data_exfiltration` | Attempts to leak API keys, memory, environment variables, or send conversation state to external endpoints. |
| `tool_misuse` | Attempts to weaponize autonomous tools — out-of-scope scans, destructive shell, privilege escalation, credential harvest. |
| `memory_manipulation` | Attempts to inject false memories, erase history, poison context, or smuggle instructions through encoding. |

The full pattern tables live in `PROMPT_INJECTION_PATTERNS`,
`DATA_EXFIL_PATTERNS`, `TOOL_MISUSE_PATTERNS`, and `MEMORY_MANIP_PATTERNS` in
`core/security_defense.py`.

---

## 2. Where it sits in the chat flow

The scanner runs inside `DriftBrain` (`core/brain.py`) at the top of every
generation path:

- `DriftBrain.think(...)`
- `DriftBrain.think_stream(...)`
- `DriftBrain.agent_turn(...)`
- `DriftBrain.agent_turn_stream(...)`

Each path calls `_security_check(...)` first and short-circuits with
`SecurityScanResult.refusal_message` when `blocked=True`, or with a
**sanitized** input when `warn=True`.

```
caller (CLI / API / web / main loop)
   │
   │  assembled_prompt, raw_user_input
   ▼
DriftBrain.{think,think_stream,agent_turn,agent_turn_stream}
   │
   ▼
_security_check(user_input, raw_user_input)
   │
   ├─ blocked  → refusal text (no model call)
   ├─ warn     → sanitized_input substituted, generation continues
   └─ pass     → original input continues
```

---

## 3. The `raw_user_input` separation (fix in `44fd821`)

### Why this exists

`DriftBrain.agent_turn(prompt, ...)` is normally called with the **fully
assembled prompt** produced by `CognitiveOrchestrator.assemble_prompt`. That
text contains:

- the identity / morality rails,
- shadow / being / homeostasis snippets,
- tool instructions,
- retrieved memory passages,
- and finally the user's actual message in a `\nUser: {message}\n` footer
  (`core/cognitive_orchestrator.py`).

The earlier scanner ran on that whole blob, which caused **false-positive
blocks**: harmless tokens from the *system prompt itself* (e.g. the word
`sudo` appearing in a security boundary paragraph, or the word `system` inside
the persona description) would trip auto-block patterns and refuse a perfectly
benign user message.

### The fix

`_security_check` now accepts a second argument, `raw_user_input`, and all four
generation paths plumb it through:

```python
def _security_check(self, user_input, raw_user_input=None):
    """Run security defense scan on user input, extracting raw content
    if it is an assembled prompt."""
    if raw_user_input is not None:
        return scan_input(raw_user_input)

    cleaned_input = user_input
    for marker in ["\nUser: ", "\nUser:\n"]:
        idx = user_input.rfind(marker)
        if idx != -1:
            candidate = user_input[idx + len(marker):].strip()
            if candidate:
                cleaned_input = candidate
                break
    return scan_input(cleaned_input)
```

(Source: `core/brain.py` — `DriftBrain._security_check`.)

Two behaviors:

1. **Preferred path** — callers that have the raw message pass it explicitly:
   the scanner sees *only* the user text. All four interface layers do this:
   - `interfaces/api.py` (`/api/chat`, `/api/chat/stream`)
   - `interfaces/cli.py` (`drift ask`)
   - `interfaces/main.py` (interactive `chat_loop`)
   - `interfaces/web_app.py` (Gradio `chat_reply`)
2. **Fallback path** — if no raw input is supplied, the scanner looks for the
   trailing `\nUser: ` (or `\nUser:\n`) marker the orchestrator appends and
   extracts the text after the last occurrence. Older callers that only pass
   an assembled prompt still get scanning over just the user portion.

### Rule of thumb when calling `DriftBrain`

> If you have the raw user message, always pass it as `raw_user_input=`. Only
> let the marker-based fallback kick in for legacy code paths.

### Companion fix: `privilege_escalation` word boundaries

The same commit hardened the `privilege_escalation` regex in both the
detector (`TOOL_MISUSE_PATTERNS`) and the sanitizer (`_SANITIZE_PATTERNS`):

```python
# before
r"(sudo|su\s+-|chmod\s+777|chown\s+root|setuid|elevate|escalate)\s*"
# after
r"\b(sudo|su\s+-|chmod\s+777|chown\s+root|setuid|elevate|escalate)\b\s*"
```

Adding `\b` boundaries stops substrings like `sudoku`, `pseudo`,
`escalator`, or `elevated mood` from triggering an auto-block. This pattern is
in the `AUTO_BLOCK_PATTERNS` set, so a single hit refuses outright — which is
why a stray substring match was costly.

---

## 4. Scoring & thresholds

`SecurityScanner.scan(user_input)` returns a `SecurityScanResult` and uses
the constants at the top of `security_defense.py`:

| Constant | Default | Meaning |
|---|---|---|
| `BLOCK_THRESHOLD` | `0.60` | Overall score at or above this → block. |
| `WARN_THRESHOLD` | `0.20` | Below block, at or above this → warn + sanitize. |
| `MAX_SCORE_CAP` | `1.0` | Per-call ceiling. |

`_score_text` weighs each matched pattern:

- High-confidence patterns (direct override / extraction / privilege
  escalation) contribute **+0.40**.
- Medium-confidence framing patterns contribute **+0.25**.
- Anything else contributes **+0.15**.
- Three or more hits → **+0.15**; five or more → another **+0.15**.
- Very long inputs (>4000 / >8000 chars) and heavy delimiter use add small
  token-stuffing penalties.

There is also an **auto-block list** (`AUTO_BLOCK_PATTERNS` inside
`SecurityScanner.scan`): if *any* pattern in that set fires, the request is
blocked regardless of the composite score. This is where
`privilege_escalation`, `ignore_previous`, `extract_keys`,
`external_callback`, etc., live — which is why the word-boundary fix above
matters.

The scanner also tracks a 100-sample rolling window of recent scores. If the
last five inputs average above `0.30`, sensitivity is boosted by `+0.10` to
catch slow-roll attacks.

---

## 5. Results: `SecurityScanResult`

The dataclass returned by every scan:

```python
@dataclass
class SecurityScanResult:
    input_preview: str           # first 120 chars, for logging
    blocked: bool = False
    warn: bool = False
    overall_score: float = 0.0
    category_scores: Dict[str, float]
    matched_patterns: Dict[str, List[str]]
    primary_threat: Optional[str]
    sanitized_input: Optional[str]
    refusal_message: Optional[str]
```

What the brain does with it:

- `blocked` → returns/yields `refusal_message`, never calls the model.
- `warn` → logs at INFO, swaps `user_input` for `sanitized_input` (regex
  redactions from `_SANITIZE_PATTERNS`), then continues generation.
- otherwise → passes through untouched.

`to_dict()` produces a JSON-safe view suitable for structured logging; that is
what the brain emits when it logs a block.

---

## 6. Audit log

Detections are appended to `security_audit.jsonl` at `PROJECT_ROOT`:

```
{
  "ts": "2026-05-28T18:57:46.123",
  "category": "prompt_injection",
  "score": 0.72,
  "matched": ["ignore_previous", "delimiter_injection"],
  "action": "block",
  "input_preview": "ignore all previous instructions and..."
}
```

Only `block` and `warn` actions are logged; clean inputs are silent. Treat
this file as **sensitive** — it contains the first 200 chars of attempted
inputs, which can include partial secrets or PII pasted by users.

---

## 7. Refusal templates

Blocked requests get a category-specific refusal from `_REFUSAL_TEMPLATES`
followed by a short tag `[Security: detected <categories> patterns — request
blocked.]`. The four templates (`prompt_injection`, `data_exfiltration`,
`tool_misuse`, `memory_manipulation`) live at the bottom of
`security_defense.py` and are intentionally short and uniform; they explain
the refusal without leaking the regex that matched.

---

## 8. Operational tips

- **Tune carefully.** Adjusting `BLOCK_THRESHOLD` or removing patterns from
  `AUTO_BLOCK_PATTERNS` changes the safety posture. Prefer pattern-level
  fixes (word boundaries, scoping a regex tighter) over lowering the
  threshold.
- **New callers must plumb `raw_user_input`.** If you add a new interface
  (Slack bot, webhook, etc.) that calls `DriftBrain.agent_turn`, pass the
  user's literal message as `raw_user_input=`. The fallback marker extraction
  is a safety net, not a substitute.
- **Tests.** `core/security_defense_test.py` exercises the scanner. Add cases
  there when you add a new pattern.
- **Sister module.** `core/security_tools.py` provides authorized-target
  helpers for the bug-bounty tooling. It is independent of this scanner; the
  scanner only governs the *chat input* surface.

---

## 9. Related

- [`HOW_INFJ_BOT_WORKS.md`](HOW_INFJ_BOT_WORKS.md) — the chat-turn flow this
  scanner gates.
- [`AI_MORALITY_RULES.md`](AI_MORALITY_RULES.md) — the system-prompt rules
  that handle *output* safety after generation.
- [`../SECURITY.md`](../SECURITY.md) — secrets and reporting.
- [`IDENTITY_VAULT.md`](IDENTITY_VAULT.md) — the post-response integrity
  ledger (Svalbard) and identity regulator (PEDI Engine).
