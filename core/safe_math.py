"""Bounded exact arithmetic and isolated symbolic math for untrusted text.

Only the validated Python AST is interpreted. SymPy receives constructor calls,
never raw text through sympify/parse_expr/eval. Symbolic work runs in a fresh,
killable POSIX process with CPU, address-space, descriptor and output limits.
This is resource containment, not an OS sandbox for arbitrary Python code.
"""

from __future__ import annotations

import ast
import json
import math
import os
import re
import signal
import subprocess
import sys
import threading
from decimal import Decimal, localcontext
from fractions import Fraction
from pathlib import Path

MAX_EXPR_LEN = 512
MAX_SYMBOLIC_LEN = 256
MAX_POW_EXPONENT = 1000
MAX_RESULT_BITS = 60000
MAX_AST_DEPTH = 60
MAX_AST_NODES = 256
SYMBOLIC_TIMEOUT_S = 3.0
SYMBOLIC_MEMORY_BYTES = 512 * 1024 * 1024
SYMBOLIC_CPU_SECONDS = 2
MAX_WORKER_OUTPUT = 65536
_WORKERS = threading.BoundedSemaphore(4)
_ALLOWED_BINOPS = (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.Pow)
_ALLOWED_FUNCS = {
    "sqrt",
    "sin",
    "cos",
    "tan",
    "asin",
    "acos",
    "atan",
    "log",
    "ln",
    "exp",
    "Abs",
    "abs",
}
_ALLOWED_CONST_NAMES = {"pi", "e", "E"}
_VAR_RE = re.compile(r"[a-zA-Z][a-zA-Z0-9]{0,9}")


class MathError(Exception):
    """A refused or unavailable computation; safe to show to the caller."""


def _guard_size(value: Fraction) -> Fraction:
    if (
        max(abs(value.numerator).bit_length(), value.denominator.bit_length())
        > MAX_RESULT_BITS
    ):
        raise MathError("result too large")
    return value


def _number(node: ast.Constant, source: str) -> Fraction:
    value = node.value
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise MathError("only numeric literals allowed")
    if isinstance(value, int):
        return _guard_size(Fraction(value))
    if not math.isfinite(value):
        raise MathError("non-finite literal")
    token = ast.get_source_segment(source, node)
    if token is None:
        raise MathError("missing numeric source")
    decimal = Decimal(token.replace("_", ""))
    if abs(decimal.as_tuple().exponent) > 1000:
        raise MathError("numeric exponent too large")
    return _guard_size(Fraction(decimal))


def _safe_pow(base: Fraction, exponent: Fraction) -> Fraction:
    if exponent.denominator != 1:
        raise MathError("non-rational power requires symbolic evaluation")
    e = exponent.numerator
    if abs(e) > MAX_POW_EXPONENT:
        raise MathError("exponent too large")
    bits = max(abs(base.numerator).bit_length(), base.denominator.bit_length(), 1)
    if abs(e) * bits > MAX_RESULT_BITS:
        raise MathError("result too large")
    if base == 0 and e < 0:
        raise MathError("division by zero")
    return _guard_size(base**e)


