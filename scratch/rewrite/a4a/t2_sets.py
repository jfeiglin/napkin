"""Task 2 of brief A4a: connected sets, the three ways of running, and where the limits are.

    python t2_sets.py component OUT KIND PLACES [rings] [RUNS]
        One connected set as one component of the present general tier: the model of `model.py`
        with PLACES places, each row written out. KIND is the request of a route (`model.KINDS`):
        `constant` reads nothing that moves; `linear`, `saturating` and `target` read a stock.
        Needs the copy of the package with 01_id_column.patch on PYTHONPATH.
    python t2_sets.py sets OUT PLACES ROUTES
        The connected sets of the model, as the rule of FINDINGS.md cuts them, and the way of each.
    python t2_sets.py sparse OUT PLACES ROUTES
        A large set whose requests read a stock: the cost of the integration on sparse arrays, and
        the cost of one sharing and of one linear program at a state. Needs the package (any copy)
        on PYTHONPATH, for its solver adapter.

Each part prints what it finds and writes OUT/<part>….json. `measure.py` runs them all.
"""

from __future__ import annotations

import json
import os
import resource
import sys
import time
from pathlib import Path

import numpy as np
import scipy.sparse as sp

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import layout  # noqa: E402
import model  # noqa: E402

HORIZON = 300.0
MEMORY_LIMIT = 5 * 1024**3  # a case that needs more stops with MemoryError, and is reported so


def load():
    return [round(x, 2) for x in os.getloadavg()]


def save(out, name, data):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    (out / f'{name}.json').write_text(json.dumps(data, indent=1, default=float))


# ---- one component of the present general tier ---------------------------------------------------


def component(out, kind, places, rings=False, runs=1):
    resource.setrlimit(resource.RLIMIT_AS, (MEMORY_LIMIT, MEMORY_LIMIT))
    from napkin.engine import allocation
    from napkin.engine.continuous import fields
    from napkin.engine.errors import SimulationError
    from napkin.engine.runtime import simulate
    from napkin.model.ir import ModelError, thaw
    from napkin.model.model import build_model

    routes = places * 7 // 6
    folder = model.write(
        Path(out) / 'component' / f'{kind}_{places}_{int(rings)}',
        *model.synthetic(places, routes, seed=1, rings=rings),
        horizon=HORIZON,
        kind=kind,
    )
    spent = {'rates': [0, 0.0], 'allocated': [0, 0.0], 'linear_program': [0, 0.0]}

    def timed(owner, name):
        inner = getattr(owner, name)

        def wrapper(self, *args, **kwargs):
            start = time.perf_counter()
            try:
                return inner(self, *args, **kwargs)
            finally:
                spent[name][0] += 1
                spent[name][1] += time.perf_counter() - start

        setattr(owner, name, wrapper)

    timed(fields.Field, 'rates')
    timed(allocation.Allocation, 'allocated')
    timed(allocation.Allocation, 'linear_program')
    row = {
        'kind': kind, 'places': places, 'routes': routes, 'rings': rings, 'stores': 2 * places,
        'flows': routes + places, 'horizon_h': HORIZON, 'runs': runs, 'load': load(),
        'dense_matrix_MB': 2 * places * (routes + places) * 8 / 1e6,
    }
    try:
        builds, simulations = [], []
        for _ in range(runs):
            for item in spent.values():
                item[0], item[1] = 0, 0.0
            start = time.perf_counter()
            built = build_model(folder / 'model.scn')
            resolved = built.resolve(next(iter(built.runs)))
            builds.append(time.perf_counter() - start)
            start = time.perf_counter()
            trajectory = simulate(resolved, thaw(built.library))
            simulations.append(time.perf_counter() - start)
        calls, inside = spent['rates']
        row.update(
            build_s=min(builds), simulate_s=min(simulations), evaluations=int(trajectory.evaluations),
            segments=len(trajectory._segments), steps=len(trajectory.trace),
            ms_per_evaluation=1e3 * inside / max(1, calls),
            share_of_run_in_evaluations=inside / simulations[-1],
            share_of_evaluation_in_allocation=spent['allocated'][1] / max(inside, 1e-12),
            linear_programs=spent['linear_program'][0], linear_program_s=spent['linear_program'][1],
        )
    except MemoryError:
        row['failed'] = f'MemoryError: more than {MEMORY_LIMIT / 1024**3:g} GB'
    except ModelError as problem:
        row['failed'] = 'ModelError: ' + problem.diagnostics[0]['message']
    except SimulationError as problem:
        row['failed'] = f'SimulationError: {problem}'
    row['peak_memory_MB'] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
    print(json.dumps(row, default=float))
    save(out, f'component_{kind}_{places}_{int(rings)}', row)


# ---- the connected sets ---------------------------------------------------------------------------


def joined(count, pairs):
    """(the number of sets, the set of each of `count` parts) when each pair of `pairs` is joined."""
    a = np.concatenate([np.asarray(pair[0]) for pair in pairs]) if pairs else np.zeros(0, dtype=int)
    b = np.concatenate([np.asarray(pair[1]) for pair in pairs]) if pairs else np.zeros(0, dtype=int)
    graph = sp.coo_array((np.ones(len(a), dtype=np.int8), (a, b)), shape=(count, count))
    return sp.csgraph.connected_components(graph, directed=False)


