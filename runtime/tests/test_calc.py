"""Tests for the CALC sandbox (roster/calc.py) — what it computes and, more importantly,
what it refuses."""

import pytest

from roster.calc import CalcError, evaluate

# ---- it computes -----------------------------------------------------------------


def test_arithmetic_and_helpers():
    assert evaluate("(7575.39 / 6900.0 - 1) * 100").startswith("9.78")
    assert evaluate("pct_change(19.9, 15.84)").startswith("-20.4")
    assert evaluate("mean([1, 2, 3, 4])") == "2.5"
    assert evaluate("round(stdev([10, 12, 23, 23, 16, 23, 21, 16]), 3)") == "5.237"


def test_drawdown_peak_to_trough():
    # Peak 100 → trough 50 = -50%, even with a later recovery.
    assert evaluate("round(drawdown([80, 100, 90, 50, 70]), 1)") == "-50.0"


def test_comprehensions_and_conditionals():
    assert evaluate("sum(v * 2 for v in [1, 2, 3])") == "12"
    assert evaluate("[v for v in [1, -2, 3] if v > 0]") == "[1, 3]"
    assert evaluate("'high' if max([15.8, 16.9]) > 30 else 'calm'") == "'calm'"


def test_subscripts_and_dicts():
    assert evaluate("sorted([3, 1, 2])[-1]") == "3"
    assert evaluate("{'a': 1, 'b': 2}['b']") == "2"


# ---- it refuses ------------------------------------------------------------------


@pytest.mark.parametrize(
    "evil",
    [
        "__import__('os').system('id')",  # unknown name + call
        "(1).__class__",  # attribute access
        "[].__class__.__mro__",  # dunder ladder
        "open('/etc/passwd')",  # unknown name
        "lambda: 1",  # lambda
        "x = 1",  # statement, not expression
        "f'{1:{__import__}}'",  # f-string smuggling
        "10 ** 999999",  # huge exponent
        "range(10**8)",  # memory blow via giant range
    ],
)
def test_rejects_escapes_and_bombs(evil):
    with pytest.raises(CalcError):
        evaluate(evil)


def test_math_errors_become_calc_errors():
    with pytest.raises(CalcError, match="ZeroDivisionError"):
        evaluate("1 / 0")
    with pytest.raises(CalcError, match="pct_change"):
        evaluate("pct_change(0, 5)")


def test_unknown_name_lists_available_helpers():
    with pytest.raises(CalcError, match="pct_change"):
        evaluate("nonexistent_fn(1)")
