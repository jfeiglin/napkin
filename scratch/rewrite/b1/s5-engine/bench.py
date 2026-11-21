"""A3's network as a program with one declared solver, run on the engine. Not a test.

Run from /home/user/napkin:

    NAPKIN_STORE=off OPENBLAS_NUM_THREADS=1 .venv/bin/python scratch/rewrite/b1/s5-engine/bench.py [PLACES ROUTES SOURCES]

The defaults are A3's 30,000 places, 35,000 routes and 15,000 sources (`scratch/rewrite/a3/network.py`):
each place has a level in [-30, 30], a store held at 0 Wh, a supply of the sum of the capacities of
its sources (times the provider's factor), and a use whose request is its need; each route has its
strength and its capacity, and the law `carried == pull * (origin.level - destination.level)`. The
provider's solver minimizes the total unmet need. At 24 h a stage sets the factor to 0.8, which makes
a second solve. The run goes to 48 h. Prints the time of each part.
"""

import resource
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'a3'))
from network import network  # A3's synthetic network

from napkin.engine import read
from napkin.engine.timeline import Plan
from napkin.engine.timeline.run import Run
from napkin.program.build import (
    BOOL,
    SINK,
    SOURCE,
    Builder,
    after,
    assign,
    constraint,
    event,
    fall,
    flow,
    fmax,
    formula,
    fsum,
    given,
    input_,
    link,
    local,
    minimize,
    named,
    q,
    route,
    solve_for,
    solver,
    start,
    this,
    value,
)
from napkin.program.config import Configuration, Request

UNITS = {'h': {'time': 1}, 'Wh': {'energy': 1}, 'W': {'energy': 1, 'time': -1}}


def program(places, routes, sources):
    net = network(places, routes, sources)
    supply = np.zeros(net['places'])
    np.add.at(supply, net['at'], net['pmax'])
    b = Builder(UNITS)
    b.entity('provider', value('factor', '', 1), event('cut', after(q(24, 'h'), assign(this.factor, 0.8))))
    place = b.template(
        'Place',
        input_('base_need', 'W', 0),
        input_('supply_limit', 'W', 0),
        value('level', '', 0, lower=-30, upper=30),
        value('power', 'Wh', 0, lower=0, upper=0),
        flow(
            'supply',
            SOURCE,
            this.power,
            capacity=formula(this.supply_limit * named('provider').factor),
            unit='W',
        ),
        flow('use', this.power, SINK, request=formula(this.base_need), unit='W'),
        value('unmet', 'W', formula(fmax(q(0, 'W'), this.use.request - this.use.actual_rate))),
    )
    link_template = b.template(
        'Route',
        link('origin', 'Place'),
        link('destination', 'Place'),
        input_('strength', 'W', 1),
        input_('limit', 'W', 1),
        route('carried', this.origin.power, this.destination.power, capacity=this.limit, unit='W'),
        value(
            'rate_follows_levels',
            BOOL,
            formula(this.carried.actual_rate == this.strength * (this.origin.level - this.destination.level)),
        ),
    )
    b.table(
        'sites',
        place,
        [
            {'id': f'p{i}', 'base_need': float(net['need'][i]), 'supply_limit': float(supply[i])}
            for i in range(net['places'])
        ],
    )
    b.table(
        'links',
        link_template,
        [
            {
                'id': f'r{j}',
                'origin': f'sites.p{int(net["frm"][j])}',
                'destination': f'sites.p{int(net["to"][j])}',
                'strength': float(net['b'][j]),
                'limit': float(net['cap'][j]),
            }
            for j in range(net['routes'])
        ],
    )
    b.entity(
        'operator',
        solver(
            'dispatch',
            given('places', place.instances),
            given('routes', link_template.instances),
            solve_for(local.places.level),
            solve_for(local.places.supply.actual_rate),
            solve_for(local.places.use.actual_rate),
            solve_for(local.routes.carried.actual_rate),
            constraint(fall(local.routes.rate_follows_levels)),
            minimize(fsum(local.places.unmet)),
        ),
    )
    b.setup(start(named('provider').cut))
    return b.finish(), net


SPENT = {}


def timed(owner, name, label):
    """Count the time of a method of the engine, for the print."""
    method = getattr(owner, name)

    def wrapper(*args, **kwargs):
        start = time.perf_counter()
        try:
            return method(*args, **kwargs)
        finally:
            seconds, calls = SPENT.get(label, (0.0, 0))
            SPENT[label] = (seconds + time.perf_counter() - start, calls + 1)

    setattr(owner, name, wrapper)


def main():
    from napkin.engine.solve import Solver
    from napkin.engine.timeline import declared

    phase_times = '--no-phase-times' not in sys.argv
    if phase_times:
        timed(Solver, 'solve', 'solve library')
        timed(declared.Former, 'problem', 'forming')
        timed(declared, 'polished', 'polish')
    sizes = [int(arg) for arg in sys.argv[1:] if arg != '--no-phase-times'] or [30000, 35000, 15000]
    clock = time.perf_counter()
    source, net = program(*sizes)
    built = time.perf_counter()
    configuration = Configuration(Request(48))
    plan = Plan.of(source, configuration)
    planned = time.perf_counter()
    engine = Run(plan)
    record = engine.run()
    ran = time.perf_counter()
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * (1 if sys.platform == 'darwin' else 1024)
    print(f'places {sizes[0]}, routes {net["routes"]}, sources {sizes[2]}')
    print(f'build {built - clock:.9f} s, plan {planned - built:.9f} s, run and record {ran - planned:.9f} s')
    if phase_times:
        print(', '.join(f'{name} {seconds:.9f} s ({calls})' for name, (seconds, calls) in SPENT.items()))
    print(f'peak resident memory {peak / 1e9:.2f} GB; failure: {record.failure}')
    solves = [(entry.t, entry.round) for entry in record.entries('solve', 'operator.dispatch')]
    print(f'solves (t, round): {solves}')
    work = engine.ways.kept['operator.dispatch']
    print(f'kept HiGHS instance: {len(work._columns)} columns, {len(work._rows)} rows')
    if record.failure is not None and record.failure.t == 0:
        return
    paths = [f'sites.p{i}.use.actual_rate' for i in range(3)] + ['sites.p0.level']
    found = read(record, source, paths, [0, 24, 48])
    print(
        'first places, use at 0, 24, 48 h:', [tuple(round(v, 6) for v in reading.values) for reading in found]
    )
    total = read(record, source, [f'sites.p{i}.use.actual_rate' for i in range(sizes[0])], [0, 48])
    served = [sum(reading.values[k] for reading in total) for k in range(2)]
    print(f'total served at 0 h {served[0]:.4f} W, at 48 h {served[1]:.4f} W; need {net["need"].sum():.4f} W')


if __name__ == '__main__':
    main()
