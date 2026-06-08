"""
core/safe_math.py — Restricted math evaluation for DRIFT.

WHY THIS EXISTS
    The LLM must never compute arithmetic "in its head" — that is where small
    models hallucinate. This module computes the answer; the model only phrases it.

THREAT MODEL
    Input strings originate from user queries AND model-drafted answers. Both are
    treated as fully untrusted. The classic escapes we must defeat:
        __import__('os').system(...)        -> blocked: no Call to non-whitelisted names,
                                                and '__' substring rejected
        (1).__class__.__bases__...          -> blocked: ast.Attribute is disallowed
        eval('...') / exec(...)             -> blocked: not in whitelist, no builtins
        9**9**9  /  factorial(10**9)         -> blocked: exponent + result-size caps,
                                                heavy functions excluded from namespace
        lambda / comprehensions / subscript -> blocked: node-type allowlist

DESIGN (two independent layers)
    Layer 1  Python `ast` allowlist. We parse the string ourselves and walk it
             against an explicit whitelist of node types. ANYTHING not on the list
             raises. This is the real security boundary.
    Layer 2  Only after Layer 1 passes do we touch sympy, and even then we call
             parse_expr with global_dict={} (no builtins) and a curated local_dict.
             We NEVER call sympy.sympify() on raw input — historically it could eval.

EXACTNESS
    Arithmetic is done in fractions.Fraction (exact rationals). We report the exact
    value and a rounded decimal approximation.

FORBIDDEN_IMPORTS COMPLIANCE
    Imports only: ast, math, re, threading, fractions, decimal, sympy.
    No os / subprocess / socket / pickle / ctypes / urllib.

REQUIRED SYMPY: >= 1.11 (older parse_expr defaults are riskier). Pin it.
"""

from __future__ import annotations

import ast
import math
import re
import threading
from decimal import Decimal, getcontext
from fractions import Fraction

# --------------------------------------------------------------------------- #
# Caps (tune for your droplet; these bound CPU and memory, not correctness)
# --------------------------------------------------------------------------- #
MAX_EXPR_LEN = 512            # reject pathologically long inputs outright
MAX_SYMBOLIC_LEN = 256        # symbolic path is more expensive; tighter cap
MAX_POW_EXPONENT = 1_000      # blocks 9**9**9-style towers
MAX_RESULT_BITS = 60_000      # ~18k digits; bounds memory of any single result
MAX_AST_DEPTH = 60            # bounds nesting / recursion
SYMBOLIC_TIMEOUT_S = 2.0      # wall-clock budget for sympy work (see honest caveat)

_ALLOWED_BINOPS = (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.Pow)
_ALLOWED_UNARY = (ast.UAdd, ast.USub)

# Functions/constants exposed to the SYMBOLIC path. Deliberately excludes
# factorial, integrate, summation, product, series, solveset-over-reals, etc.,
# because those are the open-ended CPU-hang vectors. Keep this list minimal.
_ALLOWED_FUNCS = {
    "sqrt", "sin", "cos", "tan", "asin", "acos", "atan",
    "log", "ln", "exp", "Abs", "abs",
}
_ALLOWED_CONST_NAMES = {"pi", "e", "E"}
_VAR_RE = re.compile(r"[a-zA-Z][a-zA-Z0-9]{0,9}")  # variable names: short, alnum
_BANNED_SUBSTR = ("__", "import", "lambda", "exec", "eval", "lcm", "compile")


class MathError(Exception):
    """Raised for any input we refuse to evaluate. Never leaks internals."""


# --------------------------------------------------------------------------- #
# LAYER 1 — pure arithmetic, exact rationals, no sympy
# --------------------------------------------------------------------------- #
def _guard_size(v: Fraction) -> Fraction:
    if (abs(v.numerator).bit_length() > MAX_RESULT_BITS
            or abs(v.denominator).bit_length() > MAX_RESULT_BITS):
        raise MathError("result too large")
    return v


