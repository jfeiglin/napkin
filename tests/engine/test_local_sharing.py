"""Local sharing on small random networks, against the oracle (`tests/reference/`).

Each case is a network of a few stores (stocked, empty, full, and `[0, 0]` junctions) and a few
directed flows between them and the outside, with random requests and capacities, and endpoints with
capacities, requests and `priority(...)` or `proportional()` allocations. The networks of the second
kind also have reversible routes between two stores, with a signed request, and flows with two legs
served at one fraction; a priority names the legs of a route and the legs of a flow with legs at their
endpoints. The oracle runs the same program in exact fractions by the selection order, so it is an
independent second reading of the rules. The rates, the fractions and the levels must agree at the
start and at moments after it; where the oracle has no answer (`NotCovered`: a ring of empty stores
or of full stores, a request at an endpoint that a route meets, a store that no rates hold just after
a moment, which its sharing moves off its bound when held and back past it when free), the engine
stops with a failure that names the stores or the endpoint. Room passed through two full stores in
series is no longer such a case: both answer it (`tests/engine/test_full_stores.py`).
"""

from __future__ import annotations

import random

import pytest

from napkin.engine import read, run
from napkin.program.build import (
    SINK,
    SOURCE,
    Builder,
    endpoint,
    flow,
    legs,
    named,
    priority,
    proportional,
    q,
    route,
    value,
)
from napkin.program.config import Configuration, Request
from napkin.program.record import Key
from tests.reference.errors import NotCovered
from tests.reference.from_program import run_of, value_at, values_at

UNITS = {'h': {'time': 1}, 'L': {'volume': 1}}
TIMES = (0, 0.5, 1, 2, 3)
STORES = {  # start, lower, upper
    'stocked': (10, 0, 100),
    'empty': (0, 0, 100),
    'full': (10, 0, 10),
    'junction': (0, 0, 0),
}


def network(seed, routes=False):
    """A random program: its stores, its flows (each owned by an entity: `f<k>` as `pipe`, and with
    `routes` also `r<k>` as the route `link` and `g<k>` as `restore` with the legs `a` and `b`), and
    the paths to read."""
    rng = random.Random(seed)
    count = rng.randint(2, 4)
    kinds = [rng.choice(list(STORES)) for _ in range(count)]
    ends = list(range(count))

    def directed():
        source = rng.choice([None, *ends])
        sink = rng.choice([s for s in [None, *ends] if s != source or s is None])
        if source is None and sink is None:
            sink = rng.choice(ends)
        request = rng.choice([0, 0.5, 1, 2, 3])
        capacity = rng.choice([None, None, 1, 2, 4, 'request'])
        return source, sink, request, request if capacity == 'request' else capacity

    flows = [directed() for _ in range(rng.randint(2, 6))]
    links, restores = [], []
    if routes:
        for _ in range(rng.randint(1, 2)):
            first, second = rng.sample(ends, 2)
            links.append((first, second, rng.choice([-3, -1, 0, 0.5, 2]), rng.choice([None, 1, 2.5])))
        for _ in range(rng.randint(0, 2)):
            restores.append([directed() for _ in range(2)])
    # The connections at each endpoint, as the paths that name them.
    incident = {(s, side): [] for s in ends for side in ('outflow', 'inflow')}

    def meets(source, sink, path):
        if source is not None:
            incident[(source, 'outflow')].append(path)
        if sink is not None:
            incident[(sink, 'inflow')].append(path)

    for k, (source, sink, _, _) in enumerate(flows):
        meets(source, sink, named(f'f{k}').pipe)
    for k, (first, second, _, _) in enumerate(links):
        meets(first, second, named(f'r{k}').link.forward)
        meets(second, first, named(f'r{k}').link.backward)
    for k, pair in enumerate(restores):
        for name, (source, sink, _, _) in zip('ab', pair):
            meets(source, sink, getattr(named(f'g{k}').restore, name))
    b = Builder(UNITS)
    for s, kind in enumerate(kinds):
        start, lower, upper = STORES[kind]
        settings = {}
        for side in ('outflow', 'inflow'):
            if rng.random() < 0.4:
                mine = incident[(s, side)]
                allocation = proportional()
                if len(mine) >= 2 and rng.random() < 0.6:
                    allocation = priority(*rng.sample(mine, rng.randint(1, len(mine))))
                settings[side] = endpoint(
                    capacity=rng.choice([None, q(1.5, 'L/h'), q(3, 'L/h')]),
                    request=rng.choice([None, None, q(2, 'L/h'), q(5, 'L/h')]),
                    allocation=allocation,
                )
        b.entity(f's{s}', value('water', 'L', start, lower=lower, upper=upper, **settings))

    def end(s, outside):
        return outside if s is None else named(f's{s}').water

    def rate(number):
        return None if number is None else q(number, 'L/h')

    for k, (source, sink, request, capacity) in enumerate(flows):
        made = flow(
            'pipe', end(source, SOURCE), end(sink, SINK), request=rate(request), capacity=rate(capacity)
        )
        b.entity(f'f{k}', made)
    for k, (first, second, request, capacity) in enumerate(links):
        b.entity(
            f'r{k}',
            route(
                'link', end(first, None), end(second, None), request=rate(request), capacity=rate(capacity)
            ),
        )
    for k, pair in enumerate(restores):
        parts = [
            flow(name, end(source, SOURCE), end(sink, SINK), request=rate(request), capacity=rate(capacity))
            for name, (source, sink, request, capacity) in zip('ab', pair)
        ]
        b.entity(f'g{k}', legs('restore', *parts))
    keys = [Key(f'f{k}', ('pipe', 'actual_rate')) for k in range(len(flows))]
    for k in range(len(links)):
        keys += [Key(f'r{k}', ('link', *steps, 'actual_rate')) for steps in ((), ('forward',), ('backward',))]
    for k in range(len(restores)):
        keys += [Key(f'g{k}', ('restore', 'served_fraction'))]
        keys += [Key(f'g{k}', ('restore', name, 'actual_rate')) for name in 'ab']
    keys += [Key(f's{s}', ('water',)) for s in ends]
    return b.finish(), keys


