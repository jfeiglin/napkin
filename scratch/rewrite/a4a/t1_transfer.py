"""Task 1 of brief A4a: a real transfer across rows.

    python t1_transfer.py tiny OUT        the tiny model: the present engine (each row written out)
                                          and the layout of this folder, with the rows in two orders
    python t1_transfer.py probe OUT       what the table path of the present engine does with it
    python t1_transfer.py agree OUT       the layout against the present engine on random networks
    python t1_transfer.py check OUT       the layout against a second implementation (reference.py)
    python t1_transfer.py scale OUT P R   the cost to build and to run with P places and R routes
    python t1_transfer.py reorder OUT P R the same named results when the rows of both files move

`tiny` and `agree` need the copy of the package with 01_id_column.patch on PYTHONPATH. `probe` runs
with the copy that PYTHONPATH names: the base commit, or the copy with 02_table_path_probe.patch.
The other parts import nothing of the package. Each part prints what it finds and writes
OUT/<part>.json. `measure.py` runs them all.
"""

from __future__ import annotations

import json
import os
import resource
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import model  # noqa: E402
import reference  # noqa: E402

TINY_PLACES = [('depot', 10.0, 0.0), ('yard', 20.0, 0.0), ('clinic', 30.0, 0.0)]
# One route: 2 L/h from the depot to the clinic all the time, and a lot of 1.5 L at 1 h.
TINY_ROUTES = [('depot_clinic', 'depot', 'clinic', 2.0, 1.5, 1.0)]
TINY_EXPECTED = {
    0.0: {'places.depot': 10.0, 'places.yard': 20.0, 'places.clinic': 30.0},
    1.0: {'places.depot': 6.5, 'places.yard': 20.0, 'places.clinic': 33.5},  # after the lot
    3.0: {'places.depot': 2.5, 'places.yard': 20.0, 'places.clinic': 37.5},
}


def load():
    return [round(x, 2) for x in os.getloadavg()]


def best(function, runs=3):
    """(the least time of `runs` calls, the result of the last call)."""
    times = []
    for _ in range(runs):
        start = time.perf_counter()
        found = function()
        times.append(time.perf_counter() - start)
    return min(times), found


def save(out, part, data):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    (out / f'{part}.json').write_text(json.dumps(data, indent=1, default=float))


def tiny(out):
    rows = []
    for label, order in (('the order of the file', [0, 1, 2]), ('the rows of the places in another order', [2, 0, 1])):
        folder = model.write(Path(out) / 'tiny' / label.replace(' ', '_'), [TINY_PLACES[i] for i in order], TINY_ROUTES)
        built = model.Built(folder)
        run = built.lines_run(3.0)
        mine = {}
        for t in TINY_EXPECTED:
            run.run(until=t)
            mine[t] = built.stock_of(run.values(t))
        present, trajectory = model.old_run(folder, list(TINY_EXPECTED))
        moved = [(entry['t'], entry['rule'], entry['transfers']) for entry in trajectory.trace]
        print(f'{label}: places.csv = {[key for key, _, _ in (TINY_PLACES[i] for i in order)]}')
        for t, expected in TINY_EXPECTED.items():
            here = {key: present[t][key] for key in expected}
            ok = here == expected and mine[t] == expected
            print(f'   t = {t:g} h   expected {expected}   present engine {here}   layout {mine[t]}   {"same" if ok else "DIFFERENT"}')
            rows.append({'order': label, 't': t, 'expected': expected, 'present': here, 'layout': mine[t], 'same': ok})
        print(f'   the move in the trace of the present engine: {moved}')
        print(f'   the move in the trace of the layout: {run.trace}')
    save(out, 'tiny', {'rows': rows, 'all_same': all(row['same'] for row in rows)})


PLACE = '''Place:  @shape
    "A place."
    var stock: L = 10 L in 0 L to 100 L  @shape

'''
TAIL = '''
places: Place from "places.csv"
routes: Route from "routes.csv"

output held: L = sum(Place.stock)  @shape
    "Held by the places"
    level
'''
CASES = {
    'one link, a flow out of the linked stock': (
        '''Route:  @shape
    "A route."
    let origin: Place
    input rate: L/h = 1 L/h in 0 L/h to 100 L/h  @shape
    var carried_total: L = 0 L in 0 L to 1000 L  @shape
    flow carried: origin.stock -> carried_total at rate  @shape
''',
        'origin,rate: L/h @shape\nplaces.1,2\nplaces.3,1\n',
        [4.0, 20.0, 27.0],
    ),
    'one link, a move out of the linked stock': (
        '''Route:  @shape
    "A route."
    let origin: Place
    input lot: L = 1 L in 0 L to 100 L  @shape
    var carried_total: L = 0 L in 0 L to 1000 L  @shape
    event ship once when t >= 1 h:  @shape
        "The route ships its lot."
        move lot from origin.stock to carried_total
''',
        'origin,lot: L @shape\nplaces.1,1.5\nplaces.3,2.5\n',
        [8.5, 20.0, 27.5],
    ),
    'two links, a move between the linked stocks': (
        '''Route:  @shape
    "A route."
    let origin: Place
    let destination: Place
    input lot: L = 1 L in 0 L to 100 L  @shape
    event ship once when t >= 1 h:  @shape
        "The route ships its lot."
        move lot from origin.stock to destination.stock
''',
        'origin,destination,lot: L @shape\nplaces.1,places.3,1.5\nplaces.2,places.1,2.5\n',
        [11.0, 17.5, 31.5],
    ),
    'two links, a flow between the linked stocks': (
        '''Route:  @shape
    "A route."
    let origin: Place
    let destination: Place
    input rate: L/h = 1 L/h in 0 L/h to 100 L/h  @shape
    flow carried: origin.stock -> destination.stock at rate  @shape
''',
        'origin,destination,rate: L/h @shape\nplaces.1,places.3,2\nplaces.2,places.1,1\n',
        [7.0, 17.0, 36.0],
    ),
}


