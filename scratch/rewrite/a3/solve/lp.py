"""One HiGHS instance that keeps its program and its basis (the solver that SciPy bundles).

    min c.x   with   row_lower <= A x <= row_upper,   lower <= x <= upper

The instance belongs to one run. Costs, bounds, columns and rows change in place, and each `run`
starts from the basis of the last one. `delete_cols` and `delete_rows` carry the basis over by hand,
because HiGHS marks it invalid after a deletion (measured: `measure.py`, "join and leave").

The signs of HiGHS for a minimum: the dual of a column is its reduced cost d = c - A'y, at least zero
at a lower bound and at most zero at an upper bound; the dual y of a row is at least zero when the row
rests on its lower side and at most zero on its upper side.
"""
import numpy as np
import scipy.sparse as sp
from scipy.optimize._highspy import _core as h

INF = h.kHighsInf
OPTIMAL = h.HighsModelStatus.kOptimal
BASIC = h.HighsBasisStatus.kBasic
AT_LOWER = h.HighsBasisStatus.kLower
AT_UPPER = h.HighsBasisStatus.kUpper
ERROR = h.HighsStatus.kError


class SolveError(Exception):
    """A failure of a solve, by name: `infeasible`, `unbounded` or `numerical`."""

    def __init__(self, name, message):
        super().__init__(f'{name}: {message}')
        self.name = name


def _i32(values):
    return np.ascontiguousarray(values, dtype=np.int32)


def _f64(values):
    return np.ascontiguousarray(values, dtype=np.float64)


