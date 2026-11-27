"""Restricted exact arithmetic and symbolic math for untrusted expressions.

The security boundary has two layers: a Python AST allowlist followed by
``sympy.parse_expr`` with deliberately small local and global namespaces.
Symbolic work also has a wall-clock timeout. Python cannot terminate a
CPU-bound thread safely, so the timeout is only a secondary backstop; the AST,
length, exponent, node-count, and result-size restrictions are the real
resource protection.
"""

from __future__ import annotations

import ast
import keyword
import math
import queue
import re
import threading
from collections.abc import Callable
from decimal import Decimal, InvalidOperation, localcontext
from fractions import Fraction
from typing import TypeVar

import sympy
from sympy.parsing.sympy_parser import parse_expr, rationalize, standard_transformations

MAX_EXPR_LEN = 512
MAX_SYMBOLIC_LEN = 256
MAX_POW_EXPONENT = 1_000
MAX_RESULT_BITS = 60_000
MAX_AST_DEPTH = 60
SYMBOLIC_TIMEOUT_S = 2.0

_MAX_AST_NODES = 256
_MAX_SYMBOLS = 4
_MAX_SOLUTIONS = 32
_MAX_RENDERED_RESULT = 8_192
_SYMBOLIC_SLOTS = threading.BoundedSemaphore(4)

_ALLOWED_BINOPS = (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.Pow)
_ALLOWED_FUNCTIONS = {
    "sqrt": sympy.sqrt,
    "sin": sympy.sin,
    "cos": sympy.cos,
    "tan": sympy.tan,
    "asin": sympy.asin,
    "acos": sympy.acos,
    "atan": sympy.atan,
    "log": sympy.log,
    "ln": sympy.log,
    "exp": sympy.exp,
    "Abs": sympy.Abs,
    "abs": sympy.Abs,
}
_ALLOWED_CONSTANTS = {"pi": sympy.pi, "e": sympy.E, "E": sympy.E}
_FUNCTION_ARITIES = {name: {1} for name in _ALLOWED_FUNCTIONS}
_FUNCTION_ARITIES["log"] = {1, 2}
_FUNCTION_ARITIES["ln"] = {1, 2}

_VARIABLE_RE = re.compile(r"[A-Za-z][A-Za-z0-9]{0,9}\Z", re.ASCII)
_ALLOWED_CHARS_RE = re.compile(r"[0-9A-Za-z_+\-*/%().,^= \t]+\Z", re.ASCII)
_SUSPICIOUS = ("__", "import", "lambda", "eval", "exec", "compile")
_DENIED_NAMES = {
    "builtins",
    "open",
    "print",
    "globals",
    "locals",
    "vars",
    "getattr",
    "setattr",
    "delattr",
    "type",
    "object",
    "classmethod",
    "staticmethod",
    "help",
    "input",
    "breakpoint",
    "memoryview",
    "super",
    "True",
    "False",
    "None",
    "nan",
    "oo",
    "zoo",
    "inf",
    "Infinity",
}
_MATH_HINT = re.compile(
    r"\d\s*(?:\*\*|[-+*/%^])\s*\d|=|"
    r"\b(?:solve|simplify|evaluate|compute|sqrt|sin|cos|tan|log|ln|exp)\b|"
    r"\d\s*%|\bpercent\b",
    re.IGNORECASE | re.ASCII,
)

_TRANSFORMATIONS = standard_transformations + (rationalize,)
_SYMPY_GLOBALS = {
    "__builtins__": {},
    "Integer": sympy.Integer,
    "Rational": sympy.Rational,
    "Float": sympy.Float,
    "Symbol": sympy.Symbol,
}


class MathError(Exception):
    """A safe, user-presentable refusal or computation error."""


def _guard_fraction(value: Fraction) -> Fraction:
    if (
        max(abs(value.numerator).bit_length(), value.denominator.bit_length())
        > MAX_RESULT_BITS
    ):
        raise MathError("result too large")
    return value