def probe(out, label):
    """Four small models through the two paths of the present engine. The stocks of the three
    places start at 10, 20 and 30 L, and are read at 3 h."""
    from napkin.engine import timeline
    from napkin.engine.runtime import simulate
    from napkin.model import hybrid
    from napkin.model.ir import ModelError, thaw
    from napkin.model.model import build_model

    rows = []
    for k, (case, (route, table, expected)) in enumerate(CASES.items()):
        folder = Path(out) / 'probe' / label / f'case{k}'
        folder.mkdir(parents=True, exist_ok=True)
        (folder / 'model.scn').write_text(model.HEAD.format(horizon=3) + PLACE + route + TAIL + model.RECORD)
        (folder / 'units.json').write_text(json.dumps(model.UNITS))
        (folder / 'places.csv').write_text('stock: L @shape\n10\n20\n30\n')
        (folder / 'routes.csv').write_text(table)
        path = folder / 'model.scn'
        built = build_model(path)
        env = simulate(built.resolve(next(iter(built.runs))), thaw(built.library)).env_at(3.0)
        flat = [env[f'places_{i}.stock'] for i in (1, 2, 3)]
        families = None
        try:
            core = hybrid.compile(path)
            families = [(family.host, len(family)) for family in core.families]
            result = timeline.run(timeline.Plan.of(core))
            table_path = [float(x) for x in result.final('places_1.stock')]
            said = 'runs'
        except ModelError as problem:
            table_path, said = None, 'ModelError: ' + problem.diagnostics[0]['message']
        except Exception as problem:  # the refusal by name (`Outside`), or a failure
            table_path, said = None, f'{type(problem).__name__}: {problem}'
        verdict = 'refused' if table_path is None else 'right' if table_path == expected else 'WRONG'
        print(f'{case}\n   expected {expected}; rows written out: {flat}\n   table path ({label}): {verdict}: {table_path if table_path is not None else said}; families {families}')
        rows.append({'case': case, 'expected': expected, 'flat': flat, 'table': table_path, 'said': said, 'verdict': verdict, 'families': families})
    save(out, f'probe_{label}', {'copy': label, 'rows': rows})


def agree(out):
    """The layout against the present engine, each row written out as one component, on random
    networks in which no stocks feed one another in a ring; and one network with rings."""
    rows = []
    for places, routes, seed, rings in ((30, 35, 1, False), (30, 35, 3, False), (100, 116, 1, False), (300, 350, 1, False), (30, 35, 3, True)):
        horizon = 300.0
        folder = model.write(Path(out) / 'agree' / f'{places}_{routes}_{seed}_{int(rings)}', *model.synthetic(places, routes, seed=seed, rings=rings), horizon=horizon)
        built = model.Built(folder)
        times = [2.0, 75.0, 150.0, 300.0]
        run = built.lines_run(horizon)
        mine = {}
        for t in times:
            run.run(until=t)
            values = run.values(t)
            mine[t] = {**built.stock_of(values), **{key + '.used': x for key, x in built.stock_of(values, 'used').items()}}
        start = time.perf_counter()
        present, trajectory = model.old_run(folder, times)
        took = time.perf_counter() - start
        worst = max(abs(mine[t][key] - present[t][key]) for t in times for key in mine[t])
        row = {
            'places': places, 'routes': routes, 'seed': seed, 'rings': rings,
            'depletions': run.counts['depletions'], 'moves': run.counts['moves'],
            'largest_difference_L': worst, 'present_engine_s': took, 'segments': len(trajectory._segments),
        }
        print(row)
        rows.append(row)
    save(out, 'agree', {'rows': rows, 'load': load()})


def moves_of(built):
    R = built.routes
    return [
        (float(R.cols['ship_at'][k]), int(built.origin[k]), int(built.destination[k]), float(R.cols['lot'][k]))
        for k in np.flatnonzero(R.cols['lot'] > 0)
    ]


