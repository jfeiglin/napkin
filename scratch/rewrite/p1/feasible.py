"""Prototype P1: is the face at the start of the distance step feasible, and how nearly?

Not a test and not linted. Solves min 0 over the exported face (rows and bounds in working units) by
HiGHS (SciPy's linprog) at primal tolerances 1e-9 and 1e-7, and the least uniform widening e of the
held claims' floors that makes it feasible: max -e with each floor lowered by e (an LP), which says by
how much fair sharing's levels overshoot what the face can hold.

    /home/user/venvs/p1/bin/python scratch/rewrite/p1/feasible.py TAG
"""

import sys
import time

import lab
import numpy as np
import scipy.sparse as sp
from scipy.optimize import linprog


def check(state, tolerance):
    w, face = state['w'], state['face']
    A, row_lower, row_upper = face.arrays(w.A)
    A = sp.csr_array(A)
    equal = row_lower == row_upper
    up = ~equal & np.isfinite(row_upper)
    down = ~equal & np.isfinite(row_lower)
    clock = time.perf_counter()
    result = linprog(
        np.zeros(w.n),
        A_ub=sp.vstack([A[np.flatnonzero(up)], -A[np.flatnonzero(down)]]),
        b_ub=np.r_[row_upper[up], -row_lower[down]],
        A_eq=A[np.flatnonzero(equal)],
        b_eq=row_lower[equal],
        bounds=list(zip(np.where(np.isfinite(face.lower), face.lower, None), np.where(np.isfinite(face.upper), face.upper, None))),
        method='highs',
        options=dict(primal_feasibility_tolerance=tolerance),
    )
    return result.status, result.message[:70], time.perf_counter() - clock


def widening(state):
    """The least e >= 0 such that the face with every held floor of a claim lowered by e (each
    column bound that fair sharing raised, in the claim's own fraction) is feasible."""
    w, face, after = state['w'], state['face'], state['after']['face']
    A, row_lower, row_upper = face.arrays(w.A)
    A = sp.csr_array(A)
    raised = face.lower > after.lower  # the bounds that held claims raised (single-column claims)
    n = w.n
    # x_j >= floor_j - e * s_j where s_j is the column's step per unit of the claim's fraction
    F = sp.csr_array(w.F)
    step = np.zeros(n)
    single = np.diff(F.indptr) == 1
    columns = F.indices[F.indptr[:-1][single]]
    step[columns] = 1.0 / np.abs(F.data[F.indptr[:-1][single]])
    lower = np.where(raised, after.lower, face.lower)  # the floor itself becomes a row with e
    rows = sp.csr_array((np.ones(int(raised.sum())), (np.arange(int(raised.sum())), np.flatnonzero(raised))), shape=(int(raised.sum()), n))
    rows = sp.hstack([rows, sp.csr_array(step[raised].reshape(-1, 1))]).tocsr()  # x_j + s_j e >= floor_j
    equal = row_lower == row_upper
    up = ~equal & np.isfinite(row_upper)
    down = ~equal & np.isfinite(row_lower)
    pad = lambda M: sp.hstack([M, sp.csr_array((M.shape[0], 1))]).tocsr()  # noqa: E731
    cost = np.r_[np.zeros(n), 1.0]
    result = linprog(
        cost,
        A_ub=sp.vstack([pad(A[np.flatnonzero(up)]), -pad(A[np.flatnonzero(down)]), -rows]),
        b_ub=np.r_[row_upper[up], -row_lower[down], -face.lower[raised]],
        A_eq=pad(A[np.flatnonzero(equal)]),
        b_eq=row_lower[equal],
        bounds=list(zip(np.where(np.isfinite(lower), lower, None), np.where(np.isfinite(face.upper), face.upper, None))) + [(0, None)],
        method='highs',
        options=dict(primal_feasibility_tolerance=1e-9),
    )
    return result.status, (result.x[-1] if result.x is not None else None)


if __name__ == '__main__':
    tag = sys.argv[1]
    state = lab.read(tag)
    for tolerance in (1e-9, 1e-7):
        status, message, seconds = check(state, tolerance)
        print(f'{tag}: face at primal tolerance {tolerance:g}: status {status} ({message}) in {seconds:.1f} s', flush=True)
    status, e = widening(state)
    print(f'{tag}: least widening of the held floors that makes the face feasible: {e} (status {status})', flush=True)