def _constant_fraction(node: ast.Constant, source: str) -> Fraction:
    value = node.value
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise MathError("only real numeric literals are allowed")
    if isinstance(value, int):
        return _guard_fraction(Fraction(value))
    if not math.isfinite(value):
        raise MathError("non-finite numbers are not allowed")
    token = ast.get_source_segment(source, node)
    if token is None:
        raise MathError("invalid numeric literal")
    try:
        decimal = Decimal(token.replace("_", ""))
    except InvalidOperation:
        raise MathError("invalid numeric literal") from None
    if abs(decimal.as_tuple().exponent) > MAX_POW_EXPONENT:
        raise MathError("numeric exponent too large")
    return _guard_fraction(Fraction(decimal))


def _safe_pow(base: Fraction, exponent: Fraction) -> Fraction:
    if exponent.denominator != 1:
        raise MathError("non-rational power requires symbolic evaluation")
    power = exponent.numerator
    if abs(power) > MAX_POW_EXPONENT:
        raise MathError("exponent too large")
    if base == 0 and power < 0:
        raise MathError("division by zero")
    base_bits = max(abs(base.numerator).bit_length(), base.denominator.bit_length(), 1)
    if abs(power) * base_bits > MAX_RESULT_BITS:
        raise MathError("result too large")
    return _guard_fraction(base**power)