def cut(built, reads=None, solver=None, tallies_join=False):
    """The connected sets of the stores and the flows of a model. A part is a store (its place) or a
    flow (the count of the stores, plus its place). What joins two parts:

    1. a flow and the store at an end of it, when that end can hold the flow back: the store has a
       bound on that side that it can reach (a lower bound at the source, an upper bound at the
       sink), or the scope of the end has a limit, a request or a rule of sharing. In this model a
       stock has a lower bound and a tally (`used`) has no bound that it can reach, so a flow joins
       its source and a stock at its sink, and not a tally at its sink (`tallies_join` joins it
       too: the plain rule);
    2. a flow and each store that its request, its limit or a factor of it reads, when that store
       moves between moments (`reads`: for each flow the places that it reads, as (flows, places));
    3. the flows whose rates one solver sets (`solver`: their places).

    The legs of one flow with legs are joined too; this model has none."""
    S, F = built.stores.count, built.net.count
    net = built.net
    used_at = built.stores.offset['places', 'used']
    is_tally = np.zeros(S, dtype=bool)
    is_tally[used_at : used_at + built.places.n] = True
    flows = np.arange(F)
    pairs = []
    out = net.src >= 0
    pairs.append((S + flows[out], net.src[out]))
    into = (net.dst >= 0) & (tallies_join | ~is_tally[np.maximum(net.dst, 0)])
    pairs.append((S + flows[into], net.dst[into]))
    if reads is not None:
        pairs.append((S + np.asarray(reads[0]), np.asarray(reads[1])))
    if solver is not None and len(solver) > 1:
        solver = np.asarray(solver)
        pairs.append((S + solver[:-1], S + solver[1:]))
    count, label = joined(S + F, pairs)
    return count, label[:S], label[S:]


COMPONENT_LIMIT = 150  # the most stores of a set that runs as one component (FINDINGS.md)


def ways(built, label_stores, label_flows, moving_flows):
    """How each set runs, from its size and from whether a rate of it reads a value that moves:
    {way: (sets, stores)}. `moving_flows`: for each flow, whether its request reads a moving value."""
    count = int(max(label_stores.max(initial=-1), label_flows.max(initial=-1))) + 1
    stores = np.bincount(label_stores, minlength=count)
    flows = np.bincount(label_flows, minlength=count)
    moving = np.bincount(label_flows, weights=moving_flows.astype(float), minlength=count) > 0
    alone = (stores <= 1) & (flows <= 1)
    small = ~alone & (stores <= COMPONENT_LIMIT)
    large = stores > COMPONENT_LIMIT
    found = {
        'arrays: a store alone, or with one flow': alone,
        'one component of the continuous engine': small,
        'lines, with rates from the sparse solver at each moment': large & ~moving,
        'refused: a large set with a rate that reads a value that moves': large & moving,
    }
    return {way: (int(mask.sum()), int(stores[mask].sum())) for way, mask in found.items()}


def sets(out, places, routes):
    folder = model.write(Path(out) / 'sets' / f'{places}_{routes}', *model.synthetic(places, routes, seed=0), old=False)
    built = model.Built(folder)
    S, F = built.stores.count, built.net.count
    none = np.zeros(F, dtype=bool)
    rows = []

    def one(label, moving, **options):
        start = time.perf_counter()
        count, of_stores, of_flows = cut(built, **options)
        took = time.perf_counter() - start
        sizes = np.bincount(of_stores, minlength=count)
        row = {
            'case': label, 'sets_with_a_store': int((sizes > 0).sum()), 'largest_set_stores': int(sizes.max()),
            'cut_s': took, 'ways': ways(built, of_stores, of_flows, moving),
        }
        print(json.dumps(row))
        rows.append(row)

    one('the requests read no value that moves', none)
    one('the same, with the plain rule: a tally joins the flow into it', none, tallies_join=True)
    # The request of each route reads the stock of its origin.
    carried = np.arange(built.carried, built.carried + built.routes.n)
    moving = none.copy()
    moving[carried] = True
    one('the request of each route reads the stock of its origin', moving, reads=(carried, built.origin))
    # The request of each route reads the stock of a place that is no end of it: here the next place.
    other = (built.origin + 1) % built.places.n
    one('the request of each route reads the stock of a third place', moving, reads=(carried, other))
    # One solver sets the rate of every route.
    one('one solver sets the rate of every route', none, solver=carried)
    save(out, f'sets_{places}_{routes}', {'places': places, 'routes': routes, 'stores': S, 'flows': F, 'component_limit': COMPONENT_LIMIT, 'rows': rows})


# ---- a large set whose requests read a stock -------------------------------------------------------


