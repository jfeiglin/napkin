"""Prototype P1: an interior point method, then the library's dual Newton method from its point.

Not a test and not linted. A raw interior point answer is near the nearest point, but where a target
lies on a bound or a row that holds it with no multiplier (a supply at its request of zero, a use at
its need), it stops about sqrt(its tolerance) away: 5e-5 on the spec's flow with legs, 4e-4 on the
random cases of `tests/engine/solve/test_random.py`. The library's method gives x(y) = clip(c -
E'y / w), exact on those bounds, but at 30,000 places needs hundreds of Newton steps from y = 0.

So each stage here runs an interior point method (Clarabel through `qpsolvers`), maps its duals to
the method's rows (the dual of a row with a slack is z_upper - z_lower), takes its values as the
first centres of the proximal coordinates (the slacks at their rows), and runs the library's method
(`distance._Dual`, its stop rules and tolerances unchanged) from there: `nearest_from` is
`distance.nearest` with that start. The answer is the method's, to the method's rules; the IPM only
gives it a start. A stage whose method does not converge goes to the library's fallback as before.

    /home/user/venvs/p1/bin/python scratch/rewrite/p1/hybrid.py TAG [--ipm NAME] [--eps E] [--repeat R]
"""

import copy
import json
import sys
import time

import lab
import numpy as np
import qp
import scipy.sparse as sp

from napkin.engine.solve import FLOW, OTHER, Budget, distance
from napkin.engine.solve.distance import EPS, SETTLED, TOL, Unconverged, _attempt, _Dual
from napkin.engine.solve.solver import Work


def nearest_from(A, row_lower, row_upper, lower, upper, target, weight, steps, work, start, eps_start):
    """`distance.nearest` from `start` = (x over all columns, y over the kept rows), with the first
    proximal weight `eps_start`. Gives (x, Newton steps taken), or raises `Unconverged`."""
    x0, y0 = start
    A = sp.csr_array(A)
    m = A.shape[0]
    if np.any(lower > upper + TOL * (1.0 + np.abs(lower))):
        raise Unconverged(0, np.inf)
    fixed = upper <= lower
    x = np.where(fixed, np.minimum(lower, upper), 0.0)
    free = np.flatnonzero(~fixed)
    shift = A[:, np.flatnonzero(fixed)] @ x[fixed] if fixed.any() else np.zeros(m)
    size = abs(A[:, np.flatnonzero(fixed)]) @ np.abs(x[fixed]) if fixed.any() else np.zeros(m)
    B = sp.csr_array(A[:, free])
    lo_r, hi_r = row_lower - shift, row_upper - shift
    empty = np.diff(B.indptr) == 0
    slack = distance.LOOSE * (1.0 + size)
    if np.any(empty & ((lo_r > slack) | (hi_r < -slack))):
        raise Unconverged(0, float(np.max(np.maximum(lo_r, -hi_r)[empty])))
    keep = np.flatnonzero(~empty & (np.isfinite(lo_r) | np.isfinite(hi_r)))
    B, lo_r, hi_r = sp.csr_array(B[keep]), lo_r[keep], hi_r[keep]
    equal = lo_r == hi_r
    loose = np.flatnonzero(~equal)
    mk, nf, ns = B.shape[0], len(free), len(loose)
    S = sp.csr_array((np.ones(ns), (loose, np.arange(ns))), shape=(mk, ns))
    E = sp.hstack([B, -S]).tocsr()
    e = np.where(equal, lo_r, 0.0)
    zl, zu = np.r_[lower[free], lo_r[loose]], np.r_[upper[free], hi_r[loose]]
    w = np.r_[weight[free], np.zeros(ns)]
    prox = w <= 0
    eps = eps_start
    w = np.where(prox, eps, w)
    c = np.r_[target[free], np.zeros(ns)]
    # the start: the IPM's values as the first centres of the proximal coordinates, its duals as y
    cx = np.clip(x0[free], zl[:nf], zu[:nf])
    c[:nf][prox[:nf]] = cx[prox[:nf]]
    c[nf:] = np.clip(B[loose] @ cx, zl[nf:], zu[nf:])
    tolerance = TOL * (1.0 + np.abs(e) + abs(B) @ np.abs(np.clip(c[:nf], zl[:nf], zu[:nf])))
    dual = _Dual(E, e, zl, zu, w)
    y = np.asarray(y0, float).copy() if y0 is not None and len(y0) == mk else np.zeros(mk)
    taken = outer = 0
    try:
        while True:
            outer += 1
            z, y1, residual, used, met = _attempt(dual, c, y, tolerance, steps - taken)
            taken += used
            if met is None and taken < steps:
                dual.lm = True
                z, y1, residual, used, met = _attempt(dual, c, y, tolerance, steps - taken)
                taken += used
                dual.lm = False
            if met is None:
                raise Unconverged(taken, residual)
            y = y1
            if not prox.any():
                break
            move = float(np.abs(z[prox] - c[prox]).max())
            c[prox] = z[prox]
            if eps * move <= met * (1.0 + float(np.abs(z[prox]).max())):
                break
            if taken >= steps or outer >= steps:
                raise Unconverged(taken, residual)
            if used <= SETTLED and eps > EPS:
                eps = max(EPS, eps / 10.0)
                dual.weigh(np.where(prox, eps, dual.w))
    finally:
        work.factorizations += dual.factorizations
    x[free] = z[:nf]
    return x, taken


