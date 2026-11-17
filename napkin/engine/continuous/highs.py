"""The linear programs of the boundary allocation (`fields.Field._linear_program`), solved as
`scipy.optimize.linprog(..., method='highs')` solves them, without the cost of its wrapper.

linprog converts and checks its inputs, gives the HiGHS solver that SciPy bundles five option
values through a checker of each option, solves, and checks the solution against the bounds and
the constraints. For a program of the allocation, that wrapper takes longer than the solver.
`solve` gives the same arrays and the same option values to the same solver, a new instance for
each program, and decides success with the same check, so each solution is linprog's, bit for bit.
Every other case goes to linprog itself, which gives its own result and messages: an input that is
not finite or not of the shapes that the allocation makes, a status of the solver that is not
optimal, and a solution that fails the check. The module reads SciPy's private interface to HiGHS
(`scipy.optimize._highspy`); a test compares `solve` with linprog on many programs
(tests/engine/test_highs.py).
"""

from __future__ import annotations

import math

import numpy as np
from scipy.optimize import OptimizeResult, linprog
from scipy.optimize._highspy import _core as highs

# The option values that linprog gives HiGHS for method='highs' with its defaults
# (`scipy.optimize._linprog_highs`); every other option keeps the solver's default. The solver
# copies them from this object, which nothing changes.
OPTIONS = highs.HighsOptions()
OPTIONS.presolve = 'on'
OPTIONS.highs_debug_level = highs.HighsDebugLevel.kHighsDebugLevelNone
OPTIONS.log_to_console = False
OPTIONS.output_flag = False
OPTIONS.simplex_strategy = highs.simplex_constants.SimplexStrategy.kSimplexStrategyDual
# The solver's tolerance for a satisfied bound: a solution may lie this far past it, in the units of
# the variables (served fractions from 0 to 1 at a boundary allocation).
FEASIBILITY = OPTIONS.primal_feasibility_tolerance
# linprog's check of a solution (`_check_result`), with its default tolerance of 1e-9.
TOLERANCE = np.sqrt(1e-9) * 10


def bounded(values):
    """Each infinite value as the solver's infinity, with its sign (linprog's `_replace_inf`). The
    solver's infinity is the float infinity in SciPy 1.18, so the values stay as they are there."""
    if highs.kHighsInf != math.inf:
        infinite = np.isinf(values)
        values[infinite] = np.sign(values[infinite]) * highs.kHighsInf
    return values


def columns(matrix):
    """The arrays of `scipy.sparse.csc_array(matrix)` for a dense float matrix: for each column,
    the rows of its nonzero entries in increasing order, and their values."""
    column, row = np.nonzero(matrix.T)
    start = np.zeros(matrix.shape[1] + 1, dtype=np.int32)
    np.cumsum(np.bincount(column, minlength=matrix.shape[1]), out=start[1:])
    return start, row.astype(np.int32), matrix[row, column]


def solve(c, a_ub, b_ub, a_eq, b_eq, bounds):
    """`linprog(c, A_ub=a_ub, b_ub=b_ub, A_eq=a_eq, b_eq=b_eq, bounds=bounds, method='highs')`:
    its `x` and `success`, and its whole result when it does not succeed."""

    def fallback():
        return linprog(c, A_ub=a_ub, b_ub=b_ub, A_eq=a_eq, b_eq=b_eq, bounds=bounds, method='highs')

    cost = np.array(c, dtype=float).reshape(-1)
    upper_rows = np.array(a_ub, dtype=float)
    upper_limits = np.array(b_ub, dtype=float).reshape(-1)
    count = len(cost)
    equal_rows = np.zeros((0, count)) if a_eq is None else np.array(a_eq, dtype=float)
    equal_values = np.array([], dtype=float) if b_eq is None else np.array(b_eq, dtype=float).reshape(-1)
    limits = np.array(bounds, dtype=float)
    if (
        count == 0
        or upper_rows.shape != (len(upper_limits), count)
        or equal_rows.shape != (len(equal_values), count)
        or limits.shape != (count, 2)
        or not all(
            np.isfinite(part).all() for part in (cost, upper_rows, upper_limits, equal_rows, equal_values)
        )
        or np.isnan(limits).any()
    ):
        return fallback()
    start, index, value = columns(np.vstack((upper_rows, equal_rows)))
    rhs = bounded(np.concatenate((upper_limits, equal_values)))
    lp = highs.HighsLp()
    lp.num_col_ = count
    lp.num_row_ = len(rhs)
    lp.a_matrix_.num_col_ = count
    lp.a_matrix_.num_row_ = len(rhs)
    lp.a_matrix_.format_ = highs.MatrixFormat.kColwise
    lp.col_cost_ = cost
    lp.col_lower_ = bounded(limits[:, 0].copy())
    lp.col_upper_ = bounded(limits[:, 1].copy())
    lp.row_lower_ = bounded(np.concatenate((np.full(len(upper_limits), -math.inf), equal_values)))
    lp.row_upper_ = rhs
    lp.a_matrix_.start_ = start
    lp.a_matrix_.index_ = index
    lp.a_matrix_.value_ = value
    solver = highs._Highs()
    error = highs.HighsStatus.kError
    if solver.passOptions(OPTIONS) == error or solver.passModel(lp) == error or solver.run() == error:
        return fallback()
    if solver.getModelStatus() != highs.HighsModelStatus.kOptimal:
        return fallback()
    objective = solver.getInfo().objective_function_value
    solution = solver.getSolution()
    x = np.array(solution.col_value)
    slack = rhs - solution.row_value
    residual, slack = slack[len(upper_limits) :], slack[: len(upper_limits)]
    if (
        np.isnan(x).any()
        or np.isnan(objective)
        or np.isnan(slack).any()
        or np.isnan(residual).any()
        or not np.all((x >= limits[:, 0] - TOLERANCE) & (x <= limits[:, 1] + TOLERANCE))
        or (slack < -TOLERANCE).any()
        or (np.abs(residual) > TOLERANCE).any()
    ):
        return fallback()
    return OptimizeResult(x=x, fun=objective, status=0, success=True)
