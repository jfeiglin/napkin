"""The selection order of the spec on one kept instance:

1. hard constraints (the rows and bounds of the problem);
2. ranked objectives in written order, each optimum kept (`ranked`, pin by default);
3. fair sharing, one priority tier after another (`fair.sequential`);
4. the flows nearest their targets (`distance`, weight one for kind FLOW);
5. with the flows fixed, the other unknowns nearest their references (weight one for kind OTHER).

The instance belongs to one run. Each `solve` restores the bounds and the costs of the instance when it
ends, so the next solve starts warm from the last basis on the same program. `join` and `leave` change
the set of columns in place (risk 3).
"""
import time
import numpy as np
import scipy.sparse as sp

from .form import Work, FLOW, OTHER, INTERNAL
from .lp import Kept
from . import ranked, fair, distance


class Answer:
    def __init__(self, x, optima, levels, stats):
        self.x, self.optima, self.levels, self.stats = x, optima, levels, stats


class Selector:
    def __init__(self, problem, method='pin', **options):
        self.method = method
        self.options = options
        self._form(problem)

    def _form(self, problem, row_scale=None):
        self.problem = problem
        self.work = Work(problem)
        w = self.work
        self.kept = Kept(w.A, w.row_lower, w.row_upper, w.lower, w.upper, **self.options)

    # -- membership ---------------------------------------------------------------------------
    def replace(self, problem, gone=(), joined=0):
        """The same rows; the columns `gone` of the old problem left and `joined` columns were added
        at the end of the new one. The kept instance follows in place, with its basis."""
        old = self.work
        w = Work(problem)
        assert w.m == old.m, 'rows do not change here'
        k = self.kept
        k.delete_cols(np.asarray(gone, dtype=int))
        if joined:
            cols = w.A[:, w.n - joined:].tocsc()
            k.add_cols(np.zeros(joined), w.lower[w.n - joined:], w.upper[w.n - joined:], cols)
        # bounds and row bounds can change with the moment
        k.set_bounds(np.arange(w.n), w.lower, w.upper)
        k.set_row_bounds(np.arange(w.m), w.row_lower, w.row_upper)
        self.problem, self.work = problem, w

    # -- one solve ----------------------------------------------------------------------------
    def solve(self, fair_limit=None, check_tol=1e-7):
        w, k = self.work, self.kept
        st = {}
        t0 = time.perf_counter()
        face = ranked.Face(w.lower, w.upper, w.row_lower, w.row_upper)
        m0, n0 = k.m, k.n
        try:
            x, optima, st['ranked'] = ranked.optimize(k, face, w.costs, self.method)
            st['t_ranked'] = time.perf_counter() - t0
            levels = {}
            t1 = time.perf_counter()
            for tier in np.unique(w.tier):
                sel = np.flatnonzero(w.tier == tier)
                lv, s = fair.sequential(k, face, w.F[sel], limit=fair_limit)
                levels[int(tier)] = (sel, lv)
                st[f'fair{tier}'] = s
            st['t_fair'] = time.perf_counter() - t1
            t2 = time.perf_counter()
            x = self._distance(face, st)
            st['t_distance'] = time.perf_counter() - t2
        finally:
            self._restore(m0, n0)
        st['seconds'] = time.perf_counter() - t0
        bad = ranked.check(w.costs, optima, x, tol=check_tol)
        st['lost'] = max([0.0] + [v - b for _, v, b in ranked.check(w.costs, optima, x, tol=0.0)])
        if bad:
            raise RuntimeError(f'an earlier optimum was lost: {bad}')
        return Answer(w.x(x), [v * s for v, s in zip(optima, w.cost_norms)], levels, st)

    def _restore(self, m0, n0):
        k, w = self.kept, self.work
        if k.m > m0:
            k.delete_rows(np.arange(m0, k.m))
        if k.n > n0:
            k.delete_cols(np.arange(n0, k.n))
        k.set_bounds(np.arange(w.n), w.lower, w.upper)
        k.set_row_bounds(np.arange(w.m), w.row_lower, w.row_upper)
        k.set_cost(np.zeros(w.n))

    def _distance(self, face, st):
        w = self.work
        A = w.A
        rl, ru = face.row_lower, face.row_upper
        if face.extra:
            A = sp.vstack([A] + [r for r, _, _ in face.extra]).tocsr()
            rl = np.r_[rl, np.concatenate([a for _, a, _ in face.extra])]
            ru = np.r_[ru, np.concatenate([b for _, _, b in face.extra])]
        lo, hi = face.lower.copy(), face.upper.copy()
        weight = (w.kind == FLOW).astype(float)
        x, s1 = distance.nearest(A, rl, ru, lo, hi, w.target, weight)
        flows = w.kind == FLOW
        lo[flows] = hi[flows] = x[flows]
        weight = (w.kind == OTHER).astype(float)
        x, s2 = distance.nearest(A, rl, ru, lo, hi, w.target, weight)
        st['distance'] = [(s.outer, s.newton, s.factorizations) for s in (s1, s2)]
        return x
