"""The benchmark of S2-E (a benchmark, not a test): the 30,000-place network of A4a, with its routes
as flows between place rows.

Each place has a stock and a tally `used`, and `flow use: this.stock -> this.used`; each route row
links an origin and a destination place and carries `flow carried: this.origin.stock ->
this.destination.stock`. The rows are A4a's random network (`a4a/model.py`, `synthetic`, without
moves and without rings, so no ring of empty stocks can form). Two cases:

- `held`: the requests are inputs, with a capacity at the request (a pipe that carries no more than it
  asks), so the rates change only at moments: the stocks run on lines (`timeline/lines.py`), and
  each stock that empties shares what reaches it among its outflows;
- `moving`: each request reads its origin's stock, `rate * stock / (stock + half)` (A4a's T2.3), so
  the set runs on the sparse integrator (`timeline/sparse.py`); no stock reaches its bound.

    cd /home/user/napkin && OPENBLAS_NUM_THREADS=1 .venv/bin/python scratch/rewrite/b1/s2-engine/bench.py held 30000 35000
"""

import sys
import time

import numpy as np

from napkin.engine import read
from napkin.engine.timeline import Plan, Run
from napkin.engine.timeline.lines import Lines
from napkin.engine.timeline.sparse import Sparse
from napkin.program.build import Builder, flow, formula, input_, link, named, q, this, value
from napkin.program.config import Configuration, Request
from napkin.program.record import Key

HALF = 20.0  # L, the stock at which a moving request asks half its rate


def synthetic(places, routes, seed=0):
    """A4a's random network without moves and rings: (stock, need) of each place, (origin,
    destination, rate) of each route; no place empties before 2 h."""
    rng = np.random.default_rng(seed)
    stock = np.round(rng.uniform(20.0, 200.0, places), 3)
    origin = rng.integers(0, places, routes)
    destination = (origin + rng.integers(1, places, routes)) % places
    origin, destination = np.minimum(origin, destination), np.maximum(origin, destination)
    rate = np.round(rng.uniform(0.2, 4.0, routes), 3)
    need = np.where(rng.uniform(size=places) < 0.5, np.round(rng.uniform(0.5, 6.0, places), 3), 0.0)
    out = np.bincount(origin, weights=rate, minlength=places) + need
    scale = np.minimum(1.0, 0.9 * stock / np.maximum(2.0 * out, 1e-9))
    return stock, need * scale, origin, destination, rate * scale[origin]


def program(kind, places, routes):
    stock, need, origin, destination, rate = synthetic(places, routes)
    b = Builder({'h': {'time': 1}, 'L': {'volume': 1}})
    if kind == 'held':
        asked = this.need, this.need
        carried = this.rate, this.rate
    else:
        own = this.stock / (this.stock + q(HALF, 'L'))
        far = this.origin.stock / (this.origin.stock + q(HALF, 'L'))
        asked = formula(this.need * own), None
        carried = formula(this.rate * far), None
    place = b.template(
        'Place',
        input_('initial', 'L', 0),
        input_('need', 'L/h', 0),
        value('stock', 'L', this.initial, lower=0, upper=1_000_000),
        value('used', 'L', 0, lower=0, upper=1_000_000),
        flow('use', this.stock, this.used, request=asked[0], capacity=asked[1]),
    )
    route = b.template(
        'Route',
        link('origin', 'Place'),
        link('destination', 'Place'),
        input_('rate', 'L/h', 0),
        flow('carried', this.origin.stock, this.destination.stock, request=carried[0], capacity=carried[1]),
    )
    width = len(str(places))
    pid = [f'p{k:0{width}d}' for k in range(places)]
    b.table(
        'places',
        place,
        [{'id': pid[k], 'initial': float(stock[k]), 'need': float(need[k])} for k in range(places)],
    )
    b.table(
        'routes',
        route,
        [
            {
                'id': f'r{k:0{len(str(routes))}d}',
                'origin': named(f'places.{pid[origin[k]]}'),
                'destination': named(f'places.{pid[destination[k]]}'),
                'rate': float(rate[k]),
            }
            for k in range(routes)
        ],
    )
    return b.finish(), pid, stock


def main():
    kind = sys.argv[1] if len(sys.argv) > 1 else 'held'
    places = int(sys.argv[2]) if len(sys.argv) > 2 else 30_000
    routes = int(sys.argv[3]) if len(sys.argv) > 3 else 35_000
    horizon = float(sys.argv[4]) if len(sys.argv) > 4 else 48.0
    began = time.perf_counter()
    made, pid, _ = program(kind, places, routes)
    built = time.perf_counter()
    keys = [Key(f'places.{pid[k]}', ('stock',)) for k in (0, places // 2, places - 1)]
    configuration = Configuration(
        Request(horizon, everything=kind == 'held', keys=() if kind == 'held' else tuple(keys))
    )
    plan = Plan.of(made, configuration)
    planned = time.perf_counter()
    runner = Run(plan)
    record = runner.run()
    ran = time.perf_counter()
    assert record.failure is None, record.failure
    found = read(record, made, keys, [0.0, horizon / 2, horizon])
    done = time.perf_counter()
    ways = {}
    for connected in plan.sets:
        ways.setdefault(connected.way, []).append(len(connected.stores))
    print(f'{kind}: {places} places, {routes} routes, to {horizon:g} h')
    print(
        '  ways (sets, largest set in stores):',
        {way: (len(sizes), max(sizes)) for way, sizes in ways.items()},
    )
    print(
        f'  build {built - began:.2f} s, plan {planned - built:.2f} s, run+record {ran - planned:.2f} s, read {done - ran:.3f} s'
    )
    for way in runner.ways.instances:
        if isinstance(way, Lines):
            empty = sum(way.level_at(store, horizon) <= 0 for store in way.stores)
            print(f'  lines: {len(way.stores)} stores, {way.version.sum()} line starts, {empty} stores at zero')
        elif isinstance(way, Sparse):
            print(f'  sparse: {len(way.stores)} stores, {way.evaluations} evaluations')
    for reading in found:
        print('  ', reading.path, [round(v, 6) for v in reading.values])


if __name__ == '__main__':
    main()
