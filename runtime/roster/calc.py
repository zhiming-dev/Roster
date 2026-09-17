"""Sandboxed calculation — the `CALC:` directive's backend.

A researcher that just FETCHed a CSV can compute a drawdown or a percent change without
round-tripping through the coder: one Python *expression*, validated against an AST
whitelist and evaluated in a namespace of math/statistics helpers. No statements, no
imports, no attribute access, no dunders — this is a calculator, not an interpreter.

Pure and stdlib-only, so it unit-tests without a runtime.
"""

from __future__ import annotations

import ast
import math
import statistics

MAX_EXPR_CHARS = 2_000
MAX_RESULT_CHARS = 2_000
# eval() guard rails: no huge exponents blowing the process (10**10**10 etc.).
_MAX_POW_EXP = 10_000


class CalcError(RuntimeError):
    """The expression was rejected or failed to evaluate."""


def _safe_range(*args: int) -> range:
    r = range(*args)
    if len(r) > 1_000_000:
        raise CalcError(f"range too large ({len(r)} items, max 1,000,000)")
    return r


def _pct_change(old: float, new: float) -> float:
    """Percent change from ``old`` to ``new`` (e.g. drawdowns: pct_change(peak, trough))."""
    if old == 0:
        raise CalcError("pct_change: old value is 0")
    return (new - old) / old * 100.0


def _drawdown(values) -> float:
    """Max peak-to-trough decline of a series, as a negative percentage."""
    vals = [float(v) for v in values]
    if not vals:
        raise CalcError("drawdown: empty series")
    peak = vals[0]
    worst = 0.0
    for v in vals:
        peak = max(peak, v)
        worst = min(worst, (v - peak) / peak * 100.0)
    return worst


# The complete namespace an expression may reference. Values are ordinary callables /
# constants; nothing here exposes attribute access, I/O, or the import machinery.
SAFE_NAMES: dict[str, object] = {
    # builtins (computation only)
    "abs": abs, "min": min, "max": max, "sum": sum, "len": len, "round": round,
    "sorted": sorted, "range": _safe_range, "zip": zip, "enumerate": enumerate,
    "float": float, "int": int, "str": str, "bool": bool, "list": list,
    "tuple": tuple, "dict": dict, "set": set, "any": any, "all": all,
    "divmod": divmod, "reversed": reversed,
    # math
    "sqrt": math.sqrt, "log": math.log, "log2": math.log2, "log10": math.log10,
    "exp": math.exp, "floor": math.floor, "ceil": math.ceil, "pow": pow,
    "pi": math.pi, "e": math.e, "inf": math.inf, "nan": math.nan,
    "isnan": math.isnan, "fabs": math.fabs, "fsum": math.fsum, "prod": math.prod,
    # statistics
    "mean": statistics.mean, "median": statistics.median, "mode": statistics.mode,
    "stdev": statistics.stdev, "pstdev": statistics.pstdev,
    "variance": statistics.variance, "pvariance": statistics.pvariance,
    "quantiles": statistics.quantiles, "correlation": statistics.correlation,
    # finance helpers
    "pct_change": _pct_change, "drawdown": _drawdown,
}

# AST node types an expression may contain. Notably ABSENT: Attribute (blocks every
# `x.__class__`-style escape in one stroke), Import*, Lambda, Await, NamedExpr,
# FormattedValue/JoinedStr (f-strings can smuggle attribute access via format specs).
_ALLOWED_NODES: tuple[type, ...] = (
    ast.Expression,
    ast.Constant,
    ast.Name, ast.Load,
    ast.BinOp, ast.UnaryOp, ast.BoolOp, ast.Compare, ast.IfExp,
    ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.Pow,
    ast.USub, ast.UAdd, ast.Not, ast.And, ast.Or,
    ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE, ast.In, ast.NotIn,
    ast.Is, ast.IsNot,
    ast.Call, ast.keyword, ast.Starred,
    ast.List, ast.Tuple, ast.Dict, ast.Set,
    ast.Subscript, ast.Slice, ast.Index if hasattr(ast, "Index") else ast.Slice,
    ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp, ast.comprehension,
    ast.Store,  # comprehension loop variables bind with Store context
)


def validate(expr: str) -> ast.Expression:
    """Parse and whitelist-check one expression; raises :class:`CalcError` on anything
    outside the calculator subset."""
    if len(expr) > MAX_EXPR_CHARS:
        raise CalcError(f"expression too long ({len(expr)} chars, max {MAX_EXPR_CHARS})")
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as exc:
        raise CalcError(f"not a valid Python expression: {exc.msg}") from exc

    # Pass 1: collect comprehension loop variables (`v` in `[v*2 for v in ...]`) — they
    # must be known before pass 2 sees their Load sites, and ast.walk visits an
    # expression's uses before the comprehension that binds them.
    bound: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.comprehension):
            for t in ast.walk(node.target):
                if isinstance(t, ast.Name):
                    bound.add(t.id)

    for node in ast.walk(tree):
        if not isinstance(node, _ALLOWED_NODES):
            raise CalcError(
                f"disallowed syntax: {type(node).__name__}. CALC takes a single "
                "expression — no attribute access, imports, lambdas, or statements."
            )
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            if node.id not in SAFE_NAMES and node.id not in bound:
                raise CalcError(
                    f"unknown name '{node.id}'. Available: numbers you type in, plus "
                    + ", ".join(sorted(SAFE_NAMES))
                )
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Pow):
            if isinstance(node.right, ast.Constant) and isinstance(
                node.right.value, (int, float)
            ):
                if abs(node.right.value) > _MAX_POW_EXP:
                    raise CalcError(f"exponent too large (max {_MAX_POW_EXP})")
    return tree


def evaluate(expr: str) -> str:
    """Validate and evaluate one expression; returns the result rendered as a string."""
    tree = validate(expr)
    try:
        result = eval(  # noqa: S307 — input is AST-whitelisted above
            compile(tree, "<calc>", "eval"), {"__builtins__": {}}, dict(SAFE_NAMES)
        )
    except CalcError:
        raise
    except Exception as exc:  # noqa: BLE001 — math errors become agent feedback
        raise CalcError(f"{type(exc).__name__}: {exc}") from exc
    text = repr(result)
    if len(text) > MAX_RESULT_CHARS:
        text = text[:MAX_RESULT_CHARS] + f"… [truncated, {len(text)} chars total]"
    return text