def _safe_pow(base: Fraction, exp: Fraction) -> Fraction:
    # Pre-flight size check so we never *build* an oversized integer.
    if exp.denominator == 1:
        e = exp.numerator
        if abs(e) > MAX_POW_EXPONENT:
            raise MathError("exponent too large")
        base_bits = max(abs(base.numerator).bit_length(),
                        abs(base.denominator).bit_length(), 1)
        if abs(e) * base_bits > MAX_RESULT_BITS:
            raise MathError("result too large")
        if e >= 0:
            return _guard_size(base ** e)
        if base == 0:
            raise MathError("division by zero")
        return _guard_size(Fraction(1) / (base ** (-e)))
    # Fractional exponent: no exact rational result. Approximate via float, bounded.
    try:
        val = float(base) ** float(exp)
    except (ValueError, OverflowError):
        raise MathError("undefined or out of range")
    if not math.isfinite(val):
        raise MathError("undefined or out of range")
    return Fraction(val).limit_denominator(10 ** 12)


def _const_to_fraction(value) -> Fraction:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise MathError("only numeric literals allowed")
    if isinstance(value, int):
        return Fraction(value)
    # Use the source text form so 0.1 -> 1/10 exactly, not the binary-float artifact.
    return Fraction(str(value))


def _eval_arith(node: ast.AST, depth: int = 0) -> Fraction:
    if depth > MAX_AST_DEPTH:
        raise MathError("expression too deeply nested")
    if isinstance(node, ast.Expression):
        return _eval_arith(node.body, depth + 1)
    if isinstance(node, ast.Constant):
        return _const_to_fraction(node.value)
    if isinstance(node, ast.UnaryOp):
        if not isinstance(node.op, _ALLOWED_UNARY):
            raise MathError("operator not allowed")
        v = _eval_arith(node.operand, depth + 1)
        return +v if isinstance(node.op, ast.UAdd) else -v
    if isinstance(node, ast.BinOp):
        if not isinstance(node.op, _ALLOWED_BINOPS):
            raise MathError("operator not allowed")
        left = _eval_arith(node.left, depth + 1)
        right = _eval_arith(node.right, depth + 1)
        op = node.op
        if isinstance(op, ast.Add):
            return _guard_size(left + right)
        if isinstance(op, ast.Sub):
            return _guard_size(left - right)
        if isinstance(op, ast.Mult):
            return _guard_size(left * right)
        if isinstance(op, ast.Div):
            if right == 0:
                raise MathError("division by zero")
            return _guard_size(left / right)
        if isinstance(op, ast.FloorDiv):
            if right == 0:
                raise MathError("division by zero")
            return Fraction(left // right)
        if isinstance(op, ast.Mod):
            if right == 0:
                raise MathError("modulo by zero")
            return _guard_size(left % right)
        if isinstance(op, ast.Pow):
            return _safe_pow(left, right)
    # ast.Name, ast.Call, ast.Attribute, ast.Subscript, ast.Lambda, comprehensions,
    # ast.Starred, etc. all fall through to here and are rejected.
    raise MathError(f"disallowed expression: {type(node).__name__}")


def safe_arithmetic(expr: str) -> Fraction:
    """Evaluate a pure-number expression exactly. Raises MathError on anything else."""
    if not isinstance(expr, str) or len(expr) > MAX_EXPR_LEN:
        raise MathError("expression too long")
    try:
        tree = ast.parse(expr, mode="eval")
    except (SyntaxError, ValueError):
        raise MathError("could not parse expression")
    return _eval_arith(tree)


# --------------------------------------------------------------------------- #
# LAYER 1 GATE for the symbolic path — validate AST shape BEFORE sympy sees it
# --------------------------------------------------------------------------- #
def _validate_symbolic_ast(node: ast.AST, depth: int = 0) -> None:
    if depth > MAX_AST_DEPTH:
        raise MathError("expression too deeply nested")
    if isinstance(node, ast.Expression):
        return _validate_symbolic_ast(node.body, depth + 1)
    if isinstance(node, ast.BinOp):
        if not isinstance(node.op, _ALLOWED_BINOPS):
            raise MathError("operator not allowed")
        if isinstance(node.op, (ast.Div, ast.FloorDiv, ast.Mod)):
            if isinstance(node.right, ast.Constant) and node.right.value == 0:
                raise MathError("division by zero")
        _validate_symbolic_ast(node.left, depth + 1)
        _validate_symbolic_ast(node.right, depth + 1)
        return
    if isinstance(node, ast.UnaryOp):
        if not isinstance(node.op, _ALLOWED_UNARY):
            raise MathError("operator not allowed")
        _validate_symbolic_ast(node.operand, depth + 1)
        return
    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
            raise MathError("only numeric literals allowed")
        return
    if isinstance(node, ast.Name):
        nm = node.id
        if nm in _ALLOWED_FUNCS or nm in _ALLOWED_CONST_NAMES:
            return
        if _VAR_RE.fullmatch(nm):
            return
        raise MathError("name not allowed")
    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name) or node.func.id not in _ALLOWED_FUNCS:
            raise MathError("function not allowed")
        if node.keywords:
            raise MathError("keyword arguments not allowed")
        if len(node.args) > 2:
            raise MathError("too many arguments")
        for a in node.args:
            _validate_symbolic_ast(a, depth + 1)
        return
    # Attribute, Subscript, Lambda, comprehensions, etc. -> rejected here.
    raise MathError(f"disallowed syntax: {type(node).__name__}")