def sparse(out, places, routes, horizon=48.0):
    """Every request reads the stock that it takes from: `rate * stock / (stock + half)`, for the
    routes and for the use of each place. No stock reaches its bound, so no sharing is needed, and
    the run is one integration of a smooth system."""
    from scipy.optimize import linprog

    from napkin.engine import solvers

    folder = model.write(Path(out) / 'sparse' / f'{places}_{routes}', *model.synthetic(places, routes, seed=0, moves=False), old=False)
    built = model.Built(folder)
    net = built.net
    S, F = built.stores.count, net.count
    half = 20.0
    full = built.want()
    source = net.src  # every flow of this model has a store at its source
    y0 = built.stores.start()

    def requests(y):
        held = y[source]
        return full * held / (held + half)

    def field(t, y):
        return net.B @ requests(np.maximum(y, 0.0))

    # The rate of a store reads the store at the source of each flow at it.
    reads = sp.csr_array((np.ones(F), (np.arange(F), source)), shape=(F, S))
    pattern = (abs(net.B) @ reads).tocsc()
    pattern.data[:] = 1.0
    count, label = net.islands()
    largest = np.zeros(count)
    np.maximum.at(largest, label, np.abs(y0))
    atol = 1e-10 * np.maximum(1.0, largest[label])
    row = {
        'places': places, 'routes': routes, 'stores': S, 'flows': F, 'horizon_h': horizon,
        'jacobian_nonzeros': int(pattern.nnz), 'dense_jacobian_MB': S * S * 8 / 1e6, 'load': load(),
    }
    start = time.perf_counter()
    for _ in range(20):
        field(0.0, y0)
    row['ms_per_evaluation'] = 1e3 * (time.perf_counter() - start) / 20
    times = []
    for _ in range(3):
        start = time.perf_counter()
        run = solvers.ScipyRadau().start(field, 0.0, y0, horizon, rtol=1e-9, atol=atol, jac_sparsity=pattern, max_step=np.inf)
        steps = 0
        while not run.finished:
            step = run.step()
            steps += 1
        times.append(time.perf_counter() - start)
    end = step.y
    row.update(integrate_s=min(times), solver_steps=steps, **run.counts(), least_stock_at_end=float(end[: places].min()), conservation_error_L=float(end.sum() - y0.sum()))
    # What a solve at a state costs, where stores rest on their bound. The state: the stores that the
    # run on lines has at rest at 48 h (`lines.py`, with the constant requests).
    lines = built.lines_run(horizon, moves=False).run()
    rest = lines.rest.copy()
    row['resting_stores_in_the_state'] = int(rest.sum())
    b_out = sp.csr_array((np.ones(F), (source, np.arange(F))), shape=(S, F))
    b_in = sp.csr_array((np.ones((net.dst >= 0).sum()), (net.dst[net.dst >= 0], np.flatnonzero(net.dst >= 0))), shape=(S, F))
    asked = b_out @ full

    def share():
        a = full.copy()
        for sweeps in range(1, 100_000):
            coming = b_in @ a
            short = rest & (asked > coming)
            fraction = np.ones(S)
            fraction[short] = coming[short] / asked[short]
            new = full * fraction[source]
            if np.abs(new - a).max() <= 1e-13 * full.max():
                return new, sweeps
            a = new
        raise RuntimeError('the sharing does not settle')

    start = time.perf_counter()
    for _ in range(3):
        _, sweeps = share()
    row['stand_in_sharing_ms'] = 1e3 * (time.perf_counter() - start) / 3
    row['stand_in_sharing_sweeps'] = sweeps
    # One linear program of the same state with the bundled HiGHS: serve the most of what the flows
    # ask, while no resting store falls. It stands for one solve of the solve library (A3 has the
    # real ones: ranks, fair shares and the nearest step cost more).
    rows_at = np.flatnonzero(rest)
    net_in = (b_in - b_out)[rows_at]
    times = []
    for _ in range(3):
        start = time.perf_counter()
        solved = linprog(-np.ones(F), A_ub=-net_in, b_ub=np.zeros(len(rows_at)), bounds=np.column_stack([np.zeros(F), full]), method='highs')
        times.append(time.perf_counter() - start)
    row['linear_program_s'] = min(times)
    row['linear_program_status'] = solved.message
    evaluations = row['evaluations']
    row['estimate_run_with_a_program_at_each_evaluation_h'] = evaluations * row['linear_program_s'] / 3600
    row['estimate_run_with_the_stand_in_sharing_at_each_evaluation_s'] = evaluations * row['stand_in_sharing_ms'] / 1e3
    row['peak_memory_MB'] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
    for key, value in row.items():
        print(f'   {key}: {value}')
    save(out, f'sparse_{places}_{routes}', row)


if __name__ == '__main__':
    part, out = sys.argv[1], sys.argv[2]
    if part == 'component':
        rest = sys.argv[5:]
        component(out, sys.argv[3], int(sys.argv[4]), 'rings' in rest, next((int(x) for x in rest if x.isdigit()), 1))
    elif part == 'sets':
        sets(out, int(sys.argv[3]), int(sys.argv[4]))
    elif part == 'sparse':
        sparse(out, int(sys.argv[3]), int(sys.argv[4]))
    else:
        raise SystemExit(__doc__)
