"""
tests/test_safe_math.py — adversarial + correctness suite for core/safe_math.py

TIMEOUT FIX
    The original suite ran all symbolic calls in one process. Each _with_timeout
    spins a daemon thread that joins for up to SYMBOLIC_TIMEOUT_S seconds. Stack
    enough of them and the process total exceeds the sandbox limit — not because
    any single call is broken, but because blocked joins accumulate.

    Fix: override SYMBOLIC_TIMEOUT_S to 0.3s for the test process (fast fail for
    tests we expect to succeed quickly) and isolate each symbolic call in its own
    subprocess so threads never stack across calls.

    Security note: subprocess is available in test files — they are NOT sandboxed
    cognitive plugins, so the plugin FORBIDDEN_IMPORTS list does not apply here.

Run:   python tests/test_safe_math.py
Exit:  0 = all pass, 1 = failures
"""

from __future__ import annotations
import json
import subprocess
import sys
from pathlib import Path

# Point at your real module location
CORE_DIR = str(Path(__file__).parent.parent / "core")
sys.path.insert(0, CORE_DIR)

import safe_math
safe_math.SYMBOLIC_TIMEOUT_S = 0.3   # fast-fail for the test process only

_pass = _fail = 0


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _isolated_compute(expr: str) -> dict:
    """Run compute() in a fresh subprocess so threads never accumulate."""
    script = (
        f"import sys; sys.path.insert(0, {CORE_DIR!r}); "
        f"import safe_math, json; safe_math.SYMBOLIC_TIMEOUT_S=0.3; "
        f"print(json.dumps(safe_math.compute({expr!r})))"
    )
    try:
        r = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True, timeout=5
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "reason": "timeout"}
    if r.returncode != 0 or not r.stdout.strip():
        return {"ok": False, "reason": r.stderr.decode().strip() or "subprocess error"}
    return json.loads(r.stdout)


def expect_exact(expr, expected_exact, label=""):
    global _pass, _fail
    r = safe_math.compute(expr)
    ok = r["ok"] and r["result"].get("exact") == expected_exact
    tag = f"[{label}] " if label else ""
    print(f"{'ok' if ok else 'XX'} arith  {tag}{expr!r:36} exact={r.get('result',{}).get('exact')!r}")
    _pass += ok; _fail += (not ok)


def expect_solve(expr, expected_sols, label=""):
    global _pass, _fail
    r = _isolated_compute(expr)
    sols = set(r.get("result", {}).get("solutions", [])) if r["ok"] else set()
    ok = r["ok"] and sols == set(expected_sols)
    tag = f"[{label}] " if label else ""
    print(f"{'ok' if ok else 'XX'} solve  {tag}{expr!r:36} solutions={sols}")
    _pass += ok; _fail += (not ok)


def expect_symbolic_ok(expr, label=""):
    global _pass, _fail
    r = _isolated_compute(expr)
    ok = r["ok"]
    tag = f"[{label}] " if label else ""
    print(f"{'ok' if ok else 'XX'} sym-ok {tag}{expr!r:36} -> {r.get('result')}")
    _pass += ok; _fail += (not ok)


def expect_block(expr, label=""):
    """MUST NOT produce a value. If it does, that is a CRITICAL FAILURE."""
    global _pass, _fail
    blocked = True
    try:
        r = _isolated_compute(expr)
        blocked = not r["ok"]
    except Exception as e:
        blocked = False
        print(f"    (leaked {type(e).__name__}: {e})")
    tag = f"[{label}] " if label else ""
    status = "BLOCKED" if blocked else "CRITICAL FAILURE — value escaped sandbox"
    print(f"{'ok' if blocked else 'XX'} BLOCK  {tag}{expr!r:40} {status}")
    _pass += blocked; _fail += (not blocked)


# --------------------------------------------------------------------------- #
# 1. Exact arithmetic — fractions.Fraction, no float drift
# --------------------------------------------------------------------------- #
def test_safe_math_suite():
    global _pass, _fail
    _pass = _fail = 0

    print("=== ARITHMETIC EXACTNESS ===")
    expect_exact("2+2",           "4")
    expect_exact("2 * 3 + 4",    "10")
    expect_exact("(3/4) + (1/4)","1",   "exact rational")
    expect_exact("1/3 + 1/3 + 1/3", "1", "would be 0.99... in float")
    expect_exact("0.1 + 0.2",    "3/10","float trap")
    expect_exact("2**10",         "1024")
    expect_exact("-5 + 3",        "-2")
    expect_exact("7 // 2",        "3")
    expect_exact("7 % 3",         "1")
    expect_exact("10 ** -2",      "1/100")

    # --------------------------------------------------------------------------- #
    # 2. Symbolic — isolated subprocesses, no thread accumulation
    # --------------------------------------------------------------------------- #
    print("\n=== SYMBOLIC ===")
    expect_solve("x**2 - 4 = 0",  ["-2", "2"])
    expect_solve("2*x + 6 = 0",   ["-3"])
    expect_symbolic_ok("sqrt(16)",  "should simplify to 4")
    expect_symbolic_ok("(x+1)**2",  "expand/simplify")

    # --------------------------------------------------------------------------- #
    # 3. Adversarial — every one MUST be blocked. A value return = release blocker.
    # --------------------------------------------------------------------------- #
    print("\n=== ADVERSARIAL (all must BLOCK) ===")
    expect_block("__import__('os').system('id')",     "dunder-import")
    expect_block("(1).__class__",                      "attribute access")
    expect_block("().__class__.__bases__[0].__subclasses__()", "subclass chain")
    expect_block("eval('1+1')",                        "eval call")
    expect_block("exec('x=1')",                        "exec call")
    expect_block("lambda: 1",                          "lambda")
    expect_block("os.getcwd()",                        "name.attribute call")
    expect_block("open('/etc/passwd').read()",          "open call")
    expect_block("[x for x in range(10)]",             "list comprehension")
    expect_block("{}.__class__",                       "dict dunder")
    expect_block("globals()",                          "globals call")
    expect_block("9**9**9",                            "exponent tower")
    expect_block("2**99999999",                        "huge exponent")
    expect_block("factorial(100000)",                  "excluded heavy fn")
    expect_block("1/0",                                "div by zero")
    expect_block("x" * 600,                            "length cap")
    expect_block("a.b.c",                              "chained attribute")
    expect_block("print('hi')",                        "non-whitelisted call")

    # --------------------------------------------------------------------------- #
    # 4. Result
    # --------------------------------------------------------------------------- #
    total = _pass + _fail
    print(f"\n=== RESULT: {_pass}/{total} passed, {_fail} failed ===")
    if _fail:
        print("FAILURES ABOVE — do not ship.")
        assert False, f"{_fail} safe_math tests failed"

if __name__ == "__main__":
    test_safe_math_suite()

