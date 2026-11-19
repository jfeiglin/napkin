"""Prototype P1: an interior point answer, then OSQP's active-set polish from it.

Not a test and not linted. An interior point method stops about sqrt(its tolerance) away from a bound
that holds the nearest point with no multiplier (a target on its bound). OSQP's polish guesses the
active set from the duals, solves the reduced KKT system on it, refines it, and keeps the result only
where it improves on the iterate; a constraint with no multiplier is left out of the guess, and the
reduced system then lands exactly on it. So each stage here is: Clarabel (or PIQP) through
`qpsolvers`, then OSQP set up on the same reduced problem (rows and bounds as `l <= A x <= u`),
warm-started with the IPM's x and duals (the bound duals from the stationarity residual), run with
`polishing` on. The stage's answer is OSQP's polished x where its polish succeeded, else the IPM's.

    /home/user/venvs/p1/bin/python scratch/rewrite/p1/polish.py TAG [--ipm NAME] [--repeat R]
"""

import copy
import json
import sys
import time

import lab
import numpy as np
import qp
import scipy.sparse as sp

from napkin.engine.solve import FLOW, OTHER
from napkin.engine.solve.solver import Work

OPTIONS = dict(eps_abs=1e-7, eps_rel=1e-7, max_iter=2000, polishing=True, polish_refine_iter=10,
               adaptive_rho_interval=25, verbose=False)  # fmt: skip


def stage(ipm, A, row_lower, row_upper, lower, upper, target, weight, box=None):
    """One stage: the IPM, then OSQP's polish from its point. Gives (x, info)."""
    import osqp

    x0, info, form = qp.candidate_stage(ipm, A, row_lower, row_upper, lower, upper, target, weight, duals=True)
    if not len(form['free']):
        return x0, dict(info, polish='empty')
    free = form['free']
    B = sp.csr_array(sp.csr_array(A)[form['rows']][:, free])
    # the rows' bounds after the fixed columns moved into them (as `qp.reduced` does)
    fixed = upper <= lower
    shift = sp.csr_array(A)[:, np.flatnonzero(fixed)] @ form['x'][fixed] if fixed.any() else 0.0
    lo_r = (row_lower - shift)[form['rows']]
    hi_r = (row_upper - shift)[form['rows']]
    n = len(free)
    w = weight[free]
    P = sp.diags_array(w).tocsc()
    q = -w * target[free]
    M = sp.vstack([B, sp.eye_array(n)]).tocsc()
    # OSQP takes 32-bit indices
    P, M = (sp.csc_matrix((m.data, m.indices.astype(np.int32), m.indptr.astype(np.int32)), shape=m.shape) for m in (P, M))
    low = np.r_[lo_r, lower[free]]
    high = np.r_[hi_r, upper[free]]
    x = x0[free]
    y_rows = form['y']
    # the bound duals: what the rows leave of the gradient, P x + q + B'y + z = 0
    z = -(P @ x + q + B.T @ y_rows)
    clock = time.perf_counter()
    solver = osqp.OSQP()
    solver.setup(P=P, q=q, A=M, l=low, u=high, **OPTIONS)
    solver.warm_start(x=x, y=np.r_[y_rows, z])
    result = solver.solve()
    seconds = time.perf_counter() - clock
    polished = int(result.info.status_polish)
    out = x0.copy()
    # OSQP's x is its polished one where the polish succeeded; with no active set (or a polish that
    # did not improve) it is its own iterate, warm-started from the IPM's and solved to OPTIONS
    solved = str(result.info.status) == 'solved'
    if (polished == 1 or solved) and result.x is not None and np.all(np.isfinite(result.x)):
        out[free] = np.clip(result.x, lower[free], upper[free])
    return out, dict(info, polish=polished, osqp=str(result.info.status), osqp_iter=int(result.info.iter),
                     polish_seconds=round(seconds, 3))  # fmt: skip


def select(face, w, budget, work, ipm='clarabel'):
    """`distance.select` with polished IPM stages; the second stage holds the flows within the box
    of `qp.BOX` (a first stage met to a tolerance leaves the levels' rows inconsistent by that much)."""
    A, row_lower, row_upper = face.arrays(w.A)
    lower, upper = face.lower.copy(), face.upper.copy()
    flows, others = w.kind == FLOW, w.kind == OTHER
    xi = None
    infos = []
    if flows.any():
        xi, info = stage(ipm, A, row_lower, row_upper, lower, upper, w.target, flows * 1.0)
        infos.append(info)
        width = qp.BOX[qp.METHODS[ipm][0]] * (1.0 + np.abs(xi[flows]))
        lower[flows] = np.maximum(lower[flows], xi[flows] - width)
        upper[flows] = np.minimum(upper[flows], xi[flows] + width)
    if others.any() or xi is None:
        xi, info = stage(ipm, A, row_lower, row_upper, lower, upper, w.target, others * 1.0)
        infos.append(info)
    work.methods.extend(f'{ipm}+polish:{i.get("polish")}' for i in infos)
    work.infos = infos
    return xi


def replacement(ipm='clarabel'):
    def chosen(face, w, budget, work):
        return select(face, w, budget, work, ipm)

    return chosen


def run(tag, ipm, repeat):
    from napkin.engine.solve import Budget

    state = lab.read(tag)
    times, answers, work = [], [], None
    for _ in range(repeat):
        work = Work()
        clock = time.perf_counter()
        xi = select(copy.deepcopy(state['face']), state['w'], Budget(), work, ipm)
        times.append(time.perf_counter() - clock)
        answers.append(xi)
    same = all(np.array_equal(a, answers[0]) for a in answers[1:]) if repeat > 1 else None
    try:
        reference = np.load(f'{lab.DATA}/{tag}-library.npy')
    except FileNotFoundError:
        reference = None
    found = lab.measures(state, answers[0], reference)
    record = dict(tag=tag, method=f'{ipm}+polish', seconds=min(times), all=times, repeat=repeat, bitwise=same,
                  infos=work.infos, measures=found, load=lab.load(), version=lab.library_version())  # fmt: skip
    with open(f'{lab.DATA}/distance.jsonl', 'a') as f:
        f.write(json.dumps(record, default=str) + '\n')
    short = [(i['status'], i['iterations'], i.get('polish'), i.get('osqp'), i.get('osqp_iter'), i.get('polish_seconds')) for i in work.infos]
    print(f'{tag} {ipm}+polish: {min(times):.2f} s (of {repeat}), bitwise {same}; {short}; {lab.fmt(found)} '
          f'[load {lab.load()}]', flush=True)  # fmt: skip


if __name__ == '__main__':
    args = sys.argv[1:]

    def option(name, default, kind):
        if name in args:
            i = args.index(name)
            value = kind(args[i + 1])
            del args[i : i + 2]
            return value
        return default

    ipm = option('--ipm', 'clarabel', str)
    repeat = option('--repeat', 1, int)
    qp._clarabel_iterations()
    run(args[0], ipm, repeat)
