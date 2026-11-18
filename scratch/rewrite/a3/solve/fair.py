"""The fair-sharing rank: within one priority tier, maximize the smallest served fraction, then the
next smallest (lexicographic max-min of fraction_i = min(1, F_i . x)).

`sequential` (the exact method): one program `max t` with `F_i x >= t` for every pending claim and
t <= 1. At its optimum t*, a claim whose row has a dual above TAU is at t* in every optimal answer
(complementary slackness), and the max-min answer is one of them; such a claim is fixed. At least one
claim has a dual, because the duals of the claim rows sum to one (the cost of t). Each program fixes at
least one claim; t* rises or stays.

A fixed claim gets the lower bound F_i x >= t* - FIX, never an equality: an equality at the computed
level failed at 30,000 places (STATE.md, ex3: infeasible with 26,563 claims pending), because t* is only
known to the feasibility tolerance of the solver. A fixed claim cannot rise above its level within the
later ranks without lowering a claim at that level, so the bound is enough.

`brute` is the reference for small problems: after each `max t`, one program for each pending claim
(`max F_i x` with the others held at t*) decides which claims are fixed.
"""
import time
import numpy as np
import scipy.sparse as sp
from scipy.optimize import linprog

from .lp import INF, AT_UPPER, SolveError
from .form import _row_max
from scipy.optimize._highspy import _core as h

TAU = 1e-9
FIX = 1e-7      # the feasibility tolerance of HiGHS: how well a level is known
ONE = 1e-9


def sequential(kept, face, F, primal=True, log=None, limit=None):
    """Max-min of the claims F (K x n, working units) on the kept instance. Narrows `face` with the
    fixes, and removes its own column and rows from the instance at the end.
    Returns (levels, stats)."""
    K = F.shape[0]
    levels = np.full(K, np.nan)
    stats = dict(programs=0, iterations=0, seconds=0.0, distinct=0)
    if not K:
        return levels, stats
    start = time.perf_counter()
    F = sp.csr_array(F)
    n0 = kept.n
    F = sp.hstack([F, sp.csr_array((K, n0 - F.shape[1]))]).tocsr() if F.shape[1] < n0 else F
    scale = 1.0 / np.maximum(1.0, _row_max(F))
    t = kept.add_cols([-1.0], [-INF], [1.0])[0]
    rows = sp.hstack([sp.diags_array(scale) @ F, sp.csr_array(-scale.reshape(-1, 1))]).tocsr()
    first = kept.add_rows(np.zeros(K), np.full(K, INF), rows)
    # start with t at its upper bound: with no shortage the first program needs no iteration
    basis = kept.s.getBasis()
    if basis.valid:
        cols = list(basis.col_status)
        cols[t] = AT_UPPER
        kept._set_basis(cols, list(basis.row_status))
    single = np.diff(F.indptr) == 1
    pending = np.ones(K, bool)
    saved = kept.s.getOptionValue('simplex_strategy')[1]
    i0 = kept.iterations
    try:
        while pending.any():
            x, d, r, y, value = kept.solve('the fair-sharing rank')
            stats['programs'] += 1
            if stats['programs'] == 1 and primal:
                kept.s.setOptionValue('simplex_strategy', 4)   # primal simplex: only bounds change now
            level = x[t]
            lam = y[first]
            if level >= 1.0 - ONE:
                fixed = pending.copy()
                level = 1.0
            else:
                fixed = pending & (lam > TAU)
                if not fixed.any():
                    raise SolveError('numerical', 'the fair-sharing rank found no claim with a dual')
            idx = np.flatnonzero(fixed)
            levels[idx] = level
            pending[idx] = False
            _fix(kept, face, F, scale, first, idx, single, level)
            if log is not None:
                log.append((stats['programs'], level, len(idx), int(pending.sum()), kept.last_iterations))
            if limit is not None and time.perf_counter() - start > limit:
                stats['stopped'] = True
                break
    finally:
        kept.s.setOptionValue('simplex_strategy', saved)
        kept.delete_rows(first)
        kept.delete_cols([t])
    stats['iterations'] = kept.iterations - i0
    stats['seconds'] = time.perf_counter() - start
    done = levels[~np.isnan(levels)]
    stats['distinct'] = int(len(np.unique(np.round(done, 7))))
    return levels, stats


