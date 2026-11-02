"""Private fresh-process worker. Apply limits before importing SymPy."""

import json
import math
import resource
import sys
from pathlib import Path


def main():
    # Hard limits cannot be raised by later library code in this process.
    limits = (
        (resource.RLIMIT_CPU, 2),
        (resource.RLIMIT_AS, 512 * 1024 * 1024),
        (resource.RLIMIT_FSIZE, 0),
        (resource.RLIMIT_CORE, 0),
        (resource.RLIMIT_NOFILE, 32),
        (resource.RLIMIT_STACK, 16 * 1024 * 1024),
    )
    for kind, value in limits:
        resource.setrlimit(kind, (value, value))
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import ast

    import safe_math as guard

    payload = json.loads(sys.stdin.read(2048))
    sides = payload["sides"]
    if (
        not isinstance(sides, list)
        or not 1 <= len(sides) <= 2
        or any(not isinstance(s, str) or "=" in s for s in sides)
    ):
        raise guard.MathError("invalid worker request")
    # Revalidate each actual expression received, not an earlier untransformed copy.
    trees = [guard._parse_validated(side, symbolic=True) for side in sides]
    target_name = payload.get("solve_for")
    guard._validated_sides("=".join(sides), target_name)
    import sympy as sp

    funcs = {
        name: getattr(sp, "Abs" if name == "abs" else "log" if name == "ln" else name)
        for name in guard._ALLOWED_FUNCS
    }
    constants = {"pi": sp.pi, "e": sp.E, "E": sp.E}

    def build(node, source):
        if isinstance(node, ast.Expression):
            return build(node.body, source)
        if isinstance(node, ast.Constant):
            value = guard._number(node, source)
            return sp.Rational(value.numerator, value.denominator)
        if isinstance(node, ast.Name):
            return constants.get(node.id, sp.Symbol(node.id))
        if isinstance(node, ast.UnaryOp):
            value = build(node.operand, source)
            return value if isinstance(node.op, ast.UAdd) else -value
        if isinstance(node, ast.Call):
            return funcs[node.func.id](*(build(a, source) for a in node.args))
        a, b = build(node.left, source), build(node.right, source)
        if isinstance(node.op, ast.Add):
            return a + b
        if isinstance(node.op, ast.Sub):
            return a - b
        if isinstance(node.op, ast.Mult):
            return a * b
        if isinstance(node.op, ast.Div):
            return a / b
        if isinstance(node.op, ast.FloorDiv):
            return sp.floor(a / b)
        if isinstance(node.op, ast.Mod):
            return sp.Mod(a, b)
        if isinstance(node.op, ast.Pow):
            return a**b
        raise guard.MathError("invalid worker node")

    values = [build(tree, source) for source, tree in trees]
    if len(values) == 2:
        expression = values[0] - values[1]
        symbols = sorted(expression.free_symbols, key=str)
        target = (
            sp.Symbol(target_name)
            if target_name
            else symbols[0]
            if len(symbols) == 1
            else None
        )
        if target is None or target not in symbols:
            raise guard.MathError("ambiguous solve variable")
        solutions = sp.solve(expression, target, dict=False)
        if len(solutions) > 32:
            raise guard.MathError("too many solutions")
        result = {
            "type": "solve",
            "variable": str(target),
            "solutions": [str(v) for v in solutions],
        }
    else:
        value = sp.simplify(values[0])
        if value.has(sp.zoo, sp.nan, sp.oo, -sp.oo):
            raise guard.MathError("undefined value")
        result = {"type": "expr", "simplified": str(value)}
        if not value.free_symbols:
            result["numeric"] = str(value.evalf(15))
    output = json.dumps({"ok": True, "result": result})
    if len(output) > guard.MAX_WORKER_OUTPUT:
        raise guard.MathError("output too large")
    print(output)


if __name__ == "__main__":
    try:
        main()
    except Exception:  # noqa: BLE001 - worker errors must fail closed without traceback data
        print('{"ok":false}')