# What a failure of the engine says where the oracle has no answer of local sharing.
NO_ANSWER = (
    'ring of stores',
    'a request at an endpoint that the route',
    'switch back and forth at its bound',
)


def compare(seed, routes=False):
    program, keys = network(seed, routes)
    configuration = Configuration(Request(TIMES[-1]))
    try:
        oracle, failed = run_of(program, configuration)
    except NotCovered:
        record = run(program, configuration)
        assert record.failure is not None
        message = record.failure.detail('message')
        assert any(reason in message for reason in NO_ANSWER), message
        return
    record = run(program, configuration)
    if failed is not None:
        assert record.failure is not None, failed
        return
    assert record.failure is None, record.failure.detail('message')
    exact = values_at(oracle, program, keys, TIMES)
    rows = read(record, program, keys, list(map(float, TIMES)))
    for key, row in zip(keys, rows, strict=True):
        for t, number, expected in zip(TIMES, row.values, exact[key], strict=True):
            assert number == pytest.approx(float(expected), rel=1e-7, abs=1e-7), (seed, str(key), t)


@pytest.mark.parametrize('seed', range(300))
def test_a_small_random_network_shares_as_the_oracle_does(seed):
    compare(seed)


@pytest.mark.deep
@pytest.mark.parametrize('seed', range(300, 2300))
def test_more_random_networks_share_as_the_oracle_does(seed):
    compare(seed)


@pytest.mark.parametrize('seed', range(300))
def test_a_random_network_with_routes_and_legs_shares_as_the_oracle_does(seed):
    compare(seed, routes=True)


@pytest.mark.deep
@pytest.mark.parametrize('seed', range(300, 2300))
def test_more_random_networks_with_routes_and_legs_share_as_the_oracle_does(seed):
    compare(seed, routes=True)


def chain():
    """A drains through two rigid pipes, 2 L/h to B and 1 L/h out; B, which holds 1 L, drains at
    3 L/h. No endpoint has a setting, so each moment of the lines solves the groups downstream of the
    store that met its bound only (`Lines._downstream`)."""

    def pipe(name, source, sink, number):
        return flow(name, source, sink, request=q(number, 'L/h'), capacity=q(number, 'L/h'))

    b = Builder(UNITS)
    a = b.entity('a', value('water', 'L', 6, lower=0, upper=100))
    s = b.entity('b', value('water', 'L', 1, lower=0, upper=100))
    b.entity(
        'p', pipe('one', a.water, s.water, 2), pipe('two', a.water, SINK, 1), pipe('three', s.water, SINK, 3)
    )
    return b.finish()


@pytest.mark.parametrize('downstream', [True, False])
def test_the_moments_of_lines_solve_downstream_only_and_give_what_whole_parts_give(downstream, monkeypatch):
    """B falls at 1 L/h and is empty at 1 h; it then passes on the 2 L/h that A gives it. A falls at
    3 L/h and is empty at 2 h, when every pipe stops. The same, whether a moment solves the groups
    downstream of the store that met its bound, or the whole coupled part."""
    from napkin.engine.timeline import lines

    if not downstream:
        original = lines.Lines.__init__

        def whole(self, *args, **kwargs):
            original(self, *args, **kwargs)
            self.closed = False

        monkeypatch.setattr(lines.Lines, '__init__', whole)
    program = chain()
    times = [0, 0.5, 1, 1.5, 2, 3]
    keys = [Key('a', ('water',)), Key('b', ('water',)), Key('p', ('three', 'actual_rate'))]
    record = run(program, Configuration(Request(3)))
    assert record.failure is None
    a, s, three = (reading.values for reading in read(record, program, keys, times))
    assert list(a) == pytest.approx([6, 4.5, 3, 1.5, 0, 0])
    assert list(s) == pytest.approx([1, 0.5, 0, 0, 0, 0])
    assert list(three) == pytest.approx([3, 3, 2, 2, 0, 0])
    oracle, _ = run_of(program, Configuration(Request(3)))
    for key, found in zip(keys, (a, s, three)):
        assert list(found) == pytest.approx([float(value_at(oracle, program, key, t)) for t in times])
