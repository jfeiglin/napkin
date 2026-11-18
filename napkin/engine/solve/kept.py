"""One HiGHS instance that a run keeps, with its program and its basis, and the QP of HiGHS.

    min c.x   with   row_lower <= A x <= row_upper,   lower <= x <= upper

This is the solver that SciPy bundles, read through SciPy's private interface
(`scipy.optimize._highspy`), as `napkin/engine/continuous/highs.py` reads it, on one thread. A `Kept`
instance belongs to one run of the engine and never to a compiled plan, so that the answers of a
sample do not depend on the samples solved before it. Costs, bounds, columns and rows change in
place, and each `run` starts from the basis of the last one. HiGHS marks its basis invalid after a
deletion, so `delete_cols` and `delete_rows` carry it over by hand (prototype A3: 300 flows that join
a kept program of 30,000 places cost 0.90 s, against 6.12 s for the program formed fresh).

The signs of HiGHS for a minimum: the dual of a column is its reduced cost d = c - A'y, at least zero
at a lower bound and at most zero at an upper bound; the dual y of a row is at least zero when the
row rests on its lower side and at most zero on its upper side.

`quadratic` solves the convex QP of a distance step on an instance of its own, the exact fallback of
the distance method.
"""

from __future__ import annotations

from contextlib import contextmanager

import numpy as np
import scipy.sparse as sp
from scipy.optimize._highspy import _core as highs

INF = highs.kHighsInf
Status = highs.HighsModelStatus
OPTIMAL, EMPTY = Status.kOptimal, Status.kModelEmpty
BASIC = highs.HighsBasisStatus.kBasic
AT_LOWER = highs.HighsBasisStatus.kLower
AT_UPPER = highs.HighsBasisStatus.kUpper
AT_ZERO = highs.HighsBasisStatus.kZero
ERROR = highs.HighsStatus.kError
PRIMAL_SIMPLEX = 4  # HiGHS's simplex_strategy for the primal simplex
# The tightest tolerances that HiGHS takes, for a second run whose duals must be exact (`Kept.tight`).
TIGHT = 1e-10


class Run:
    """What one run of HiGHS gives: its status, the values and duals of the columns and the rows, the
    objective, and the simplex iterations that it took."""

    def __init__(self, status, x, d, row_value, y, objective, iterations):
        self.status, self.x, self.d, self.row_value, self.y = status, x, d, row_value, y
        self.objective, self.iterations = objective, iterations


def _options():
    # The thread count is left at HiGHS's default, as linprog leaves it. The process has one pool of
    # threads, made by the first instance that runs; an instance that asks another count than that
    # pool's fails to solve. The simplex and the QP solver run serially either way.
    options = highs.HighsOptions()
    options.output_flag = False
    options.log_to_console = False
    return options


def _i32(values):
    return np.ascontiguousarray(values, dtype=np.int32)


def _f64(values):
    return np.ascontiguousarray(values, dtype=np.float64)


def _model(A, row_lower, row_upper, lower, upper, cost):
    A = sp.csc_array(A)
    A.sort_indices()
    m, n = A.shape
    lp = highs.HighsLp()
    lp.num_col_, lp.num_row_ = n, m
    lp.a_matrix_.num_col_, lp.a_matrix_.num_row_ = n, m
    lp.a_matrix_.format_ = highs.MatrixFormat.kColwise
    lp.a_matrix_.start_ = _i32(A.indptr)
    lp.a_matrix_.index_ = _i32(A.indices)
    lp.a_matrix_.value_ = _f64(A.data)
    lp.col_cost_ = _f64(cost)
    lp.col_lower_, lp.col_upper_ = _f64(lower), _f64(upper)
    lp.row_lower_, lp.row_upper_ = _f64(row_lower), _f64(row_upper)
    return lp


