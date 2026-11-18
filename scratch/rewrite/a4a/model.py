"""The model of the A4a measurements: places with a stock, and routes between two places.

In the new language (the spec's forms; nothing parses this text here):

    Place:
        input out_limit: L/h = 0
        readonly stock: L = 0 in [0 L, 1000000 L]
            outflow.capacity = this.out_limit
        input need: L/h = 0
        input critical: bool = false
        used: L = 0 in [0 L, 1000000 L]
        flow use: this.stock -> this.used
            request = this.need

    Route:
        origin: Place
        destination: Place
        input rate: L/h = 0
        input lot: L = 0
        input ship_at: h = 1
        flow carried: this.origin.stock -> this.destination.stock
            request = this.rate
        ship = event():
            when t >= this.ship_at:
                this.ship.start()
                reset when false
            after 0 h:
                move this.lot from this.origin.stock to this.destination.stock

    places: Place from "places.csv"
    routes: Route from "routes.csv"

`out_limit` is more than the flows out of a place can ask together, in every table that `write`
makes: it never binds. The old language needs it, because flows that take from one stock must share
a limit there. `write` makes the two tables. `build` makes the layout of this file from them (`layout.py`), and
`lines_run` the run on straight lines (`lines.py`). `OLD` is the same model in the language of the
base commit, for the present engine: `old_run` runs it with each row written out (one component).
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

import layout
from lines import Lines


HEAD = '''scenario "A synthetic model"
    summary "A model of a test, with no source."
    horizon {horizon:g} h
    scope "Nothing: the model is synthetic."

'''
RECORD = '\nrecord shape: assumption "A synthetic model, with no source."\n'
OLD = '''Place:  @shape
    "A place."
    var stock: L = 10 L in 0 L to 1000000 L size 1000 L  @shape
    input need: L/h = 0 L/h in 0 L/h to 1000000 L/h  @shape
    input critical: bool = false  @shape
    input out_limit: L/h = 1 L/h in 0 L/h to 1000000 L/h  @shape
    var used: L = 0 L in 0 L to 1000000 L size 1000 L  @shape
    flow use: stock -> used at need  @shape
    share stock limit out_limit  @shape

Route:  @shape
    "A route."
    let origin: Place
    let destination: Place
    input rate: L/h = 0 L/h in 0 L/h to 1000000 L/h  @shape
    input lot: L = 0 L in 0 L to 1000000 L  @shape
    input ship_at: h = 1 h in 0 h to 100000 h  @shape
    flow carried: origin.stock -> destination.stock at rate  @shape
    event ship once when t >= ship_at:  @shape
        "The route ships its lot."
        move lot from origin.stock to destination.stock

places: Place from "places.csv"
routes: Route from "routes.csv"

output first: L = places.1.stock  @shape
    "Held by the first place of the file"
    level
'''
# The request of the flow of a route, in the old language, for each kind of model of the measurements
# of task 2. `constant` reads nothing that moves. The others read a stock, which moves between moments:
# `linear` asks a share of what the origin holds in an hour, `saturating` slows down as the origin
# runs low, and `target` asks what brings the destination to a goal in a given time (the form of
# the spec: `formula(max(0 L, 15 L - this.water) / (2 h))`).
KINDS = {
    'constant': ('rate', ''),
    'linear': ('pull * origin.stock', '    input pull: fraction/h = 0.02 fraction/h in 0 fraction/h to 10 fraction/h  @shape\n'),
    'saturating': (
        'rate * origin.stock / (origin.stock + half)',
        '    input half: L = 20 L in 1 L to 1000 L  @shape\n',
    ),
    'target': (
        'max(0 L, goal - destination.stock) / lag',
        '    input goal: L = 150 L in 0 L to 1000 L  @shape\n    input lag: h = 20 h in 1 h to 1000 h  @shape\n',
    ),
}


def old_text(kind='constant', horizon=3.0):
    """The old model with the request of the kind."""
    request, inputs = KINDS[kind]
    body = OLD.replace('    flow carried: origin.stock -> destination.stock at rate  @shape\n', f'{inputs}    flow carried: origin.stock -> destination.stock at {request}  @shape\n')
    assert body != OLD or kind == 'constant'
    return HEAD.format(horizon=horizon) + body + RECORD


UNITS = {
    'L': {'kind': 'volume', 'dimensions': {'volume': 1}, 'scale': 1, 'description': 'Litres.'},
    'L/h': {'kind': 'volume_rate', 'dimensions': {'volume': 1, 'time': -1}, 'scale': 1, 'description': 'Litres in an hour.'},
}


def write(folder, places, routes, horizon=3.0, old=True, kind='constant'):
    """Write the two tables, and the old model beside them. `places`: (id, stock, need) for each, or
    (id, stock, need, critical); `routes`: (id, origin id, destination id, rate, lot, ship_at) for each."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    places = [(*row, False)[:4] for row in places]
    asked = {i: need for i, _, need, _ in places}
    for _, a, _, rate, _, _ in routes:
        asked[a] += rate
    with open(folder / 'places.csv', 'w') as handle:
        handle.write('id,stock: L @shape,need: L/h @shape,critical @shape,out_limit: L/h @shape\n')
        handle.writelines(
            f'{i},{stock!r},{need!r},{"true" if critical else "false"},{2 * asked[i] + 1!r}\n'
            for i, stock, need, critical in places
        )
    with open(folder / 'routes.csv', 'w') as handle:
        handle.write('id,origin,destination,rate: L/h @shape,lot: L @shape,ship_at: h @shape\n')
        handle.writelines(
            f'{i},places.{a},places.{b},{rate!r},{lot!r},{at!r}\n' for i, a, b, rate, lot, at in routes
        )
    if old:
        (folder / 'model.scn').write_text(old_text(kind, horizon))
        (folder / 'units.json').write_text(json.dumps(UNITS))
    return folder


