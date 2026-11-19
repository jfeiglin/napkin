"""Prototype P1, the shared parts: problems, the library's order up to a step, and the checks.

Not a test and not linted. Run with the environment /home/user/venvs/p1 and
PYTHONPATH=/home/user/napkin, one thread (the variables below are set before numpy loads):

    /home/user/venvs/p1/bin/python scratch/rewrite/p1/lab.py export SHARE SCENARIO
    /home/user/venvs/p1/bin/python scratch/rewrite/p1/lab.py engine PLACES

- `scenario_problem`: A3's network as the library's bench forms it (`b1/solve/bench.py`), in A3's
  scenarios normal, shortage (need x1.45), damaged and global (need x1.7).
- `engine_problem`: the `Problem` that the engine gives `Solver.solve` at its first solve, from the
  engine's bench (`b1/s5-engine/bench.py`), caught there and pickled.
- `prefix`: the library's order on a fresh `Solver` up to the start of the distance step; gives the
  state there (w, face, optima, levels) and the state after the objective (face, basis), which the
  fair-sharing variants start from. `export` pickles both into /home/user/p1-data.
- `measures`: what the brief asks of an answer: the largest violation of a row or a bound, the change
  of each kept optimum and fair level, and the strict invariants (each store balances, equal claims
  get equal shares, each value in its range), each relative to its size.
"""

import os

for _name in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS', 'RAYON_NUM_THREADS'):
    os.environ.setdefault(_name, '1')

import copy  # noqa: E402
import hashlib  # noqa: E402
import importlib.util  # noqa: E402
import pickle  # noqa: E402
import sys  # noqa: E402
import time  # noqa: E402

import numpy as np  # noqa: E402
import scipy.sparse as sp  # noqa: E402

NAPKIN = '/home/user/napkin'
DATA = '/home/user/p1-data'
sys.path.insert(0, NAPKIN)

from napkin.engine.solve import FLOW, OTHER, Solver, distance, fair, ranked  # noqa: E402
from napkin.engine.solve.scaled import Scaled  # noqa: E402
from napkin.engine.solve.solver import Work, _check_hard  # noqa: E402

SCENARIOS = ('normal', 'shortage', 'damaged', 'global')


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def library_version():
    """The commit of the checkout and a hash of the library's files as they are read now."""
    digest = hashlib.sha256()
    folder = f'{NAPKIN}/napkin/engine/solve'
    for name in sorted(os.listdir(folder)):
        if name.endswith('.py'):
            with open(f'{folder}/{name}', 'rb') as f:
                digest.update(name.encode() + f.read())
    with open(f'{NAPKIN}/.git/HEAD') as f:
        head = f.read().strip()
    if head.startswith('ref: '):
        with open(f'{NAPKIN}/.git/{head[5:]}') as f:
            head = f.read().strip()
    return f'{head[:7]}+{digest.hexdigest()[:12]}'


def load():
    return round(os.getloadavg()[0], 2)


_bench = None


def bench():
    global _bench
    if _bench is None:
        _bench = load_module('p1_solve_bench', f'{NAPKIN}/scratch/rewrite/b1/solve/bench.py')
    return _bench


def scenario_problem(share, name):
    b = bench()
    net, need, up = b.scenario(share, name)
    return b.network_problem(net, need, up)


def engine_problem(places):
    """The Problem of the engine's first solve at `places` places (A3's proportions), from the pickle
    that `engine` writes."""
    with open(f'{DATA}/engine-{places}.pkl', 'rb') as f:
        return pickle.load(f)


class _Exported(Exception):
    pass