def _eval_arith(node: ast.AST, source: str) -> Fraction:
    if isinstance(node, ast.Expression):
        return _eval_arith(node.body, source)
    if isinstance(node, ast.Constant):
        return _number(node, source)
    if isinstance(node, ast.UnaryOp):
        value = _eval_arith(node.operand, source)
        return value if isinstance(node.op, ast.UAdd) else -value
    if not isinstance(node, ast.BinOp):
        raise MathError("not pure arithmetic")
    a, b = _eval_arith(node.left, source), _eval_arith(node.right, source)
    try:
        if isinstance(node.op, ast.Add):
            value = a + b
        elif isinstance(node.op, ast.Sub):
            value = a - b
        elif isinstance(node.op, ast.Mult):
            value = a * b
        elif isinstance(node.op, ast.Div):
            value = a / b
        elif isinstance(node.op, ast.FloorDiv):
            value = Fraction(a // b)
        elif isinstance(node.op, ast.Mod):
            value = a % b
        elif isinstance(node.op, ast.Pow):
            value = _safe_pow(a, b)
        else:
            raise MathError("operator not allowed")
    except ZeroDivisionError:
        raise MathError("division by zero") from None
    return _guard_size(value)


def _validate_node(node: ast.AST, source: str, symbolic: bool, depth: int = 0) -> None:
    if depth > MAX_AST_DEPTH:
        raise MathError("expression too deeply nested")
    child = lambda n: _validate_node(n, source, symbolic, depth + 1)
    if isinstance(node, ast.Expression):
        child(node.body)
    elif isinstance(node, ast.Constant):
        _number(node, source)
    elif isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        child(node.operand)
    elif isinstance(node, ast.BinOp) and isinstance(node.op, _ALLOWED_BINOPS):
        child(node.left)
        child(node.right)
        if isinstance(node.op, ast.Pow):
            # Variable exponents and power towers are intentionally unsupported.
            exponent = _eval_arith(node.right, source)
            if abs(exponent) > MAX_POW_EXPONENT:
                raise MathError("exponent too large")
            if any(isinstance(n, (ast.Name, ast.Call)) for n in ast.walk(node.left)):
                return
            base = _eval_arith(node.left, source)
            if exponent.denominator == 1:
                _safe_pow(base, exponent)
        if (
            isinstance(node.op, (ast.Div, ast.FloorDiv, ast.Mod))
            and not any(
                isinstance(n, (ast.Name, ast.Call)) for n in ast.walk(node.right)
            )
            and _eval_arith(node.right, source) == 0
        ):
            raise MathError("division by zero")
    elif symbolic and isinstance(node, ast.Name) and _VAR_RE.fullmatch(node.id):
        if node.id in {"nan", "oo", "zoo", "inf", "Infinity"}:
            raise MathError("non-finite name")
        if node.id in _ALLOWED_FUNCS:
            raise MathError("function requires arguments")
    elif (
        symbolic
        and isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in _ALLOWED_FUNCS
    ):
        arities = (1, 2) if node.func.id in {"log", "ln"} else (1,)
        if node.keywords or len(node.args) not in arities:
            raise MathError("invalid function arguments")
        for arg in node.args:
            child(arg)
    else:
        raise MathError("disallowed syntax")


def _parse_validated(expr: str, *, symbolic: bool) -> tuple[str, ast.Expression]:
    if (
        not isinstance(expr, str)
        or not expr.strip()
        or len(expr) > (MAX_SYMBOLIC_LEN if symbolic else MAX_EXPR_LEN)
    ):
        raise MathError("empty or oversized expression")
    # Validate exactly the normalized string that is subsequently interpreted.
    source = expr.strip().replace("^", "**")
    if len(source) > MAX_EXPR_LEN or not re.fullmatch(
        r"[0-9a-zA-Z_+\-*/%()., \t]+", source
    ):
        raise MathError("disallowed character")
    try:
        tree = ast.parse(source, mode="eval")
    except (SyntaxError, ValueError, RecursionError):
        raise MathError("could not parse expression") from None
    if sum(1 for _ in ast.walk(tree)) > MAX_AST_NODES:
        raise MathError("too many expression nodes")
    _validate_node(tree, source, symbolic)
    return source, tree


def safe_arithmetic(expr: str) -> Fraction:
    source, tree = _parse_validated(expr, symbolic=False)
    return _eval_arith(tree, source)


def _validated_sides(expr: str, solve_for: str | None = None) -> list[str]:
    if not isinstance(expr, str) or len(expr) > MAX_SYMBOLIC_LEN:
        raise MathError("expression too long")
    if solve_for is not None and (
        not isinstance(solve_for, str)
        or not _VAR_RE.fullmatch(solve_for)
        or solve_for in _ALLOWED_FUNCS | _ALLOWED_CONST_NAMES
    ):
        raise MathError("invalid solve variable")
    parts = expr.split("=")
    if len(parts) > 2:
        raise MathError("only one '=' supported")
    return [_parse_validated(side, symbolic=True)[0] for side in parts]


def safe_symbolic(expr: str, *, solve_for: str | None = None) -> dict:
    sides = _validated_sides(expr, solve_for)
    if os.name != "posix":
        raise MathError("resource-limited symbolic worker unavailable")
    if not _WORKERS.acquire(blocking=False):
        raise MathError("symbolic worker busy")
    proc = None
    try:
        worker = str(Path(__file__).with_name("_safe_math_worker.py"))
        proc = subprocess.Popen(
            [sys.executable, "-I", worker],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
            env={"PATH": os.defpath, "PYTHONHASHSEED": "0"},
        )
        try:
            output, _ = proc.communicate(
                json.dumps({"sides": sides, "solve_for": solve_for}),
                timeout=SYMBOLIC_TIMEOUT_S,
            )
        except subprocess.TimeoutExpired:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            proc.communicate()
            raise MathError("computation exceeded time budget") from None
        if proc.returncode != 0 or len(output) > MAX_WORKER_OUTPUT:
            raise MathError("symbolic worker failed or exceeded resource budget")
        payload = json.loads(output)
        if not payload.get("ok"):
            raise MathError("could not evaluate symbolic expression")
        return payload["result"]
    except (OSError, ValueError, KeyError):
        raise MathError("symbolic worker unavailable") from None
    finally:
        if proc is not None and proc.poll() is None:
            proc.kill()
            proc.wait()
        _WORKERS.release()


_MATH_HINT = re.compile(
    r"\d\s*[-+*/^]\s*\d|=|\b(solve|simplify|evaluate|compute|sqrt)\b|\d%|\bpercent\b",
    re.IGNORECASE,
)


def looks_like_math(text: str) -> bool:
    return isinstance(text, str) and bool(_MATH_HINT.search(text))


def format_fraction(frac: Fraction, sig: int = 12) -> dict:
    try:
        exact = (
            str(frac.numerator)
            if frac.denominator == 1
            else f"{frac.numerator}/{frac.denominator}"
        )
    except ValueError:
        raise MathError("result too large to display") from None
    with localcontext() as ctx:
        ctx.prec = sig
        approx = str((Decimal(frac.numerator) / Decimal(frac.denominator)).normalize())
    return {"exact": exact, "approx": exact if frac.denominator == 1 else approx}


def compute(text: str) -> dict:
    if not isinstance(text, str):
        return {"ok": False, "reason": "expression must be text", "input": None}
    text = text.strip()
    try:
        # Validate once before dispatch: an arithmetic resource rejection must not
        # escape through the symbolic fallback.
        sides = _validated_sides(text) if len(text) <= MAX_SYMBOLIC_LEN else None
        if sides is None:
            frac = safe_arithmetic(text)
        elif len(sides) == 1 and not any(
            isinstance(n, (ast.Name, ast.Call))
            for n in ast.walk(ast.parse(sides[0], mode="eval"))
        ):
            try:
                frac = safe_arithmetic(text)
            except MathError as exc:
                if str(exc) != "non-rational power requires symbolic evaluation":
                    raise
                return {
                    "ok": True,
                    "kind": "symbolic",
                    "result": safe_symbolic(text),
                    "input": text,
                }
        else:
            return {
                "ok": True,
                "kind": "symbolic",
                "result": safe_symbolic(text),
                "input": text,
            }
        return {
            "ok": True,
            "kind": "arithmetic",
            "result": format_fraction(frac),
            "input": text,
        }
    except (MathError, ArithmeticError, RecursionError) as exc:
        reason = str(exc) if isinstance(exc, MathError) else "undefined or out of range"
        return {"ok": False, "reason": reason, "input": text}