def synthetic(places, routes, seed=0, moves=True, need_share=0.5, drain=1.0, rings=True):
    """A random network of `places` places and `routes` routes, as the rows of the two tables. Each
    route joins two different places. About half of the places use what they hold. A move ships a
    small lot at 1 h, before any place can be empty: no stock empties before 2 h. Without `rings`,
    each route goes from a place to a later place of the list, so no stocks feed one another in a
    ring."""
    rng = np.random.default_rng(seed)
    stock = np.round(rng.uniform(20.0, 200.0, places), 3)
    origin = rng.integers(0, places, routes)
    destination = (origin + rng.integers(1, places, routes)) % places
    if not rings:
        origin, destination = np.minimum(origin, destination), np.maximum(origin, destination)
    rate = np.round(rng.uniform(0.2, 4.0, routes), 3) * drain
    need = np.where(rng.uniform(size=places) < need_share, np.round(rng.uniform(0.5, 6.0, places), 3), 0.0) * drain
    # No place empties before 2 h: what leaves it in 2 h, with its lots, is less than it holds.
    out = np.bincount(origin, weights=rate, minlength=places) + need
    lot = np.round(rng.uniform(0.0, 1.0, routes), 3) if moves else np.zeros(routes)
    lots = np.bincount(origin, weights=lot, minlength=places)
    scale = np.minimum(1.0, 0.9 * stock / np.maximum(2.0 * out + lots, 1e-9))
    rate, need, lot = rate * scale[origin], need * scale, lot * scale[origin]
    width = len(str(places))
    pid = [f'p{k:0{width}d}' for k in range(places)]
    critical = np.random.default_rng(seed + 1000).uniform(size=places) < 0.1
    place_rows = [(pid[k], float(stock[k]), float(need[k]), bool(critical[k])) for k in range(places)]
    route_rows = [
        (f'r{k:0{len(str(routes))}d}', pid[origin[k]], pid[destination[k]], float(rate[k]), float(lot[k]), 1.0)
        for k in range(routes)
    ]
    return place_rows, route_rows


class Built:
    """The layout of the model from its two tables."""

    def __init__(self, folder, canonical=True):
        folder = Path(folder)
        self.places = P = layout.Pool.from_csv('places', folder / 'places.csv', canonical)
        self.routes = R = layout.Pool.from_csv('routes', folder / 'routes.csv', canonical)
        for field in ('stock', 'need', 'out_limit'):
            P.number(field)
        P.flag('critical')
        for field in ('rate', 'lot', 'ship_at'):
            R.number(field)
        R.link('origin', P)
        R.link('destination', P)
        P.cols['used'] = np.zeros(P.n)
        self.stores = stores = layout.Stores()
        stores.add(P, 'stock')
        stores.add(P, 'used')
        self.net = net = layout.Network(stores)
        origin = stores.place(P, 'stock', R.links['origin'][1])
        destination = stores.place(P, 'stock', R.links['destination'][1])
        self.carried = net.add('carried', R, origin, destination)
        self.use = net.add('use', P, stores.place(P, 'stock', np.arange(P.n)), stores.place(P, 'used', np.arange(P.n)))
        net.finish()
        self.origin, self.destination = origin, destination
        # The limit of the outflow of a place never binds in these tables: the run does not read it.
        asked = np.bincount(R.links['origin'][1], weights=R.cols['rate'], minlength=P.n) + P.cols['need']
        if np.any(asked > P.cols['out_limit']):
            raise layout.LayoutError('places: a limit of an outflow binds, and this prototype has no such limit')

    def want(self):
        return np.concatenate([self.routes.cols['rate'], self.places.cols['need']])

    def lines_run(self, horizon, recorder=None, moves=True):
        run = Lines(self.net, self.stores.start(), 0.0, self.want(), horizon, recorder)
        R = self.routes
        if moves:
            lot, at = R.cols['lot'], R.cols['ship_at']
            # The order of the moves of one time is the order of the ids of the routes.
            for k in np.flatnonzero(lot > 0).tolist():
                run.schedule_move(at[k], f'routes.{R.ids[k]}.ship', self.origin[k], self.destination[k], lot[k])
        return run.start()

    def stock_of(self, values, field='stock'):
        """{`places.id`: the stock} from the vector of the stores."""
        at = self.stores.offset['places', field]
        return {f'places.{key}': float(values[at + k]) for k, key in enumerate(self.places.ids)}


def old_run(folder, times):
    """The present engine on the old model of a folder, each row written out: the stock of each place
    by its id at each time, and the trajectory."""
    import csv

    from napkin.engine.runtime import simulate
    from napkin.model.ir import thaw
    from napkin.model.model import build_model

    folder = Path(folder)
    model = build_model(folder / 'model.scn')
    resolved = model.resolve(next(iter(model.runs)))
    trajectory = simulate(resolved, thaw(model.library))
    with open(folder / 'places.csv', newline='') as handle:
        ids = [row[0] for row in csv.reader(handle)][1:]
    found = {}
    for t in times:
        env = trajectory.env_at(t)
        found[t] = {f'places.{key}': env[f'places_{k}.stock'] for k, key in enumerate(ids, 1)}
        found[t].update({f'places.{key}.used': env[f'places_{k}.used'] for k, key in enumerate(ids, 1)})
    return found, trajectory