def _validate_expr_side(side: str) -> None:
    side = side.strip()
    if not side:
        raise MathError("empty expression")
    try:
        # '^' is xor in Python ast; map to '**' so power validates correctly.
        tree = ast.parse(side.replace("^", "**"), mode="eval")
    except (SyntaxError, ValueError):
        raise MathError("could not parse expression")
    _validate_symbolic_ast(tree)


def _prevalidate_symbolic(expr: str) -> None:
    if not isinstance(expr, str) or len(expr) > MAX_SYMBOLIC_LEN:
        raise MathError("expression too long")
    low = expr.lower()
    if any(b in low for b in _BANNED_SUBSTR):
        raise MathError("disallowed token")
    # Charset gate: digits, letters, the operators we allow, parens, dot, comma, =, space.
    if not re.fullmatch(r"[0-9a-zA-Z_+\-*/^().,= \t]+", expr):
        raise MathError("disallowed character")
    # Validate each side of an equation independently — eval-mode ast can't parse '='.
    parts = expr.split("=")
    if len(parts) > 2:
        raise MathError("only one '=' supported")
    for part in parts:
        _validate_expr_side(part)


def _with_timeout(fn, *args):
    """Run fn in a daemon thread with a wall-clock budget.

    HONEST CAVEAT: a hung, CPU-bound sympy call holds the GIL and CANNOT be force-
    killed from another thread. If it overruns we stop *waiting* and return an error,
    but the thread may still run to completion in the background. The REAL protection
    against hangs is the input restriction above (length cap + exclusion of integrate/
    summation/factorial/series), not this timeout. Treat the timeout as a backstop.
    """
    result, error = [], []

    def runner():
        try:
            result.append(fn(*args))
        except Exception as e:  # noqa: BLE001 - surface as MathError below
            error.append(e)

    t = threading.Thread(target=runner, daemon=True)
    t.start()
    t.join(SYMBOLIC_TIMEOUT_S)
    if t.is_alive():
        raise MathError("computation exceeded time budget")
    if error:
        raise MathError("could not evaluate symbolic expression")
    return result[0]


def _symbolic_namespace():
    import sympy
    return {
        "sqrt": sympy.sqrt, "sin": sympy.sin, "cos": sympy.cos, "tan": sympy.tan,
        "asin": sympy.asin, "acos": sympy.acos, "atan": sympy.atan,
        "log": sympy.log, "ln": sympy.log, "exp": sympy.exp,
        "Abs": sympy.Abs, "abs": sympy.Abs,
        "pi": sympy.pi, "e": sympy.E, "E": sympy.E,
    }


