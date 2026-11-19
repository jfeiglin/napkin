"""Prototype P1, the distance step: the library's method against Clarabel, PIQP and OSQP.

Not a test and not linted. Each candidate solves the library's two stages on the face exported at
the start of `distance.select` (`lab.export`): the flows nearest their targets, then, with the flows
fixed, the other unknowns nearest their references,

    min 1/2 sum_j w_j (x_j - c_j)^2   with   row_lower <= A x <= row_upper,   lower <= x <= upper,

w_j one on the coordinates of the stage and zero elsewhere, in working units. A candidate gets the
problem as the library's method does: the fixed columns moved into the rows' bounds, rows with no
free column dropped (they hold to LOOSE, as the method checks), then through `qpsolvers` as
equalities, one-sided inequalities and bounds. Its answer is clipped into the bounds before the
flows are fixed, as the library's QP fallback does.

    /home/user/venvs/p1/bin/python scratch/rewrite/p1/qp.py TAG METHOD [--repeat R] [--save]

METHOD is `library`, `library-loose` (the method with its row tolerance TOL at 1e-7), or a candidate
of METHODS. Prints one line and appends a record to /home/user/p1-data/distance.jsonl; `--save`
keeps the answer (DATA/TAG-METHOD.npy), and the answer of `library` is the reference of the others.
"""

import json
import sys
import time

import lab  # sets the thread variables first
import numpy as np
import scipy.sparse as sp

from napkin.engine.solve import FLOW, OTHER, Budget, distance
from napkin.engine.solve.solver import Work

LOOSE = 1e-6  # a row of fixed columns alone holds to this times (1 + its size), as in the method

# name: (qpsolvers solver, options). One thread each; the tolerances are each solver's own.
METHODS = {
    'clarabel': ('clarabel', dict(max_threads=1)),
    'clarabel-tight': ('clarabel', dict(max_threads=1, tol_gap_abs=1e-10, tol_gap_rel=1e-10, tol_feas=1e-10)),
    'clarabel-loose': ('clarabel', dict(max_threads=1, tol_gap_abs=1e-6, tol_gap_rel=1e-6, tol_feas=1e-7)),
    'piqp': ('piqp', dict(backend='sparse')),
    'piqp-tight': ('piqp', dict(backend='sparse', eps_abs=1e-10, eps_rel=1e-11)),
    'piqp-loose': ('piqp', dict(backend='sparse', eps_abs=1e-6, eps_rel=1e-7)),
    'piqp-long': ('piqp', dict(backend='sparse', max_iter=1000)),
    'osqp': ('osqp', dict(eps_abs=1e-6, eps_rel=1e-6, max_iter=200_000, polishing=True, time_limit=840)),
    'osqp-tight': ('osqp', dict(eps_abs=1e-9, eps_rel=1e-9, max_iter=400_000, polishing=True, time_limit=840)),
}
# `NAME-box`: the same, but the second stage holds the flows within BOX (relative) of the first
# stage's values instead of exactly: a first stage met to its solver's tolerance leaves the rows of
# the second (the levels, with every flow fixed) inconsistent by that much (PIQP stops there).
BOX = {'clarabel': 1e-8, 'piqp': 1e-8, 'osqp': 1e-6}
for _name in list(METHODS):
    METHODS[f'{_name}-box'] = METHODS[_name]


def reduced(A, row_lower, row_upper, lower, upper, target, weight):
    """The stage with its fixed columns moved into the rows' bounds and its empty rows dropped, as
    `qpsolvers` takes it: dict(P, q, G, h, A, b, lb, ub) over the free columns, and `free`, `x` (the
    fixed values in place)."""
    A = sp.csr_array(A)
    fixed = upper <= lower
    x = np.where(fixed, np.minimum(lower, upper), 0.0)
    free = np.flatnonzero(~fixed)
    shift = A[:, np.flatnonzero(fixed)] @ x[fixed] if fixed.any() else np.zeros(A.shape[0])
    size = abs(A[:, np.flatnonzero(fixed)]) @ np.abs(x[fixed]) if fixed.any() else np.zeros(A.shape[0])
    B = sp.csr_array(A[:, free])
    lo, hi = row_lower - shift, row_upper - shift
    empty = np.diff(B.indptr) == 0
    slack = LOOSE * (1.0 + size)
    if np.any(empty & ((lo > slack) | (hi < -slack))):
        raise ValueError('a row of fixed columns fails')
    keep = ~empty & (np.isfinite(lo) | np.isfinite(hi))
    B, lo, hi = sp.csr_array(B[np.flatnonzero(keep)]), lo[keep], hi[keep]
    equal = lo == hi
    up = ~equal & np.isfinite(hi)
    down = ~equal & np.isfinite(lo)
    G = sp.vstack([B[np.flatnonzero(up)], -B[np.flatnonzero(down)]]).tocsc()
    h = np.r_[hi[up], -lo[down]]
    w = weight[free]
    P = sp.diags_array(w).tocsc()
    q = -w * target[free]
    return dict(
        P=P,
        q=q,
        G=G if G.shape[0] else None,
        h=h if G.shape[0] else None,
        A=sp.csc_array(B[np.flatnonzero(equal)]) if equal.any() else None,
        b=lo[equal] if equal.any() else None,
        lb=lower[free],
        ub=upper[free],
        free=free,
        x=x,
        rows=np.flatnonzero(keep),
        equal=equal,
        up=up,
        down=down,
    )


