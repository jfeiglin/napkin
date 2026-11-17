"""A thin wrapper of the HiGHS solver that SciPy bundles: one persistent instance for one island."""
import math
import numpy as np
import scipy.sparse as sp
from scipy.optimize._highspy import _core as h

def options(threads=1, presolve='on'):
    o = h.HighsOptions()
    o.output_flag = False
    o.log_to_console = False
    o.threads = threads
    o.presolve = presolve
    return o

class Island:
    """min c.x (+ 1/2 x'Qx) s.t. row_lower <= A x <= row_upper, lower <= x <= upper."""
    def __init__(self, A, row_lower, row_upper, lower, upper, cost=None, presolve='on'):
        A = sp.csc_array(A)
        m, n = A.shape
        lp = h.HighsLp()
        lp.num_col_, lp.num_row_ = n, m
        lp.a_matrix_.num_col_, lp.a_matrix_.num_row_ = n, m
        lp.a_matrix_.format_ = h.MatrixFormat.kColwise
        lp.a_matrix_.start_ = A.indptr.astype(np.int32)
        lp.a_matrix_.index_ = A.indices.astype(np.int32)
        lp.a_matrix_.value_ = A.data.astype(float)
        lp.col_cost_ = np.zeros(n) if cost is None else np.asarray(cost, float)
        lp.col_lower_, lp.col_upper_ = np.asarray(lower, float), np.asarray(upper, float)
        lp.row_lower_, lp.row_upper_ = np.asarray(row_lower, float), np.asarray(row_upper, float)
        self.s = h._Highs()
        self.s.passOptions(options(presolve=presolve))
        status = self.s.passModel(lp)
        assert status != h.HighsStatus.kError
        self.n, self.m = n, m

    def hessian(self, diagonal):
        """Q diagonal (the objective has 1/2 x'Qx)."""
        q = h.HighsHessian()
        n = self.n
        q.dim_ = n
        q.format_ = h.HessianFormat.kTriangular
        q.start_ = np.arange(n + 1, dtype=np.int32)
        q.index_ = np.arange(n, dtype=np.int32)
        q.value_ = np.asarray(diagonal, float)
        status = self.s.passHessian(q)
        assert status != h.HighsStatus.kError, status

    def run(self):
        self.s.run()
        status = self.s.getModelStatus()
        sol = self.s.getSolution()
        info = self.s.getInfo()
        return status, np.array(sol.col_value), info

if __name__ == '__main__':
    A = sp.csr_array(np.array([[1.0, 1.0]]))
    isl = Island(A, [1.0], [1.0], [0, 0], [1, 1], cost=[-1.0, 0.0])
    st, x, info = isl.run(); print(st, x, info.objective_function_value, info.simplex_iteration_count)
    isl.hessian([2.0, 2.0])
    isl.s.changeColsCost(2, np.array([0, 1], dtype=np.int32), np.array([-0.5, -0.5]))
    st, x, info = isl.run(); print(st, x, info.objective_function_value, info.qp_iteration_count)
