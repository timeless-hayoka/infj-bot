"""Standalone correctness and adversarial tests for ``drift.core.safe_math``."""

from __future__ import annotations

import json
import sys
from fractions import Fraction
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from drift.core import safe_math as math

ARITHMETIC_CASES = [
    ("2+2", "4"),
    ("2 * 3 + 4", "10"),
    ("(3/4) + (1/4)", "1"),
    ("1/3 + 1/3 + 1/3", "1"),
    ("0.1 + 0.2", "3/10"),
    ("2**10", "1024"),
    ("-5 + 3", "-2"),
    ("7 // 2", "3"),
    ("7 % 3", "1"),
    ("10 ** -2", "1/100"),
]

SYMBOLIC_CASES = [
    ("x**2 - 4 = 0", "solutions", ["-2", "2"]),
    ("2*x + 6 = 0", "solutions", ["-3"]),
    ("sqrt(16)", "simplified", "4"),
    ("(x+1)**2", "simplified", "(x + 1)**2"),
]

REQUIRED_ADVERSARIAL = [
    "__import__('os').system('id')",
    "(1).__class__",
    "().__class__.__bases__[0].__subclasses__()",
    "eval('1+1')",
    "exec('x=1')",
    "lambda: 1",
    "os.getcwd()",
    "open('/etc/passwd').read()",
    "[x for x in range(10)]",
    "{}.__class__",
    "globals()",
    "9**9**9",
    "2**99999999",
    "factorial(100000)",
    "1/0",
    "x" * 600,
    "a.b.c",
    "print('hi')",
]

BOUNDARY_ADVERSARIAL = [
    # booleans and complex values
    "True",
    "1 + False",
    "1j",
    "complex(1, 2)",
    # malformed or ambiguous equations
    "x =",
    "= 1",
    "x == 1",
    "x = 1 = 2",
    "x + y = 1",
    # keyword, starred, and invalid function arity
    "sqrt(x=2)",
    "sin(*[1])",
    "sin()",
    "sin(1, 2)",
    "log(8, 2, 1)",
    # containers, comprehensions, assignment expressions, and subscripts
    "[1, 2]",
    "(1, 2)",
    "{1, 2}",
    "{'x': 1}",
    "[x for x in range(3)]",
    "(x := 1)",
    "x[0]",
    # nesting, names, Unicode, and disallowed characters
    "(" * 70 + "1" + ")" * 70,
    "abcdefghijk + 1",
    "_x + 1",
    "class + 1",
    "builtins + 1",
    "π + 1",
    "x ≤ 2",
    "1 + 💥",
    # zero negative powers and result-growth boundaries
    "0 ** -1",
    "1 / (999999999999999999999999999999 ** 1000)",
    "x ** 1000 = 1",
    "(x ** 1000) ** 1000",
    # additional denied calls and non-finite names
    "compile('1', 'x', 'eval')",
    "getattr(x, 'y')",
    "nan + 1",
    "oo + 1",
]


def run_suite(*, verbose: bool = True) -> dict:
    failures: list[str] = []
    correctness_passed = 0
    blocked = 0
    leaked_exceptions = 0
    blocked_returned_value = 0

    def compute_no_leak(expression):
        nonlocal leaked_exceptions
        try:
            return math.compute(expression)
        except Exception as exc:  # noqa: BLE001 - all public exceptions are test failures
            leaked_exceptions += 1
            failures.append(
                f"public exception for {expression!r}: {type(exc).__name__}: {exc}"
            )
            return {"ok": True, "result": "exception sentinel"}

    for expression, expected in ARITHMETIC_CASES:
        result = compute_no_leak(expression)
        if (
            result.get("ok") is True
            and result.get("kind") == "arithmetic"
            and result.get("result", {}).get("exact") == expected
        ):
            correctness_passed += 1
        else:
            failures.append(f"arithmetic {expression!r}: expected {expected}, got {result}")

    for expression, field, expected in SYMBOLIC_CASES:
        result = compute_no_leak(expression)
        if result.get("ok") is True and result.get("result", {}).get(field) == expected:
            correctness_passed += 1
        else:
            failures.append(f"symbolic {expression!r}: expected {field}={expected}, got {result}")

    adversarial = REQUIRED_ADVERSARIAL + BOUNDARY_ADVERSARIAL
    for expression in adversarial:
        result = compute_no_leak(expression)
        if result.get("ok") is False and result.get("reason"):
            blocked += 1
        else:
            blocked_returned_value += 1
            failures.append(f"RELEASE BLOCKER: adversarial input returned a value: {expression!r}: {result}")

    # Public API and explicit solve target checks.
    try:
        if math.safe_arithmetic("1/2 + 1/2") != Fraction(1):
            failures.append("safe_arithmetic did not return Fraction(1)")
        solved = math.safe_symbolic("x + y = 1", solve_for="x")
        if solved != {"type": "solve", "variable": "x", "solutions": ["1 - y"]}:
            failures.append(f"explicit solve_for returned {solved}")
        try:
            math.safe_symbolic("x=1", solve_for="x.__class__")
        except math.MathError:
            pass
        else:
            failures.append("invalid solve_for was accepted")
    except Exception as exc:  # noqa: BLE001 - all public exceptions are test failures
        failures.append(f"direct API contract failed: {type(exc).__name__}: {exc}")

    if not math.looks_like_math("please compute 2 + 2"):
        failures.append("looks_like_math missed clear arithmetic")
    if math.looks_like_math("tell me a quiet story about DNS"):
        failures.append("looks_like_math flagged non-math prose")

    for value in (None, True, 5, [], {}):
        result = compute_no_leak(value)
        if result.get("ok") is not False:
            failures.append(f"non-text input was accepted: {value!r}")

    source = Path(math.__file__).read_text(encoding="utf-8")
    for forbidden in ("import os", "import subprocess", "import socket", "import pickle", "import ctypes"):
        if forbidden in source:
            failures.append(f"forbidden sandbox import present: {forbidden}")
    if "parse_expr(" not in source or '"__builtins__": {}' not in source:
        failures.append("restricted parse_expr namespace is not visibly configured")

    summary = {
        "verdict": "PASS" if not failures else "FAIL",
        "correctness_passed": correctness_passed,
        "correctness_total": len(ARITHMETIC_CASES) + len(SYMBOLIC_CASES),
        "adversarial_blocked": blocked,
        "adversarial_total": len(adversarial),
        "non_matherror_exceptions_leaked": leaked_exceptions,
        "blocked_inputs_returning_values": blocked_returned_value,
        "failures": failures,
    }
    if verbose:
        print(json.dumps(summary, indent=2, ensure_ascii=True))
    return summary


def test_safe_math_contract() -> None:
    """Pytest-compatible entry point; pytest is not required by this file."""

    summary = run_suite(verbose=False)
    assert summary["verdict"] == "PASS", summary


def main() -> int:
    return 0 if run_suite()["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