def _eval_arithmetic(node: ast.AST, source: str) -> Fraction:
    if isinstance(node, ast.Expression):
        return _eval_arithmetic(node.body, source)
    if isinstance(node, ast.Constant):
        return _constant_fraction(node, source)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        value = _eval_arithmetic(node.operand, source)
        return value if isinstance(node.op, ast.UAdd) else -value
    if not isinstance(node, ast.BinOp) or not isinstance(node.op, _ALLOWED_BINOPS):
        raise MathError("not a pure arithmetic expression")

    left = _eval_arithmetic(node.left, source)
    right = _eval_arithmetic(node.right, source)
    try:
        if isinstance(node.op, ast.Add):
            result = left + right
        elif isinstance(node.op, ast.Sub):
            result = left - right
        elif isinstance(node.op, ast.Mult):
            result = left * right
        elif isinstance(node.op, ast.Div):
            result = left / right
        elif isinstance(node.op, ast.FloorDiv):
            result = Fraction(left // right)
        elif isinstance(node.op, ast.Mod):
            result = left % right
        else:
            result = _safe_pow(left, right)
    except ZeroDivisionError:
        raise MathError("division by zero") from None
    return _guard_fraction(result)


def _is_variable_name(name: str) -> bool:
    return bool(
        _VARIABLE_RE.fullmatch(name)
        and name not in _DENIED_NAMES
        and not keyword.iskeyword(name)
        and not any(token in name.lower() for token in _SUSPICIOUS)
    )


def _validate_ast(
    node: ast.AST, source: str, *, symbolic: bool, depth: int = 0
) -> None:
    if depth > MAX_AST_DEPTH:
        raise MathError("expression too deeply nested")

    def child(value: ast.AST) -> None:
        _validate_ast(value, source, symbolic=symbolic, depth=depth + 1)

    if isinstance(node, ast.Expression):
        child(node.body)
        return
    if isinstance(node, ast.Constant):
        _constant_fraction(node, source)
        return
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        child(node.operand)
        return
    if isinstance(node, ast.BinOp) and isinstance(node.op, _ALLOWED_BINOPS):
        if isinstance(node.op, ast.Pow):
            if any(
                isinstance(part, ast.Pow)
                for branch in (node.left, node.right)
                for part in ast.walk(branch)
            ):
                raise MathError("nested exponentiation is not allowed")
            try:
                exponent = _eval_arithmetic(node.right, source)
            except MathError as exc:
                raise MathError(
                    "power exponent must be bounded numeric arithmetic"
                ) from exc
            if abs(exponent) > MAX_POW_EXPONENT:
                raise MathError("exponent too large")
            if exponent.denominator == 1 and not any(
                isinstance(part, (ast.Name, ast.Call)) for part in ast.walk(node.left)
            ):
                _safe_pow(_eval_arithmetic(node.left, source), exponent)
        child(node.left)
        child(node.right)
        if (
            isinstance(node.op, (ast.Div, ast.FloorDiv, ast.Mod))
            and not any(
                isinstance(part, (ast.Name, ast.Call)) for part in ast.walk(node.right)
            )
            and _eval_arithmetic(node.right, source) == 0
        ):
            raise MathError("division by zero")
        return
    if symbolic and isinstance(node, ast.Name):
        if node.id in _ALLOWED_CONSTANTS:
            return
        if node.id in _ALLOWED_FUNCTIONS:
            raise MathError("function requires arguments")
        if _is_variable_name(node.id):
            return
        raise MathError("invalid variable name")
    if symbolic and isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        name = node.func.id
        if name not in _ALLOWED_FUNCTIONS:
            raise MathError("function is not allowed")
        if node.keywords or any(isinstance(arg, ast.Starred) for arg in node.args):
            raise MathError("keyword and starred arguments are not allowed")
        if len(node.args) not in _FUNCTION_ARITIES[name]:
            raise MathError("invalid function arguments")
        for argument in node.args:
            child(argument)
        return
    raise MathError("disallowed syntax")


def _prepare_side(expr: str, *, symbolic: bool) -> tuple[str, ast.Expression]:
    limit = MAX_SYMBOLIC_LEN if symbolic else MAX_EXPR_LEN
    if not isinstance(expr, str) or not expr.strip():
        raise MathError("expression must be non-empty text")
    if len(expr) > limit:
        raise MathError("expression too long")
    if any(token in expr.lower() for token in _SUSPICIOUS):
        raise MathError("suspicious input is not allowed")
    if not _ALLOWED_CHARS_RE.fullmatch(expr):
        raise MathError("disallowed character")
    source = expr.strip().replace("^", "**")
    nesting = 0
    for character in source:
        if character == "(":
            nesting += 1
            if nesting > MAX_AST_DEPTH:
                raise MathError("expression too deeply nested")
        elif character == ")":
            nesting -= 1
            if nesting < 0:
                raise MathError("could not parse expression")
    if nesting:
        raise MathError("could not parse expression")
    if "=" in source:
        raise MathError("equality must separate two expressions")
    try:
        tree = ast.parse(source, mode="eval")
    except (SyntaxError, ValueError, RecursionError):
        raise MathError("could not parse expression") from None
    if sum(1 for _ in ast.walk(tree)) > _MAX_AST_NODES:
        raise MathError("too many expression nodes")
    _validate_ast(tree, source, symbolic=symbolic)
    return source, tree


def _prepare_equation(expr: str) -> list[tuple[str, ast.Expression]]:
    if not isinstance(expr, str) or not expr.strip():
        raise MathError("expression must be non-empty text")
    if len(expr) > MAX_SYMBOLIC_LEN:
        raise MathError("expression too long")
    if expr.count("=") > 1:
        raise MathError("only one equality sign is allowed")
    parts = expr.split("=")
    if any(not part.strip() for part in parts):
        raise MathError("malformed equation")
    return [_prepare_side(part, symbolic=True) for part in parts]


def safe_arithmetic(expr: str) -> Fraction:
    """Evaluate bounded arithmetic exactly as a :class:`Fraction`."""

    source, tree = _prepare_side(expr, symbolic=False)
    return _eval_arithmetic(tree, source)


def _parse_restricted(source: str):
    local_dict = dict(_ALLOWED_FUNCTIONS)
    local_dict.update(_ALLOWED_CONSTANTS)
    return parse_expr(
        source,
        local_dict=local_dict,
        global_dict=dict(_SYMPY_GLOBALS),
        transformations=_TRANSFORMATIONS,
        evaluate=True,
    )


def _symbolic_work(
    prepared: list[tuple[str, ast.Expression]], solve_for: str | None
) -> dict:
    values = [_parse_restricted(source) for source, _ in prepared]
    symbols = set().union(*(value.free_symbols for value in values))
    if len(symbols) > _MAX_SYMBOLS:
        raise MathError("too many variables")

    if len(values) == 2:
        equation = values[0] - values[1]
        equation_symbols = equation.free_symbols
        if solve_for is None:
            if len(equation_symbols) != 1:
                raise MathError("ambiguous solve variable")
            target = next(iter(equation_symbols))
        else:
            target = sympy.Symbol(solve_for)
            if target not in equation_symbols:
                raise MathError("solve variable is not present")
        try:
            polynomial = sympy.Poly(equation, target)
        except sympy.PolynomialError:
            raise MathError("only bounded polynomial equations can be solved") from None
        if polynomial.degree() > 8:
            raise MathError("equation degree is too large")
        solutions = sympy.solve(equation, target, dict=False)
        if len(solutions) > _MAX_SOLUTIONS:
            raise MathError("too many solutions")
        rendered = [str(solution) for solution in solutions]
        if sum(map(len, rendered)) > _MAX_RENDERED_RESULT:
            raise MathError("result too large")
        return {"type": "solve", "variable": str(target), "solutions": rendered}

    if solve_for is not None:
        raise MathError("solve_for requires an equation")
    value = sympy.simplify(values[0])
    if value.has(sympy.zoo, sympy.nan, sympy.oo, -sympy.oo):
        raise MathError("undefined value")
    rendered = str(value)
    if len(rendered) > _MAX_RENDERED_RESULT:
        raise MathError("result too large")
    result = {"type": "expr", "simplified": rendered}
    if not value.free_symbols:
        numeric = str(value.evalf(15))
        if len(numeric) > _MAX_RENDERED_RESULT:
            raise MathError("result too large")
        result["numeric"] = numeric
    return result


_T = TypeVar("_T")


def _run_with_timeout(function: Callable[[], _T]) -> _T:
    if not _SYMBOLIC_SLOTS.acquire(blocking=False):
        raise MathError("symbolic evaluator is busy")
    outcome: queue.Queue[tuple[bool, object]] = queue.Queue(maxsize=1)

    def worker() -> None:
        try:
            outcome.put((True, function()))
        except Exception as exc:  # noqa: BLE001 - worker must relay all failures
            outcome.put((False, exc))
        finally:
            _SYMBOLIC_SLOTS.release()

    thread = threading.Thread(target=worker, name="safe-math-symbolic", daemon=True)
    thread.start()
    try:
        succeeded, value = outcome.get(timeout=SYMBOLIC_TIMEOUT_S)
    except queue.Empty:
        raise MathError("symbolic computation exceeded time limit") from None
    if succeeded:
        return value  # type: ignore[return-value]
    if isinstance(value, MathError):
        raise value
    raise MathError("symbolic computation failed")


def safe_symbolic(expr: str, *, solve_for: str | None = None) -> dict:
    """Simplify or solve a validated symbolic expression."""

    if solve_for is not None and (
        not isinstance(solve_for, str)
        or not _is_variable_name(solve_for)
        or solve_for in _ALLOWED_FUNCTIONS
        or solve_for in _ALLOWED_CONSTANTS
    ):
        raise MathError("invalid solve variable")
    prepared = _prepare_equation(expr)
    return _run_with_timeout(lambda: _symbolic_work(prepared, solve_for))


def looks_like_math(text: str) -> bool:
    """Conservatively identify text that may contain a math request."""

    return (
        isinstance(text, str) and len(text) <= 4_096 and bool(_MATH_HINT.search(text))
    )


def _format_fraction(value: Fraction, significant_digits: int = 12) -> dict[str, str]:
    exact = (
        str(value.numerator)
        if value.denominator == 1
        else f"{value.numerator}/{value.denominator}"
    )
    if value.denominator == 1:
        return {"exact": exact, "approx": exact}
    with localcontext() as context:
        context.prec = significant_digits
        approx = str(
            (Decimal(value.numerator) / Decimal(value.denominator)).normalize()
        )
    return {"exact": exact, "approx": approx}


def compute(text: str) -> dict:
    """Compute an untrusted expression without exposing internal exceptions."""

    if not isinstance(text, str):
        return {"ok": False, "reason": "expression must be text", "input": None}
    original = text.strip()
    try:
        prepared = _prepare_equation(original)
        is_symbolic = len(prepared) == 2 or any(
            isinstance(node, (ast.Name, ast.Call))
            for _, tree in prepared
            for node in ast.walk(tree)
        )
        if not is_symbolic:
            try:
                value = safe_arithmetic(original)
            except MathError as exc:
                if str(exc) != "non-rational power requires symbolic evaluation":
                    raise
                is_symbolic = True
        if is_symbolic:
            return {
                "ok": True,
                "kind": "symbolic",
                "result": safe_symbolic(original),
                "input": original,
            }
        return {
            "ok": True,
            "kind": "arithmetic",
            "result": _format_fraction(value),
            "input": original,
        }
    except MathError as exc:
        return {"ok": False, "reason": str(exc), "input": original}
    except Exception:  # noqa: BLE001 - public math API must never leak exceptions
        return {"ok": False, "reason": "computation failed safely", "input": original}