def _fix(kept, face, F, scale, first, idx, single, level):
    """F_i x >= level - FIX for the claims idx: a bound for a claim of one column, else a row."""
    kept.set_row_bounds(first[idx], np.full(len(idx), -INF), np.full(len(idx), INF))
    floor = level - FIX if level < 1.0 else 1.0 - FIX
    one = idx[single[idx]]
    if len(one):
        cols = F.indices[F.indptr[one]]
        a = F.data[F.indptr[one]]
        lo, hi = face.lower, face.upper
        pos = a > 0
        lo[cols[pos]] = np.maximum(lo[cols[pos]], floor / a[pos])
        hi[cols[~pos]] = np.minimum(hi[cols[~pos]], floor / a[~pos])
        kept.set_bounds(cols, lo[cols], hi[cols])
    many = idx[~single[idx]]
    if len(many):
        rows = sp.diags_array(scale[many]) @ F[many]
        lower = scale[many] * floor
        kept.add_rows(lower, np.full(len(many), INF), sp.hstack([rows, sp.csr_array((len(many), kept.n - rows.shape[1]))]))
        face.add(rows, lower, np.full(len(many), INF))


# -- the reference: one program for each pending claim ----------------------------------------------
def brute(A, rl, ru, lo, hi, F, tol=1e-7):
    """Lexicographic max-min of min(1, F x) over rl <= A x <= ru, lo <= x <= hi, with scipy's linprog.
    Small problems only."""
    A, F = sp.csr_array(A), sp.csr_array(F)
    n, K = A.shape[1], F.shape[0]
    eq = rl == ru
    pending = np.ones(K, bool)
    levels = np.full(K, np.nan)
    floors = np.zeros(K)

    def program(c, extra_lower):
        # columns x, then t
        G = [A[~eq], -A[~eq]]
        g = [ru[~eq], -rl[~eq]]
        # claims: t - F_i x <= 0 (pending), -F_i x <= -floor (fixed)
        rows, rhs = [], []
        for i in range(K):
            if pending[i]:
                rows.append(sp.hstack([-F[[i]], sp.csr_array([[1.0]])]))
                rhs.append(0.0)
            else:
                rows.append(sp.hstack([-F[[i]], sp.csr_array((1, 1))]))
                rhs.append(-floors[i])
        Ub = sp.vstack([sp.hstack([Gi, sp.csr_array((Gi.shape[0], 1))]) for Gi in G] + rows + extra_lower[0])
        ub = np.r_[np.concatenate(g), rhs, extra_lower[1]]
        keep = np.isfinite(ub)
        Ae = sp.hstack([A[eq], sp.csr_array((int(eq.sum()), 1))])
        res = linprog(c, A_ub=Ub[keep], b_ub=ub[keep], A_eq=Ae if eq.any() else None,
                      b_eq=rl[eq] if eq.any() else None,
                      bounds=list(zip(np.where(np.isfinite(lo), lo, None), np.where(np.isfinite(hi), hi, None))) + [(None, 1.0)],
                      method='highs')
        if res.status != 0:
            raise RuntimeError(res.message)
        return res

    while pending.any():
        c = np.zeros(n + 1); c[n] = -1.0
        star = -program(c, ([], np.zeros(0))).fun
        if star >= 1 - tol:
            levels[pending] = 1.0
            break
        hold = []
        for i in np.flatnonzero(pending).tolist():
            # can claim i rise above star with every pending claim at star or more?
            c = np.zeros(n + 1)
            c[:n] = -F[[i]].toarray().ravel()
            row = sp.hstack([sp.csr_array((1, n)), sp.csr_array([[-1.0]])])
            best = -program(c, ([row], np.array([-star]))).fun
            if best <= star + tol:
                hold.append(i)
        levels[hold] = star
        floors[hold] = star - tol
        pending[hold] = False
        if not hold:
            raise RuntimeError('no claim is held: the tolerance is too small')
    return levels
