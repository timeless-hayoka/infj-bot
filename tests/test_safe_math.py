"""Correctness and adversarial contracts; errors and crashes are not test passes."""

import json
import os
import subprocess
import sys
import time
from fractions import Fraction
from pathlib import Path

import pytest

from drift.core import safe_math as math


@pytest.mark.parametrize(
    "expression,exact",
    [
        ("2+2", "4"),
        ("2*3+4", "10"),
        ("3/4+1/4", "1"),
        ("1/3+1/3+1/3", "1"),
        ("0.1+0.2", "3/10"),
        ("2**10", "1024"),
        ("-5+3", "-2"),
        ("7//2", "3"),
        ("7%3", "1"),
        ("10**-2", "1/100"),
        ("0.10000000000000001", "10000000000000001/100000000000000000"),
        ("2^3", "8"),
        ("1e-12", "1/1000000000000"),
    ],
)
def test_exact_arithmetic(expression, exact):
    result = math.compute(expression)
    assert result["ok"], result
    assert result["kind"] == "arithmetic"
    assert result["result"]["exact"] == exact


@pytest.mark.parametrize(
    "expression,solutions", [("x**2-4=0", ["-2", "2"]), ("2*x+6=0", ["-3"])]
)
def test_solve(expression, solutions):
    result = math.compute(expression)
    assert result["ok"], result
    assert result["result"]["solutions"] == solutions


@pytest.mark.parametrize(
    "expression,simplified",
    [
        ("sqrt(16)", "4"),
        ("(x+1)**2", "(x + 1)**2"),
        ("sin(pi/2)", "1"),
        ("2**(1/2)", "sqrt(2)"),
        ("0.1+x", "x + 1/10"),
    ],
)
def test_symbolic(expression, simplified):
    result = math.compute(expression)
    assert result["ok"], result
    assert result["result"]["simplified"] == simplified


ADVERSARIAL = [
    "__import__('os').system('id')",
    "(1).__class__",
    "().__class__.__bases__[0].__subclasses__()",
    "eval('1+1')",
    "exec('x=1')",
    "lambda:1",
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
    "x+9**9**9",
    "x+2**99999999",
    "x+True",
    "sqrt(x=2)",
    "sin()",
    "sin(1,2)",
    "Symbol(x)",
    "x[0]",
    "(x:=1)",
    "1e999999999",
    "1e-999999999",
    "nan",
    "oo",
]


@pytest.mark.parametrize("expression", ADVERSARIAL)
def test_adversarial_rejected(expression):
    result = math.compute(expression)
    assert result["ok"] is False, result
    assert result["reason"]


def test_unknown_names_are_symbols_not_python_names():
    assert (
        math.compute("builtins+1")["ok"] is True
    )  # inert Symbol, never resolved Python name
    assert math.compute("builtins(1)")["ok"] is False


def test_invalid_solve_target():
    with pytest.raises(math.MathError):
        math.safe_symbolic("x=1", solve_for="x.__class__")


def test_no_global_decimal_mutation():
    from decimal import getcontext

    before = getcontext().prec
    math.format_fraction(Fraction(1, 3))
    assert getcontext().prec == before


def test_arithmetic_rejection_never_enters_worker(monkeypatch):
    def fail(*args, **kwargs):
        pytest.fail("unsafe arithmetic reached worker")

    monkeypatch.setattr(math.subprocess, "Popen", fail)
    for expression in ["9**9**9", "x+9**9**9", "2**99999999", "1/0", "x+1/0"]:
        assert not math.compute(expression)["ok"]


def test_actual_normalized_ast_validated():
    assert math.compute("x^2=4")["result"]["solutions"] == ["-2", "2"]
    assert not math.compute("x^999999999")["ok"]
    assert not math.compute("x^__import__(1)")["ok"]


@pytest.mark.skipif(os.name != "posix", reason="POSIX worker resource limits")
def test_wall_timeout_reaps_real_worker(monkeypatch):
    processes = []
    popen = subprocess.Popen

    def record(*args, **kwargs):
        process = popen(*args, **kwargs)
        processes.append(process)
        return process

    monkeypatch.setattr(math.subprocess, "Popen", record)
    monkeypatch.setattr(math, "SYMBOLIC_TIMEOUT_S", 0.001)
    start = time.monotonic()
    with pytest.raises(math.MathError, match="time budget"):
        math.safe_symbolic("sqrt(16)")
    assert time.monotonic() - start < 2
    assert len(processes) == 1 and processes[0].poll() is not None
    # A later request works; no abandoned worker or leaked admission slot.
    monkeypatch.setattr(math, "SYMBOLIC_TIMEOUT_S", 3)
    assert math.compute("sqrt(16)")["ok"]