class Kept:
    """One HiGHS instance with its program and basis (see the module text)."""

    def __init__(self, A, row_lower, row_upper, lower, upper):
        self.m, self.n = A.shape
        self.s = highs._Highs()
        self.s.passOptions(_options())
        if self.s.passModel(_model(A, row_lower, row_upper, lower, upper, np.zeros(self.n))) == ERROR:
            raise ValueError('HiGHS refused the program')
        # the bounds that the instance holds, so that a change sends only what differs
        self.lower, self.upper = _f64(lower).copy(), _f64(upper).copy()
        self.row_lower, self.row_upper = _f64(row_lower).copy(), _f64(row_upper).copy()
        self.iterations = 0  # the simplex iterations of every run of the instance

    # -- changes in place --------------------------------------------------------------------------
    def set_cost(self, cost):
        """The whole cost vector."""
        if self.n:
            self.s.changeColsCost(self.n, _i32(np.arange(self.n)), _f64(cost))

    def set_bounds(self, index, lower, upper):
        """The bounds of the columns `index`."""
        index = _i32(index)
        if len(index):
            self.lower[index], self.upper[index] = lower, upper
            self.s.changeColsBounds(len(index), index, _f64(self.lower[index]), _f64(self.upper[index]))

    def set_row_bounds(self, index, lower, upper):
        """The bounds of the rows `index`."""
        index = np.asarray(index, dtype=np.int64)
        self.row_lower[index], self.row_upper[index] = lower, upper
        # the binding of SciPy changes the bounds of one row a call
        change = self.s.changeRowBounds
        for i, low, high in zip(
            index.tolist(), self.row_lower[index].tolist(), self.row_upper[index].tolist()
        ):
            change(i, low, high)

    def bounds(self, lower, upper):
        """Every column's bounds, sending only those that differ from the instance's."""
        changed = np.flatnonzero((self.lower != lower) | (self.upper != upper))
        self.set_bounds(changed, lower[changed], upper[changed])

    def row_bounds(self, lower, upper):
        """Every row's bounds, sending only those that differ from the instance's."""
        changed = np.flatnonzero((self.row_lower != lower) | (self.row_upper != upper))
        self.set_row_bounds(changed, lower[changed], upper[changed])

    def add_cols(self, lower, upper, columns):
        """New columns at the end, with zero cost; `columns` is a sparse matrix (rows x new columns).
        Gives their positions. A new column is not basic, so the basis stays valid."""
        k = len(lower)
        columns = sp.csc_array(columns)
        columns.sort_indices()
        if (
            self.s.addCols(
                k,
                _f64(np.zeros(k)),
                _f64(lower),
                _f64(upper),
                columns.nnz,
                _i32(columns.indptr[:-1]),
                _i32(columns.indices),
                _f64(columns.data),
            )
            == ERROR
        ):
            raise ValueError('HiGHS refused the new columns')
        self.lower, self.upper = np.r_[self.lower, lower], np.r_[self.upper, upper]
        first, self.n = self.n, self.n + k
        return np.arange(first, self.n)

    def add_rows(self, lower, upper, rows):
        """New rows at the end; `rows` is a sparse matrix (new rows x columns). Gives their positions.
        A new row is basic, so the basis stays valid."""
        rows = sp.csr_array(rows)
        rows.sort_indices()
        k = rows.shape[0]
        if (
            self.s.addRows(
                k,
                _f64(lower),
                _f64(upper),
                rows.nnz,
                _i32(rows.indptr[:-1]),
                _i32(rows.indices),
                _f64(rows.data),
            )
            == ERROR
        ):
            raise ValueError('HiGHS refused the new rows')
        self.row_lower, self.row_upper = np.r_[self.row_lower, lower], np.r_[self.row_upper, upper]
        first, self.m = self.m, self.m + k
        return np.arange(first, self.m)

    def delete_cols(self, index):
        """Delete columns and keep the basis: each deleted column that was basic gives its place to
        a row that was not."""
        index = np.unique(np.asarray(index, dtype=np.int64))
        if not len(index):
            return
        basis = self.s.getBasis()
        cols, rows = list(basis.col_status), list(basis.row_status)
        self.s.deleteCols(len(index), _i32(index))
        self.lower, self.upper = np.delete(self.lower, index), np.delete(self.upper, index)
        self.n -= len(index)
        if basis.valid:
            gone = set(index.tolist())
            lost = sum(1 for j in gone if cols[j] == BASIC)
            cols = [status for j, status in enumerate(cols) if j not in gone]
            for i, status in enumerate(rows):
                if not lost:
                    break
                if status != BASIC:
                    rows[i] = BASIC
                    lost -= 1
            self._set_basis(cols, rows)

    def delete_rows(self, index):
        """Delete rows and keep the basis: each deleted row that was not basic takes a basic column
        out of the basis, one of its own columns where one is basic."""
        index = np.unique(np.asarray(index, dtype=np.int64))
        if not len(index):
            return
        basis = self.s.getBasis()
        cols, rows = list(basis.col_status), list(basis.row_status)
        tight = [i for i in index.tolist() if rows[i] != BASIC] if basis.valid else []
        held = {i: [int(j) for j in self.s.getRowEntries(i)[1]] for i in tight}
        self.s.deleteRows(len(index), _i32(index))
        self.row_lower, self.row_upper = np.delete(self.row_lower, index), np.delete(self.row_upper, index)
        self.m -= len(index)
        if basis.valid:
            gone = set(index.tolist())
            rows = [status for i, status in enumerate(rows) if i not in gone]
            spare = (j for j, status in enumerate(cols) if status == BASIC)
            for i in tight:
                choice = next((j for j in held[i] if cols[j] == BASIC), None)
                if choice is None:
                    choice = next((j for j in spare if cols[j] == BASIC), None)
                if choice is None:
                    # no basic column is left: a basic row gives its place
                    k = next(k for k, status in enumerate(rows) if status == BASIC)
                    rows[k] = _resting(self.row_lower[k], self.row_upper[k])
                else:
                    cols[choice] = _resting(self.lower[choice], self.upper[choice])
            self._set_basis(cols, rows)

    def _set_basis(self, cols, rows):
        basis = highs.HighsBasis()
        basis.col_status = cols
        basis.row_status = rows
        basis.valid = True
        basis.alien = True  # HiGHS checks the basis and mends it where its matrix is singular
        self.s.setBasis(basis)

    def start_at_upper(self, column):
        """Make `column` rest on its upper bound in the basis, where it is not basic."""
        basis = self.s.getBasis()
        if basis.valid:
            cols = list(basis.col_status)
            if cols[column] != BASIC:
                cols[column] = AT_UPPER
                self._set_basis(cols, list(basis.row_status))

    @contextmanager
    def option(self, name, value):
        """An option of HiGHS changed for the runs inside the block."""
        saved = self.s.getOptionValue(name)[1]
        self.s.setOptionValue(name, value)
        try:
            yield
        finally:
            self.s.setOptionValue(name, saved)

    # -- solve -------------------------------------------------------------------------------------
    def run(self):
        """One run of HiGHS from the present basis."""
        s = self.s
        if s.run() == ERROR:
            return Run(Status.kSolveError, None, None, None, None, None, 0)
        status = s.getModelStatus()
        info = s.getInfo()
        iterations = max(0, info.simplex_iteration_count)
        self.iterations += iterations
        if status == EMPTY:
            # no column is left: the answer is empty
            zeros = np.zeros(self.m)
            return Run(OPTIMAL, np.zeros(0), np.zeros(0), zeros, zeros, 0.0, iterations)
        solution = s.getSolution()
        return Run(
            status,
            np.array(solution.col_value),
            np.array(solution.col_dual),
            np.array(solution.row_value),
            np.array(solution.row_dual),
            info.objective_function_value,
            iterations,
        )

    def tight(self):
        """One more run from the present basis with the tightest tolerances of HiGHS, so that its
        duals are exact where the first run left a dual of the wrong sign within its tolerance."""
        with (
            self.option('dual_feasibility_tolerance', TIGHT),
            self.option('primal_feasibility_tolerance', TIGHT),
        ):
            return self.run()


