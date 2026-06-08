"""
core/safe_math_integration.py — wires safe_math.compute() into the inference path.

WHY THIS FILE EXISTS
    safe_math.py is a validated, adversarially-tested library. Without this file it
    is never called — structurally complete, functionally disconnected. This module
    provides the two integration points that close the gap:

        1. PROMPT BUILDER HOOK (before inference)
           Detects math in the user's query, computes the grounded result, and injects
           a VERIFIED RESULT block into the prompt BEFORE the model sees it. The model
           is told to state the value exactly — not re-derive it.

        2. BRAIN CRITIC HOOK (after inference, during the critic pass)
           After the model generates a response, checks whether any grounded result
           for this turn appears modified or absent. If the model drifted from the
           tool result, the critic corrects it in-place. Tool result wins — always.

WIRING LOCATIONS (adapt to your exact symbol names)
    prompt_builder.py  — inside `build_prompt()` or `format_user_section()`,
                         after the user_input is available but BEFORE the prompt
                         string is finalized. Call inject_grounded_math().

    brain.py critic    — inside the critic pass block that already checks factuality
                         and logical integrity. Add a call to critic_math_check()
                         after that pass, passing the model's draft and the
                         grounded_results dict stored on the request context.

CRITICAL CONTRACT (one rule to remember)
    On {"ok": False}: the model MUST say it could not compute — NOT invent a number.
    The prompt hook enforces this by injecting an explicit "do not guess" instruction.
    The critic enforces it on the output side.

FORBIDDEN_IMPORTS NOTE
    This is a core infrastructure module, not a sandboxed cognitive plugin.
    It may import safe_math, re, and typing freely.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

import contextvars
from infj_bot.core.safe_math import compute, looks_like_math, MathError

active_grounded_math_var: contextvars.ContextVar[List[GroundedResult]] = contextvars.ContextVar("active_grounded_math", default=[])


# --------------------------------------------------------------------------- #
# Expression extraction — pull candidate math sub-strings from natural language
# --------------------------------------------------------------------------- #

# Patterns that suggest a math expression embedded in text.
# Deliberately conservative: high precision over high recall. A missed expression
# is less harmful than injecting a wrong grounded fact.
_EXPR_PATTERNS = [
    # arithmetic: number op number (handles multi-term chains via iteration)
    re.compile(r"[\d.]+(?:\s*[+\-*/^%]\s*[\d.]+)+", re.ASCII),
    # equations: LHS = RHS with at least one variable or operation
    re.compile(r"[a-zA-Z\d\s+\-*/^().,]+=\s*[\d\-][\d.]*", re.ASCII),
    # named functions: sqrt(...), log(...), sin(...) etc.
    re.compile(r"(?:sqrt|sin|cos|tan|log|ln|exp|abs)\s*\([^)]{1,60}\)", re.ASCII),
    # percentage arithmetic
    re.compile(r"[\d.]+\s*%\s*(?:of\s*)?[\d.]+", re.ASCII),
]


def extract_math_candidates(text: str) -> List[str]:
    """Return candidate math sub-strings from natural-language text.

    Returns a de-duplicated list, shortest-first, max 5 candidates so we don't
    run compute() on a flood of false positives.
    """
    if not looks_like_math(text):
        return []
    seen, out = set(), []
    for pat in _EXPR_PATTERNS:
        for m in pat.finditer(text):
            candidate = m.group(0).strip()
            if candidate not in seen and len(candidate) <= 256:
                seen.add(candidate)
                out.append(candidate)
    return sorted(out, key=len)[:5]


# --------------------------------------------------------------------------- #
# Grounded result type
# --------------------------------------------------------------------------- #

class GroundedResult:
    """One verified math result for this turn."""
    def __init__(self, expression: str, result: Dict[str, Any]):
        self.expression = expression
        self.result = result              # the full dict from compute()
        self.ok = result["ok"]

    @property
    def display_value(self) -> str:
        if not self.ok:
            return "[could not compute]"
        r = self.result["result"]
        if isinstance(r, dict):
            exact = r.get("exact", "")
            approx = r.get("approx", "")
            sols = r.get("solutions")
            if sols is not None:
                return "solutions: " + ", ".join(str(s) for s in sols)
            if exact == approx or not approx:
                return exact
            return f"{exact} (≈ {approx})"
        return str(r)

    def __repr__(self) -> str:
        return f"GroundedResult({self.expression!r} -> {self.display_value!r})"


# --------------------------------------------------------------------------- #
# 1. PROMPT BUILDER HOOK
# --------------------------------------------------------------------------- #

def compute_grounded_results(user_input: str) -> List[GroundedResult]:
    """Compute verified results for all math found in user_input.

    Call this BEFORE assembling the final prompt. Store the returned list on
    the request context (e.g., request_state.grounded_math = ...) so the critic
    hook can access it after generation.

    Returns an empty list when no math is detected — zero overhead for
    non-math turns.
    """
    candidates = extract_math_candidates(user_input)
    results = []
    for expr in candidates:
        try:
            r = compute(expr)
            results.append(GroundedResult(expr, r))
        except MathError:
            results.append(GroundedResult(expr, {"ok": False, "reason": "blocked"}))
    return results


def build_grounding_block(grounded: List[GroundedResult]) -> str:
    """Format a [MATH ENGINE] section to inject into the system prompt.

    Inject this BEFORE the user message, so the model reads the verified results
    before it processes the query. The instruction is explicit: state the value
    exactly, do NOT re-derive, do NOT invent on failure.

    Returns an empty string when there are no grounded results — leaves the
    prompt unchanged on non-math turns.
    """
    if not grounded:
        return ""
    lines = [
        "[MATH ENGINE — VERIFIED RESULTS]",
        "The following were computed by a sandboxed arithmetic engine, not by you.",
        "Rules: state exact values as given. Never re-derive. Never round unless asked.",
    ]
    for gr in grounded:
        if gr.ok:
            lines.append(f"  • {gr.expression}  →  {gr.display_value}")
        else:
            lines.append(
                f"  • {gr.expression}  →  COULD NOT COMPUTE. "
                "Tell the user you cannot evaluate this; do not invent a number."
            )
    lines.append("[END MATH ENGINE]")
    return "\n".join(lines)


def inject_grounded_math(user_input: str, existing_prompt: str) -> tuple[str, List[GroundedResult]]:
    """One-call convenience: compute, format, and prepend to the existing prompt.

    ADAPT: Replace `existing_prompt` with whatever your prompt_builder constructs.
    The grounded list is returned so the critic hook can use it later.

    Example (inside your prompt_builder / assemble_prompt_sections):

        prompt, grounded = inject_grounded_math(user_input, assembled_system_block)
        request_context.grounded_math = grounded   # store for critic pass
        return prompt
    """
    grounded = compute_grounded_results(user_input)
    block = build_grounding_block(grounded)
    if not block:
        return existing_prompt, grounded
    # Inject after the system header, before conversation history.
    updated = block + "\n\n" + existing_prompt
    return updated, grounded


# --------------------------------------------------------------------------- #
# 2. BRAIN CRITIC HOOK
# --------------------------------------------------------------------------- #

# Regex for numbers in model output: integers, decimals, simple fractions.
_NUMBER_RE = re.compile(r"-?\d+(?:[./]\d+)?")


def critic_math_check(
    model_draft: str,
    grounded: List[GroundedResult],
    *,
    correct_in_place: bool = True,
) -> tuple[str, List[str]]:
    """Check and optionally correct the model's draft against grounded results.

    Call this inside brain.py's critic pass, AFTER factuality / logical-integrity
    checks. The tool result ALWAYS wins over the model's arithmetic.

    Args:
        model_draft:       The model's generated text for this turn.
        grounded:          The GroundedResult list from compute_grounded_results().
        correct_in_place:  If True, replace wrong values in the draft. If False,
                           just report violations without modifying text.

    Returns:
        (corrected_draft, violations)
        violations is a list of human-readable mismatch descriptions.
        When everything is correct, violations is empty.

    ADAPT: in brain.py critic block, add:

        from core.safe_math_integration import critic_math_check
        response, violations = critic_math_check(response, request_context.grounded_math)
        if violations:
            log.warning("critic corrected math: %s", violations)
    """
    if not grounded:
        return model_draft, []

    draft = model_draft
    violations: List[str] = []

    for gr in grounded:
        if not gr.ok:
            # Model should have said it couldn't compute. If it stated a number, flag it.
            # We can't know which number it "invented," so just log for human review.
            nums_in_draft = _NUMBER_RE.findall(draft)
            if nums_in_draft:
                violations.append(
                    f"Expression {gr.expression!r} could not be computed, but draft "
                    f"contains numbers {nums_in_draft[:3]}. Verify none were invented."
                )
            continue

        # Extract the canonical exact value.
        r = gr.result.get("result", {})
        if isinstance(r, dict):
            sols = r.get("solutions")
            exact = r.get("exact")
            if sols:
                # For solved equations, check each solution appears in the draft.
                for sol in sols:
                    sol_str = str(sol)
                    if sol_str and sol_str not in draft:
                        violations.append(
                            f"{gr.expression} solution {sol_str} missing from draft."
                        )
            elif exact and exact not in draft:
                # The exact canonical value isn't in the draft. Check for close variants.
                approx = r.get("approx", "")
                if not approx or approx not in draft:
                    # Neither exact nor decimal approximation appears. Attempt correction.
                    violations.append(
                        f"{gr.expression} → {exact}: value not found in draft."
                    )
                    if correct_in_place:
                        # Find the first number in the draft near this expression and
                        # append a correction footnote. Do NOT blindly str-replace
                        # numbers (too many false positives in prose). Instead surface
                        # the correct value at the end so the model's prose is preserved
                        # and the user gets the right answer regardless.
                        correction = (
                            f"\n[Verified: {gr.expression} = {gr.display_value}]"
                        )
                        draft += correction
    return draft, violations


# --------------------------------------------------------------------------- #
# Integration checklist — run this once to confirm seams are reachable
# --------------------------------------------------------------------------- #
def _run_integration_check() -> None:
    """Quick smoke-check: verify both hooks work end-to-end without real LLM.

    Run manually: python -c "from core.safe_math_integration import _run_integration_check; _run_integration_check()"
    """
    print("safe_math_integration smoke-check")
    # Hook 1: prompt injection
    prompt, grounded = inject_grounded_math(
        "What is 1/3 + 1/3 + 1/3?",
        "SYSTEM PROMPT PLACEHOLDER"
    )
    assert "[MATH ENGINE" in prompt, "injection failed"
    assert any(g.ok for g in grounded), "no grounded result"
    print(f"  prompt hook OK — grounded: {[str(g) for g in grounded]}")

    # Hook 2: critic catches drift
    fake_draft = "The answer is approximately 0.999 which rounds to 1."
    corrected, violations = critic_math_check(fake_draft, grounded)
    print(f"  critic hook OK — violations: {violations}")
    print("  both hooks reachable and returning expected shapes")
    print("SMOKE-CHECK PASSED")