class Kept:
    def __init__(self, A, row_lower, row_upper, lower, upper, cost=None, threads=1, presolve='on',
                 primal_tolerance=None, dual_tolerance=None):
        A = sp.csc_array(A)
        A.sort_indices()
        m, n = A.shape
        lp = h.HighsLp()
        lp.num_col_, lp.num_row_ = n, m
        lp.a_matrix_.num_col_, lp.a_matrix_.num_row_ = n, m
        lp.a_matrix_.format_ = h.MatrixFormat.kColwise
        lp.a_matrix_.start_ = _i32(A.indptr)
        lp.a_matrix_.index_ = _i32(A.indices)
        lp.a_matrix_.value_ = _f64(A.data)
        lp.col_cost_ = np.zeros(n) if cost is None else _f64(cost)
        lp.col_lower_, lp.col_upper_ = _f64(lower), _f64(upper)
        lp.row_lower_, lp.row_upper_ = _f64(row_lower), _f64(row_upper)
        options = h.HighsOptions()
        options.output_flag = False
        options.log_to_console = False
        options.threads = threads
        options.presolve = presolve
        if primal_tolerance is not None:
            options.primal_feasibility_tolerance = primal_tolerance
        if dual_tolerance is not None:
            options.dual_feasibility_tolerance = dual_tolerance
        self.s = h._Highs()
        self.s.passOptions(options)
        if self.s.passModel(lp) == ERROR:
            raise SolveError('numerical', 'HiGHS refused the program')
        self.n, self.m = n, m
        self.runs = 0
        self.iterations = 0

    # -- changes in place -------------------------------------------------------------------
    def set_cost(self, cost):
        """The whole cost vector."""
        self.s.changeColsCost(self.n, _i32(np.arange(self.n)), _f64(cost))

    def set_costs(self, index, cost):
        index = _i32(index)
        if len(index):
            self.s.changeColsCost(len(index), index, _f64(cost))

    def set_bounds(self, index, lower, upper):
        index = _i32(index)
        if len(index):
            self.s.changeColsBounds(len(index), index, _f64(lower), _f64(upper))

    def set_row_bounds(self, index, lower, upper):
        change = self.s.changeRowBounds
        for i, lo, hi in zip(np.asarray(index).tolist(), np.asarray(lower, float).tolist(),
                             np.asarray(upper, float).tolist()):
            change(i, lo, hi)

    def set_coefficient(self, row, col, value):
        self.s.changeCoeff(int(row), int(col), float(value))

    def add_cols(self, cost, lower, upper, columns=None):
        """New columns at the end; `columns` is a sparse matrix (rows x new columns) or None."""
        k = len(lower)
        if columns is None:
            start, index, value, nnz = np.zeros(k, np.int32), np.zeros(0, np.int32), np.zeros(0), 0
        else:
            columns = sp.csc_array(columns)
            columns.sort_indices()
            start, index, value, nnz = _i32(columns.indptr[:-1]), _i32(columns.indices), _f64(columns.data), columns.nnz
        if self.s.addCols(k, _f64(cost), _f64(lower), _f64(upper), nnz, start, index, value) == ERROR:
            raise SolveError('numerical', 'HiGHS refused the new columns')
        first = self.n
        self.n += k
        return np.arange(first, self.n)

    def add_rows(self, lower, upper, rows):
        """New rows at the end; `rows` is a sparse matrix (new rows x columns)."""
        rows = sp.csr_array(rows)
        rows.sort_indices()
        k = rows.shape[0]
        if self.s.addRows(k, _f64(lower), _f64(upper), rows.nnz, _i32(rows.indptr[:-1]), _i32(rows.indices),
                          _f64(rows.data)) == ERROR:
            raise SolveError('numerical', 'HiGHS refused the new rows')
        first = self.m
        self.m += k
        return np.arange(first, self.m)

    def delete_cols(self, index):
        """Delete columns and keep the basis: a deleted column that was basic gives its place to the
        row of a tight slack (any row that is not basic)."""
        index = np.unique(np.asarray(index, dtype=np.int64))
        if not len(index):
            return
        basis = self.s.getBasis()
        valid = basis.valid
        cols, rows = list(basis.col_status), list(basis.row_status)
        self.s.deleteCols(len(index), _i32(index))
        self.n -= len(index)
        if valid:
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
        """Delete rows and keep the basis: a deleted row that was not basic takes one basic column
        out of the basis (a column that the row held, if one is basic)."""
        index = np.unique(np.asarray(index, dtype=np.int64))
        if not len(index):
            return
        basis = self.s.getBasis()
        valid = basis.valid
        cols, rows = list(basis.col_status), list(basis.row_status)
        extra = []
        if valid:
            for i in index.tolist():
                if rows[i] != BASIC:
                    extra.append(i)
        held = {}
        for i in extra:
            columns = self.s.getRowEntries(i)[1]     # (status, columns, values)
            held[i] = [int(j) for j in columns]
        self.s.deleteRows(len(index), _i32(index))
        self.m -= len(index)
        if valid:
            gone = set(index.tolist())
            rows = [status for i, status in enumerate(rows) if i not in gone]
            for i in extra:
                choice = next((j for j in held[i] if cols[j] == BASIC), None)
                if choice is None:
                    choice = next((j for j, status in enumerate(cols) if status == BASIC), None)
                if choice is None:
                    # no basic column is left: a basic row gives its place
                    k = next(k for k, status in enumerate(rows) if status == BASIC)
                    rows[k] = AT_LOWER
                else:
                    cols[choice] = AT_LOWER
            self._set_basis(cols, rows)

    def _set_basis(self, cols, rows):
        basis = h.HighsBasis()
        basis.col_status = cols
        basis.row_status = rows
        basis.valid = True
        basis.alien = True   # HiGHS checks it and mends it if its matrix is singular
        self.s.setBasis(basis)

    def forget(self):
        """Drop the basis: the next run starts cold."""
        self.s.clearSolver()

    # -- solve --------------------------------------------------------------------------------
    def run(self):
        """(status, x, reduced costs, row values, row duals, objective)."""
        s = self.s
        if s.run() == ERROR:
            raise SolveError('numerical', 'HiGHS stopped with an error')
        status = s.getModelStatus()
        info = s.getInfo()
        self.runs += 1
        self.last_iterations = info.simplex_iteration_count
        self.iterations += max(0, info.simplex_iteration_count)
        sol = s.getSolution()
        return (status, np.array(sol.col_value), np.array(sol.col_dual), np.array(sol.row_value),
                np.array(sol.row_dual), info.objective_function_value)

    def solve(self, what='the program'):
        """`run`, and a failure by name when the program has no optimum."""
        status, x, d, r, y, value = self.run()
        if status == OPTIMAL:
            return x, d, r, y, value
        if status == h.HighsModelStatus.kModelEmpty:      # no column: the answer is empty
            return np.zeros(self.n), np.zeros(self.n), np.zeros(self.m), np.zeros(self.m), 0.0
        name = str(status).split('.')[-1]
        if status == h.HighsModelStatus.kInfeasible:
            raise SolveError('infeasible', f'{what} has no answer within its conditions')
        if status in (h.HighsModelStatus.kUnbounded, h.HighsModelStatus.kUnboundedOrInfeasible):
            raise SolveError('unbounded', f'{what} has no finite optimum ({name})')
        raise SolveError('numerical', f'HiGHS ended {what} with the status {name}')