def stage(ipm, A, row_lower, row_upper, lower, upper, target, weight, budget, work, eps_start, what):
    """The IPM, then the method from its point; else the library's stage (method, then its QP)."""
    clock = time.perf_counter()
    x0, info, form = qp.candidate_stage(ipm, A, row_lower, row_upper, lower, upper, target, weight, duals=True)
    ipm_seconds = time.perf_counter() - clock
    clock = time.perf_counter()
    try:
        x, steps = nearest_from(
            A, row_lower, row_upper, lower, upper, target, weight, budget.newton_steps, work,
            (x0, form['y']), eps_start,
        )  # fmt: skip
        work.newton.append(steps)
        work.methods.append(f'{ipm}+newton')
    except Unconverged as stopped:
        work.newton.append(stopped.steps)
        work.methods.append('fallback')
        x = distance.stage(A, row_lower, row_upper, lower, upper, target, weight, budget, work, what)
    work.times = getattr(work, 'times', []) + [(round(ipm_seconds, 3), round(time.perf_counter() - clock, 3))]
    work.ipm = getattr(work, 'ipm', []) + [info['iterations']]
    return x


def select(face, w, budget, work, ipm='clarabel', eps_start=distance.EPS_START):
    """`distance.select` with the hybrid stages."""
    A, row_lower, row_upper = face.arrays(w.A)
    lower, upper = face.lower.copy(), face.upper.copy()
    flows, others = w.kind == FLOW, w.kind == OTHER
    xi = None
    if flows.any():
        xi = stage(ipm, A, row_lower, row_upper, lower, upper, w.target, flows * 1.0, budget, work, eps_start, 'the flows')
        lower[flows] = upper[flows] = xi[flows]
    if others.any() or xi is None:
        xi = stage(ipm, A, row_lower, row_upper, lower, upper, w.target, others * 1.0, budget, work, eps_start, 'the others')
    return xi


def replacement(ipm='clarabel', eps_start=distance.EPS_START):
    """A `distance.select` replacement for the library's Solver (the correctness runs)."""

    def chosen(face, w, budget, work):
        return select(face, w, budget, work, ipm, eps_start)

    return chosen


def run(tag, ipm, eps_start, repeat):
    state = lab.read(tag)
    times, answers, work = [], [], None
    for _ in range(repeat):
        work = Work()
        clock = time.perf_counter()
        xi = select(copy.deepcopy(state['face']), state['w'], Budget(), work, ipm, eps_start)
        times.append(time.perf_counter() - clock)
        answers.append(xi)
    same = all(np.array_equal(a, answers[0]) for a in answers[1:]) if repeat > 1 else None
    try:
        reference = np.load(f'{lab.DATA}/{tag}-library.npy')
    except FileNotFoundError:
        reference = None
    found = lab.measures(state, answers[0], reference)
    infos = dict(newton=work.newton, methods=work.methods, ipm=work.ipm, times=work.times, factorizations=work.factorizations)
    record = dict(tag=tag, method=f'hybrid-{ipm}-eps{eps_start:g}', seconds=min(times), all=times, repeat=repeat,
                  bitwise=same, infos=infos, measures=found, load=lab.load(), version=lab.library_version())  # fmt: skip
    with open(f'{lab.DATA}/distance.jsonl', 'a') as f:
        f.write(json.dumps(record, default=str) + '\n')
    print(f'{tag} hybrid {ipm} eps {eps_start:g}: {min(times):.2f} s (of {repeat}: '
          f'{", ".join(f"{t:.2f}" for t in times)}), bitwise {same}; {infos}; {lab.fmt(found)} [load {lab.load()}]',
          flush=True)  # fmt: skip


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
    eps_start = option('--eps', distance.EPS_START, float)
    repeat = option('--repeat', 1, int)
    qp._clarabel_iterations()
    run(args[0], ipm, eps_start, repeat)