def test_worker_revalidates_actual_payload():
    worker = Path(math.__file__).with_name("_safe_math_worker.py")
    run = subprocess.run(
        check=False,
        args=[sys.executable, "-I", str(worker)],
        input=json.dumps({"sides": ["x.__class__"]}),
        text=True,
        capture_output=True,
        timeout=5,
    )
    assert run.returncode == 0
    assert json.loads(run.stdout) == {"ok": False}


def test_worker_busy_fails_closed():
    for _ in range(4):
        assert math._WORKERS.acquire(blocking=False)
    try:
        with pytest.raises(math.MathError, match="busy"):
            math.safe_symbolic("sqrt(16)")
    finally:
        for _ in range(4):
            math._WORKERS.release()


def test_non_text_input_is_safe_error():
    for value in [None, 5, [], {}]:
        assert math.compute(value)["ok"] is False


@pytest.mark.skipif(os.name != "posix", reason="POSIX resource limits")
def test_real_worker_applies_hard_limits(tmp_path):
    worker = Path(math.__file__).with_name("_safe_math_worker.py")
    # Observe the actual limits at the symbolic operation seam in the real worker.
    wrapper = tmp_path / "limits.py"
    wrapper.write_text(
        "import sympy as sp, resource, runpy\n"
        "def inspect(value):\n"
        "    assert resource.getrlimit(resource.RLIMIT_CPU) == (2, 2)\n"
        "    assert resource.getrlimit(resource.RLIMIT_AS) == (536870912, 536870912)\n"
        "    assert resource.getrlimit(resource.RLIMIT_FSIZE) == (0, 0)\n"
        "    return sp.Integer(42)\n"
        "sp.simplify = inspect\n"
        f'runpy.run_path({str(worker)!r}, run_name="__main__")\n'
    )
    run = subprocess.run(
        check=False,
        args=[sys.executable, "-I", str(wrapper)],
        input=json.dumps({"sides": ["sqrt(16)"]}),
        text=True,
        capture_output=True,
        timeout=5,
    )
    assert run.returncode == 0, run.stderr
    assert json.loads(run.stdout)["result"]["simplified"] == "42"


@pytest.mark.skipif(os.name != "posix", reason="POSIX resource limits")
def test_cpu_limit_kills_expensive_symbolic_operation(tmp_path):
    worker = Path(math.__file__).with_name("_safe_math_worker.py")
    wrapper = tmp_path / "busy.py"
    wrapper.write_text(
        "import sympy as sp, runpy\n"
        "def busy(value):\n"
        "    while True: pass\n"
        "sp.simplify = busy\n"
        f'runpy.run_path({str(worker)!r}, run_name="__main__")\n'
    )
    run = subprocess.run(
        check=False,
        args=[sys.executable, "-I", str(wrapper)],
        input=json.dumps({"sides": ["sqrt(16)"]}),
        text=True,
        capture_output=True,
        timeout=6,
    )
    assert run.returncode < 0, (run.returncode, run.stdout, run.stderr)


@pytest.mark.skipif(os.name != "posix", reason="POSIX resource limits")
def test_memory_limit_refuses_expensive_symbolic_allocation(tmp_path):
    worker = Path(math.__file__).with_name("_safe_math_worker.py")
    wrapper = tmp_path / "memory.py"
    wrapper.write_text(
        "import sympy as sp, runpy\n"
        "def allocate(value):\n"
        "    return bytearray(1024 * 1024 * 1024)\n"
        "sp.simplify = allocate\n"
        f'runpy.run_path({str(worker)!r}, run_name="__main__")\n'
    )
    run = subprocess.run(
        check=False,
        args=[sys.executable, "-I", str(wrapper)],
        input=json.dumps({"sides": ["sqrt(16)"]}),
        text=True,
        capture_output=True,
        timeout=5,
    )
    assert run.returncode == 0, run.stderr
    assert json.loads(run.stdout) == {"ok": False}