def _parse_sym(text: str):
    import sympy
    from sympy.parsing.sympy_parser import (
        parse_expr, standard_transformations,
        implicit_multiplication_application, convert_xor,
    )
    transformations = standard_transformations + (
        implicit_multiplication_application,  # "2x" -> "2*x"
        convert_xor,                          # "^"  -> "**"
    )
    ns = _symbolic_namespace()
    # global_dict supplies ONLY sympy's expression-construction primitives plus our
    # whitelisted names. '__builtins__': {} is critical — without it, eval() inside
    # parse_expr auto-injects the real Python builtins. Security still rests on the
    # Layer-1 AST allowlist that ran before we ever reach this point.
    gdict = {
        "Integer": sympy.Integer, "Float": sympy.Float, "Rational": sympy.Rational,
        "Symbol": sympy.Symbol, "Mul": sympy.Mul, "Add": sympy.Add, "Pow": sympy.Pow,
        "__builtins__": {},
    }
    gdict.update(ns)
    return parse_expr(
        text, local_dict=ns, global_dict=gdict,
        transformations=transformations, evaluate=True,
    )


def safe_symbolic(expr: str, *, solve_for: str | None = None) -> dict:
    """Simplify an expression or solve an equation (single '=' splits into Eq)."""
    import sympy
    _prevalidate_symbolic(expr)

    if "=" in expr:
        lhs, _, rhs = expr.partition("=")
        if "=" in rhs:
            raise MathError("only one '=' supported")

        def _solve():
            L, R = _parse_sym(lhs), _parse_sym(rhs)
            eq = sympy.Eq(L, R)
            syms = sorted(eq.free_symbols, key=lambda s: s.name)
            if solve_for:
                target = sympy.Symbol(solve_for)
            elif len(syms) == 1:
                target = syms[0]
            else:
                raise MathError("ambiguous: specify which variable to solve for")
            sols = sympy.solve(eq, target, dict=False)
            return {"type": "solve", "variable": str(target),
                    "solutions": [str(s) for s in sols]}

        return _with_timeout(_solve)

    def _simplify():
        e = sympy.simplify(_parse_sym(expr))
        out = {"type": "expr", "simplified": str(e)}
        if not e.free_symbols:
            out["numeric"] = str(e.evalf(15))
        return out

    return _with_timeout(_simplify)


# --------------------------------------------------------------------------- #
# Public surface: dispatcher + formatting (this is what brain/prompt_builder call)
# --------------------------------------------------------------------------- #
_MATH_HINT = re.compile(r"\d\s*[-+*/^]\s*\d|=|\b(solve|simplify|evaluate|compute)\b"
                        r"|\bsqrt\b|\d%|\bpercent\b", re.IGNORECASE)


def looks_like_math(text: str) -> bool:
    """Cheap heuristic: should we even try? Keep recall high, precision loose."""
    return bool(text) and bool(_MATH_HINT.search(text))


def format_fraction(frac: Fraction, sig: int = 12) -> dict:
    if frac.denominator == 1:
        return {"exact": str(frac.numerator), "approx": str(frac.numerator)}
    getcontext().prec = sig + 6
    approx = (Decimal(frac.numerator) / Decimal(frac.denominator)).normalize()
    return {"exact": f"{frac.numerator}/{frac.denominator}", "approx": str(approx)}


def compute(text: str) -> dict:
    """Single entry point. Returns a (value, validity) result, never raises.

    Shape:
        {"ok": True,  "kind": "arithmetic"|"symbolic", "result": {...}, "input": text}
        {"ok": False, "reason": "<safe message>", "input": text}

    The caller feeds result back to the model as a GROUNDED FACT to phrase — the
    model must not re-derive it. On {"ok": False} the model should say it could not
    compute it, NOT invent a number.
    """
    text = (text or "").strip()
    # Try exact arithmetic first (fast, no sympy).
    try:
        frac = safe_arithmetic(text)
        return {"ok": True, "kind": "arithmetic",
                "result": format_fraction(frac), "input": text}
    except MathError:
        pass
    # Fall back to symbolic (slower, guarded).
    try:
        return {"ok": True, "kind": "symbolic",
                "result": safe_symbolic(text), "input": text}
    except MathError as e:
        return {"ok": False, "reason": str(e), "input": text}
