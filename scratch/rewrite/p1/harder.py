"""Prototype P1: what makes the engine's problem harder for the distance method than the bench's.

Not a test and not linted. For each exported face, one Newton system of the method's first stage
(`distance._Dual`, at the first point of `nearest`) is factorized by SuperLU as the method does it,
with its fill and time; then the same with a store's two rows `-b.x <= 0` and `b.x <= 0` (a store
held at [0, 0], the engine's form) merged into the one equality `b.x == 0` (the bench's form), and
with the levels on the bench's scale (one).

    /home/user/venvs/p1/bin/python scratch/rewrite/p1/harder.py TAG [TAG ...] [--method]

`--method` also runs the library's two stages on the merged face and gives their time and steps.
"""

import copy
import sys
import time

import lab
import numpy as np
import scipy.sparse as sp
from scipy.sparse.linalg import splu

from napkin.engine.solve import FLOW, Budget, distance
from napkin.engine.solve.solver import Work


def newton_system(A, row_lower, row_upper, lower, upper, target, weight):
    """The augmented system of the first Newton step of `nearest` (its own preparation, shortened)."""
    A = sp.csr_array(A)
    fixed = upper <= lower
    x = np.where(fixed, np.minimum(lower, upper), 0.0)
    free = np.flatnonzero(~fixed)
    shift = A[:, np.flatnonzero(fixed)] @ x[fixed]
    B = sp.csr_array(A[:, free])
    lo, hi = row_lower - shift, row_upper - shift
    keep = np.flatnonzero((np.diff(B.indptr) > 0) & (np.isfinite(lo) | np.isfinite(hi)))
    B, lo, hi = sp.csr_array(B[keep]), lo[keep], hi[keep]
    equal = lo == hi
    loose = np.flatnonzero(~equal)
    mk, ns = B.shape[0], len(loose)
    S = sp.csr_array((np.ones(ns), (loose, np.arange(ns))), shape=(mk, ns))
    E = sp.hstack([B, -S]).tocsr()
    e = np.where(equal, lo, 0.0)
    zl, zu = np.r_[lower[free], lo[loose]], np.r_[upper[free], hi[loose]]
    w = np.r_[weight[free], np.zeros(ns)]
    w = np.where(w <= 0, distance.EPS_START, w)
    c = np.r_[target[free], np.zeros(ns)]
    dual = distance._Dual(E, e, zl, zu, w)
    y = np.zeros(mk)
    u = c - (dual.ET @ y) / dual.w
    inside = (u > zl) & (u < zu)
    dual.K.data[dual.diagonal] = np.r_[np.where(inside, w, w * (1.0 + distance.RHO)), np.full(mk, -distance.DELTA)]
    return dual.K, dict(free=len(free), rows=mk, slacks=ns, equalities=int(equal.sum()))


def merged(state):
    """The state with each pair of rows that are negatives of each other, both `<= 0` sides of one
    store, merged into one row whose bounds are the intersection."""
    state = copy.deepcopy(state)
    w, face = state['w'], state['face']
    keys = w.arrays.row_keys
    order = [keys[i] for i in w.rows.tolist()]
    at = {key: k for k, key in enumerate(order)}
    drop, A = [], w.A.tolil()
    lower, upper = face.row_lower, face.row_upper
    for k, key in enumerate(order):
        if isinstance(key, tuple) and key[0] == 'store' and key[2] == 'lower':
            other = at.get(('store', key[1], 'upper'))
            if other is None:
                continue
            # row k is -b.x in [lo_k, hi_k], row `other` is b.x in [lo_o, hi_o]
            lo = max(-upper[k], lower[other])
            hi = min(-lower[k], upper[other])
            lower[other], upper[other] = lo, hi
            drop.append(k)
    keep = np.setdiff1d(np.arange(len(order)), drop)
    w.A = sp.csr_array(w.A[keep])
    w.row_lower, w.row_upper = w.row_lower[keep], w.row_upper[keep]
    w.rows = w.rows[keep]
    w.row_scale = w.row_scale[keep]
    face.row_lower, face.row_upper = lower[keep], upper[keep]
    w.m = len(keep)
    return state, len(drop)


def factor(state, label):
    A, row_lower, row_upper, lower, upper, target, kind = lab.distance_problem(state)
    K, size = newton_system(A, row_lower, row_upper, lower, upper, target, (kind == FLOW) * 1.0)
    clock = time.perf_counter()
    lu = splu(sp.csc_array(K), permc_spec='MMD_AT_PLUS_A')
    seconds = time.perf_counter() - clock
    print(
        f'  {label}: {size}, K {K.shape[0]} x {K.shape[0]}, nnz {K.nnz}; SuperLU {seconds:.2f} s, '
        f'L+U nnz {lu.L.nnz + lu.U.nnz} ({(lu.L.nnz + lu.U.nnz) / K.nnz:.1f} x K)',
        flush=True,
    )


def method(state, label):
    work = Work()
    clock = time.perf_counter()
    distance.select(copy.deepcopy(state['face']), state['w'], Budget(), work)
    print(f'  {label}: method {time.perf_counter() - clock:.2f} s, Newton {work.newton}, '
          f'factorizations {work.factorizations} [load {lab.load()}]', flush=True)


if __name__ == '__main__':
    args = sys.argv[1:]
    run_method = '--method' in args
    candidate = None
    if '--candidate' in args:
        i = args.index('--candidate')
        candidate = args[i + 1]
        del args[i : i + 2]
    tags = [a for a in args if not a.startswith('--')]
    for tag in tags:
        state = lab.read(tag)
        print(tag, flush=True)
        factor(state, 'as exported')
        if tag.startswith('engine'):
            joined, count = merged(state)
            factor(joined, f'store rows merged ({count} pairs)')
            if run_method:
                method(joined, 'store rows merged')
            if candidate:
                import qp

                qp._clarabel_iterations()
                clock = time.perf_counter()
                xi, infos = qp.candidate(candidate, joined)
                print(f'  store rows merged: {candidate} {time.perf_counter() - clock:.2f} s, '
                      f'{[(i["status"], i["iterations"]) for i in infos]}; {lab.fmt(lab.measures(joined, xi))}', flush=True)