def check(out):
    """The layout against the second implementation, on networks with rings."""
    rows = []
    for places, routes, seed in ((300, 350, 3), (3000, 3500, 1)):
        horizon = 300.0
        folder = model.write(Path(out) / 'check' / f'{places}_{routes}', *model.synthetic(places, routes, seed=seed), horizon=horizon, old=False)
        built = model.Built(folder)
        times = [2.0, 75.0, 150.0, 300.0]
        run = built.lines_run(horizon)
        mine = {}
        for t in times:
            run.run(until=t)
            mine[t] = run.values(t).copy()
        found, moments = reference.run(built.net, built.stores.start(), built.want(), horizon, moves_of(built), times)
        worst = max(float(np.abs(mine[t] - found[t]).max()) for t in times)
        row = {'places': places, 'routes': routes, 'depletions': run.counts['depletions'], 'moves': run.counts['moves'], 'largest_difference_L': worst}
        print(row)
        rows.append(row)
    save(out, 'check', {'rows': rows})


def scale(out, places, routes, horizon=48.0, runs=3):
    folder = Path(out) / 'scale' / f'{places}_{routes}'
    t_rows, rows = best(lambda: model.synthetic(places, routes, seed=0), 1)
    t_write, _ = best(lambda: model.write(folder, *rows, horizon=horizon, old=False), 1)
    size = sum((folder / name).stat().st_size for name in ('places.csv', 'routes.csv'))
    t_build, built = best(lambda: model.Built(folder), runs)
    started = []

    def whole():
        start = time.perf_counter()
        run = built.lines_run(horizon)
        started.append(time.perf_counter() - start)
        return run.run()

    t_run, run = best(whole, runs)
    t_start = min(started)
    start, end = built.stores.start(), run.values(horizon)
    count, label = built.net.islands()
    sizes = np.bincount(label)
    at, used = built.stores.offset['places', 'stock'], built.stores.offset['places', 'used']
    P = built.places.n
    row = {
        'places': places, 'routes': routes, 'stores': built.stores.count, 'flows': built.net.count,
        'horizon_h': horizon, 'csv_bytes': size,
        'write_csv_s': t_write, 'build_s': t_build, 'start_s': t_start, 'run_s': t_run - t_start,
        'moments': run.counts['moments'], 'depletions': run.counts['depletions'], 'moves': run.counts['moves'],
        'line_restarts': run.counts['line restarts'], 'share_steps': run.counts['share steps'],
        'microseconds_per_moment': 1e6 * (t_run - t_start) / max(1, run.counts['moments']),
        'resting_at_end': int(run.rest.sum()),
        'total_start_L': float(start.sum()), 'total_end_L': float(end.sum()),
        'conservation_error_L': float(end.sum() - start.sum()),
        'moved_by_flows_and_lots_L': float(np.abs(end[at : at + P] - start[at : at + P]).sum() / 2 + end[used : used + P].sum() / 2),
        'connected_sets': int(count), 'largest_set_stores': int(sizes.max()), 'sets_of_two_stores': int((sizes == 2).sum()),
        'peak_memory_MB': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024,
        'load': load(), 'runs': runs,
    }
    for key, value in row.items():
        print(f'   {key}: {value}')
    save(out, f'scale_{places}_{routes}', row)


def reorder(out, places, routes, horizon=48.0):
    """Both tables with their rows in another order, and no link cell edited: the named results."""
    rng = np.random.default_rng(7)
    place_rows, route_rows = model.synthetic(places, routes, seed=0)
    one = model.write(Path(out) / 'reorder' / 'file', place_rows, route_rows, horizon=horizon, old=False)
    moved_places = [place_rows[k] for k in rng.permutation(places)]
    moved_routes = [route_rows[k] for k in rng.permutation(routes)]
    two = model.write(Path(out) / 'reorder' / 'moved', moved_places, moved_routes, horizon=horizon, old=False)
    found = {}
    for canonical in (True, False):
        ends = []
        for folder in (one, two):
            built = model.Built(folder, canonical=canonical)
            run = built.lines_run(horizon).run()
            values = run.values(horizon)
            ends.append({**built.stock_of(values), **{key + '.used': x for key, x in built.stock_of(values, 'used').items()}})
        a, b = ends
        differ = [key for key in a if a[key] != b[key]]
        worst = max((abs(a[key] - b[key]) for key in a), default=0.0)
        found['rows in the order of their ids' if canonical else 'rows in the order of the file'] = {
            'named_values': len(a), 'values_with_other_bits': len(differ), 'largest_difference_L': worst,
        }
    for key, value in found.items():
        print(f'   {key}: {value}')
    save(out, f'reorder_{places}_{routes}', {'places': places, 'routes': routes, **found})


if __name__ == '__main__':
    part, out = sys.argv[1], sys.argv[2]
    if part == 'tiny':
        tiny(out)
    elif part == 'probe':
        probe(out, sys.argv[3])
    elif part == 'agree':
        agree(out)
    elif part == 'check':
        check(out)
    elif part == 'scale':
        scale(out, int(sys.argv[3]), int(sys.argv[4]), runs=int(sys.argv[5]) if len(sys.argv) > 5 else 3)
    elif part == 'reorder':
        reorder(out, int(sys.argv[3]), int(sys.argv[4]))
    else:
        raise SystemExit(__doc__)