def export_engine(places):
    """Run the engine's bench program until its first solve and pickle the Problem given there."""
    engine = load_module('p1_engine_bench', f'{NAPKIN}/scratch/rewrite/b1/s5-engine/bench.py')
    from napkin.engine.timeline.run import Run
    from napkin.engine.timeline import Plan
    from napkin.program.config import Configuration, Request

    def caught(self, problem):
        with open(f'{DATA}/engine-{places}.pkl', 'wb') as f:
            pickle.dump(problem, f, protocol=pickle.HIGHEST_PROTOCOL)
        raise _Exported

    Solver.solve = caught
    clock = time.perf_counter()
    source, net = engine.program(places, int(places * 35 / 30), places // 2)
    plan = Plan.of(source, Configuration(Request(48)))
    try:
        Run(plan).run()
    except _Exported:
        pass
    print(f'engine {places}: exported in {time.perf_counter() - clock:.1f} s [load {load()}]', flush=True)


def prefix(problem, share=None, budget=None):
    """The library's order up to the start of the distance step, on a fresh Solver, timed by step.
    `share` replaces `fair.share` (same signature). Gives a dict: w, face (at the distance start),
    objective_face and basis (after the objective), optima, levels, work, times, kept (the Solver's
    instance, for a variant that continues on it)."""
    solver = Solver(budget)
    arrays = problem.arrays()
    _check_hard(arrays)
    w = solver._follow(Scaled(arrays))
    kept, work = solver._kept, Work()
    face = ranked.Face(w)
    times = {}
    clock = time.perf_counter()
    optima = ranked.optimize(kept, face, w, work)
    times['objective'] = time.perf_counter() - clock
    basis = kept.s.getBasis()
    after = dict(
        face=copy.deepcopy(face),
        col_status=np.array([int(s) for s in basis.col_status], np.int8),
        row_status=np.array([int(s) for s in basis.row_status], np.int8),
        iterations=kept.iterations,
    )
    clock = time.perf_counter()
    levels = (share or fair.share)(kept, face, w, solver.budget, work)
    times['fair'] = time.perf_counter() - clock
    work.iterations = kept.iterations
    work.renewals = kept.renewals
    return dict(
        w=w, face=face, optima=optima, levels=levels, work=work, times=times, after=after, solver=solver
    )


BUDGET_PROGRAMS = 5000  # the fair-sharing budget of the exports, as `bench.py --fair-programs 5000`


def export(problem, tag):
    """`prefix` with the library's fair sharing, pickled as DATA/tag.pkl (without the instance). The
    fair-sharing budget is BUDGET_PROGRAMS (the default 1,000 stops need x1.45 and x1.7 at 30,000)."""
    from napkin.engine.solve import Budget

    clock = time.perf_counter()
    state = prefix(problem, budget=Budget(fair_programs=BUDGET_PROGRAMS))
    state.pop('solver')
    state['version'] = library_version()
    state['load'] = load()
    with open(f'{DATA}/{tag}.pkl', 'wb') as f:
        pickle.dump(state, f, protocol=pickle.HIGHEST_PROTOCOL)
    work, times = state['work'], state['times']
    print(
        f'export {tag}: objective {times["objective"]:.2f} s, fair {times["fair"]:.2f} s, '
        f'{work.fair_programs} programs, {work.levels} levels, {work.iterations} iterations, '
        f'{work.tight} tight, {work.renewals} renewals; total {time.perf_counter() - clock:.1f} s '
        f'[load {load()}] [{state["version"]}]',
        flush=True,
    )
    return state


def read(tag):
    with open(f'{DATA}/{tag}.pkl', 'rb') as f:
        return pickle.load(f)


# -- the distance problem at its start --------------------------------------------------------------
def distance_problem(state):
    """The arrays that `distance.select` reads: (A, row_lower, row_upper, lower, upper, target, kind),
    in working units."""
    w, face = state['w'], state['face']
    A, row_lower, row_upper = face.arrays(w.A)
    return sp.csr_array(A), row_lower, row_upper, face.lower.copy(), face.upper.copy(), w.target, w.kind


def library_distance(state, budget=None):
    """The library's two distance stages on the exported face; gives (xi, work, seconds)."""
    from napkin.engine.solve import Budget

    work = Work()
    clock = time.perf_counter()
    xi = distance.select(copy.deepcopy(state['face']), state['w'], budget or Budget(), work)
    return xi, work, time.perf_counter() - clock


# -- measures -------------------------------------------------------------------------------------
def positive(w, xi):
    """xi with each positive part recomputed as max(0, e.x + e0), as the answer does."""
    x = w.arrays.positive_parts(w.author(xi))
    return x[w.columns] / w.scale


def _row_miss(A, lower, upper, x):
    value = A @ x
    size = 1.0 + abs(A) @ np.abs(x)
    miss = np.maximum(np.maximum(lower - value, value - upper), 0.0)
    return float((miss / size).max(initial=0.0)), float(miss.max(initial=0.0))


def _bound_miss(lower, upper, x):
    miss = np.maximum(np.maximum(lower - x, x - upper), 0.0)
    return float((miss / (1.0 + np.abs(x))).max(initial=0.0)), float(miss.max(initial=0.0))


def store_rows(w):
    """The rows of the problem that are the books of a store: ('balance', i) in the bench's problem,
    ('store', name, side) in the engine's."""
    keys = w.arrays.row_keys
    return np.array(
        [isinstance(keys[i], tuple) and keys[i][0] in ('balance', 'store') for i in w.rows.tolist()], bool
    )


def engine_polished(state, xi):
    """xi after the engine's polish (`timeline/declared.polished`, NEAR 1e-6, then clipped into the
    bounds, as `DeclaredWay.answer` does), in working units; the first solve's order is the problem's."""
    from napkin.engine.timeline.declared import polished

    w = state['w']
    arrays = w.arrays
    x = arrays.positive_parts(w.author(np.asarray(xi, float)))
    x = np.clip(polished(arrays, x, state['levels']), arrays.lower, arrays.upper)
    return x[w.columns] / w.scale


def measures(state, xi, reference=None, polish=True):
    """The measures of an answer xi (working units, the instance's order) on the state's problem;
    with `polish`, also the strict invariants after the engine's polish (keys 'p ...')."""
    w, face, levels, optima = state['w'], state['face'], state['levels'], state['optima']
    raw = np.asarray(xi, float)
    if polish:
        polished_reference = None if reference is None else engine_polished(state, reference)
        after = measures(state, engine_polished(state, raw), polished_reference, polish=False)
    xi = positive(w, raw)
    out = {}
    out['rows'] = _row_miss(w.A, w.row_lower, w.row_upper, xi)[0]
    A, row_lower, row_upper = face.arrays(w.A)
    out['face rows'] = _row_miss(sp.csr_array(A), row_lower, row_upper, xi)[0]
    out['bounds'] = _bound_miss(w.lower, w.upper, xi)[0]
    out['bounds abs'] = _bound_miss(w.lower, w.upper, xi)[1]
    out['face bounds'] = _bound_miss(face.lower, face.upper, xi)[0]
    # the kept optima, by the measure of `ranked.lost` (the library refuses above 1e-7)
    out['optima'] = max(
        [float((c @ xi - best) / (np.abs(c) @ (1.0 + np.abs(xi)))) for c, best in zip(w.costs, optima)],
        default=0.0,
    )
    # the fair levels: shortfall of the served fraction below its level (the library refuses above
    # 1e-6 of the size of its terms), and the largest rise above it
    if len(levels):
        served = w.F @ xi
        fraction = np.minimum(served, 1.0)
        size = 1.0 + abs(w.F) @ np.abs(xi)
        out['level short'] = float(((np.minimum(levels, 1.0) - served) / size).max(initial=0.0))
        out['level rise'] = float((fraction - levels).max(initial=0.0))
        # equal treatment: the claims of one level are served one fraction
        groups = np.round(levels / 1e-6).astype(np.int64)
        spread = 0.0
        below = levels < 1.0 - 1e-9
        if below.any():
            g, inverse = np.unique(groups[below], return_inverse=True)
            high = np.full(len(g), -np.inf)
            low = np.full(len(g), np.inf)
            np.maximum.at(high, inverse, fraction[below])
            np.minimum.at(low, inverse, fraction[below])
            spread = float((high - low).max(initial=0.0))
        out['equal spread'] = spread
    # conservation: the books of each store, in author units of the rate and relative to the terms
    books = store_rows(w)
    if books.any():
        x = w.author(xi)  # author units, the problem's order
        rows = w.rows[books]
        Aa = w.arrays.A[rows]
        value = Aa @ x
        lo, hi = w.arrays.row_lower[rows], w.arrays.row_upper[rows]
        miss = np.maximum(np.maximum(lo - value, value - hi), 0.0)
        out['books abs'] = float(miss.max(initial=0.0))
        out['books'] = float((miss / (1.0 + abs(Aa) @ np.abs(x))).max(initial=0.0))
    if reference is not None:
        ref = positive(w, np.asarray(reference, float))
        diff = np.abs(xi - ref) / (1.0 + np.abs(ref))
        out['diff flows'] = float(diff[w.kind == FLOW].max(initial=0.0))
        out['diff others'] = float(diff[w.kind == OTHER].max(initial=0.0))
    if polish:
        for key in ('rows', 'bounds abs', 'level short', 'equal spread', 'books', 'books abs', 'diff flows'):
            if key in after:
                out[f'p {key}'] = after[key]
    return out


def fmt(values):
    return ', '.join(f'{k} {v:.1e}' if isinstance(v, float) else f'{k} {v}' for k, v in values.items())


if __name__ == '__main__':
    command = sys.argv[1]
    if command == 'export':
        share, name = float(sys.argv[2]), sys.argv[3]
        export(scenario_problem(share, name), f'bench-{int(30000 * share)}-{name}')
    elif command == 'engine':
        export_engine(int(sys.argv[2]))
    elif command == 'export-engine':
        places = int(sys.argv[2])
        export(engine_problem(places), f'engine-{places}-normal')
    else:
        raise SystemExit(f'unknown command {command}')