def _resting(lower, upper):
    """The status of a column that leaves the basis: on a finite bound, or at zero when it is free."""
    if np.isfinite(lower):
        return AT_LOWER
    if np.isfinite(upper):
        return AT_UPPER
    return AT_ZERO


def quadratic(A, row_lower, row_upper, lower, upper, target, weight, iterations):
    """min 1/2 sum w (x - c)^2 over the rows and bounds, by the QP of HiGHS on an instance of its own
    with at most `iterations` iterations. Gives (status, x, iterations taken)."""
    n = A.shape[1]
    s = highs._Highs()
    s.passOptions(_options())
    if s.passModel(_model(A, row_lower, row_upper, lower, upper, -weight * target)) == ERROR:
        return Status.kSolveError, None, 0
    weighed = np.flatnonzero(weight > 0)
    if len(weighed):
        # a diagonal Hessian, by its lower triangle column by column; a column of no weight has none
        hessian = highs.HighsHessian()
        hessian.dim_ = n
        hessian.format_ = highs.HessianFormat.kTriangular
        hessian.start_ = _i32(np.r_[0, np.cumsum(weight > 0)])
        hessian.index_ = _i32(weighed)
        hessian.value_ = _f64(weight[weighed])
        if s.passHessian(hessian) == ERROR:
            return Status.kSolveError, None, 0
    s.setOptionValue('qp_iteration_limit', int(iterations))
    if s.run() == ERROR:
        return Status.kSolveError, None, 0
    status, info = s.getModelStatus(), s.getInfo()
    taken = max(0, info.qp_iteration_count) + max(0, info.simplex_iteration_count)
    if status == EMPTY:
        return OPTIMAL, np.zeros(0), taken
    return status, np.array(s.getSolution().col_value), taken