def candidate_stage(name, A, row_lower, row_upper, lower, upper, target, weight, duals=False):
    """One stage by the candidate `name`; gives (x, info), and with `duals` also the dual of each
    kept row in the library's sign (W(x - c) + B'y = 0 on the free columns) and the form."""
    import qpsolvers

    solver, options = METHODS[name]
    clock = time.perf_counter()
    form = reduced(A, row_lower, row_upper, lower, upper, target, weight)
    formed = time.perf_counter() - clock
    if not len(form['free']):  # every column fixed: nothing to solve (OSQP refuses n = 0)
        info = dict(found=True, status='empty', iterations=0, formed=formed, solve=0.0, build=0.0, free=0, rows=(0, 0))
        if duals:
            form['y'] = np.zeros(len(form['rows']))
            return form['x'].copy(), info, form
        return form['x'].copy(), info
    problem = qpsolvers.Problem(
        sp.csc_matrix(form['P']),
        form['q'],
        None if form['G'] is None else sp.csc_matrix(form['G']),
        form['h'],
        None if form['A'] is None else sp.csc_matrix(form['A']),
        form['b'],
        form['lb'],
        form['ub'],
    )
    solution = qpsolvers.solve_problem(problem, solver=solver, **options)
    x = form['x'].copy()
    x[form['free']] = np.clip(solution.x, form['lb'], form['ub']) if solution.x is not None else np.nan
    extras = solution.extras or {}
    info = extras.get('info')
    if solver == 'clarabel':
        status = str(extras.get('status')).split('.')[-1]
        iterations = getattr(_clarabel_iterations, 'last', None)
    elif solver == 'piqp':
        status, iterations = str(info.status).split('.')[-1], int(info.iter)
    else:
        status, iterations = str(info.status), int(info.iter)
    if duals:
        y = np.zeros(len(form['rows']))
        if form['A'] is not None and solution.y is not None:
            y[form['equal']] = solution.y
        if form['G'] is not None and solution.z is not None:
            z = np.asarray(solution.z)
            k = int(form['up'].sum())
            y[form['up']] += z[:k]
            y[form['down']] -= z[k:]
        form['y'] = y
    info = dict(
        found=bool(solution.found),
        status=status,
        iterations=iterations,
        formed=formed,
        solve=solution.solve_time,
        build=solution.build_time,
        free=len(form['free']),
        rows=(0 if form['A'] is None else form['A'].shape[0], 0 if form['G'] is None else form['G'].shape[0]),
    )
    return (x, info, form) if duals else (x, info)


def candidate(name, state):
    """The two stages by a candidate, as `distance.select` orders them; gives (xi, infos)."""
    A, row_lower, row_upper, lower, upper, target, kind = lab.distance_problem(state)
    flows, others = kind == FLOW, kind == OTHER
    infos, xi = [], None
    if flows.any():
        xi, info = candidate_stage(name, A, row_lower, row_upper, lower, upper, target, flows * 1.0)
        infos.append(info)
        if name.endswith('-box'):
            width = BOX[METHODS[name][0]] * (1.0 + np.abs(xi[flows]))
            lower[flows] = np.maximum(lower[flows], xi[flows] - width)
            upper[flows] = np.minimum(upper[flows], xi[flows] + width)
        else:
            lower[flows] = upper[flows] = xi[flows]
    if others.any() or xi is None:
        xi, info = candidate_stage(name, A, row_lower, row_upper, lower, upper, target, others * 1.0)
        infos.append(info)
    return xi, infos


def _clarabel_iterations():
    """qpsolvers drops Clarabel's iteration count: read it from the result by a wrapper."""
    import clarabel

    solve = clarabel.DefaultSolver.solve

    def counted(self):
        result = solve(self)
        _clarabel_iterations.last = int(result.iterations)
        return result

    clarabel.DefaultSolver.solve = counted


def run(tag, method, repeat=1, save=False):
    state = lab.read(tag)
    times, answers, infos = [], [], None
    for _ in range(repeat):
        clock = time.perf_counter()
        if method.startswith('library'):
            if method == 'library-loose':
                distance.TOL = 1e-7
            work = Work()
            import copy

            xi = distance.select(copy.deepcopy(state['face']), state['w'], Budget(), work)
            infos = dict(newton=work.newton, methods=work.methods, factorizations=work.factorizations, qp=work.qp)
        else:
            xi, infos = candidate(method, state)
        times.append(time.perf_counter() - clock)
        answers.append(xi)
    same = all(np.array_equal(a, answers[0]) for a in answers[1:]) if repeat > 1 else None
    reference = None
    try:
        reference = np.load(f'{lab.DATA}/{tag}-library.npy')
    except FileNotFoundError:
        pass
    found = lab.measures(state, answers[0], None if method == 'library' else reference)
    record = dict(
        tag=tag,
        method=method,
        seconds=min(times),
        all=times,
        repeat=repeat,
        bitwise=same,
        infos=infos,
        measures=found,
        load=lab.load(),
        version=lab.library_version(),
    )
    with open(f'{lab.DATA}/distance.jsonl', 'a') as f:
        f.write(json.dumps(record, default=str) + '\n')
    if save:
        np.save(f'{lab.DATA}/{tag}-{method}.npy', answers[0])
    print(
        f'{tag} {method}: {min(times):.2f} s (of {repeat}: {", ".join(f"{t:.2f}" for t in times)}), '
        f'bitwise {same}; {infos}; {lab.fmt(found)} [load {lab.load()}]',
        flush=True,
    )


if __name__ == '__main__':
    args = sys.argv[1:]
    repeat = 1
    if '--repeat' in args:
        i = args.index('--repeat')
        repeat = int(args[i + 1])
        del args[i : i + 2]
    save = '--save' in args
    if save:
        args.remove('--save')
    _clarabel_iterations()
    run(args[0], args[1], repeat, save)
