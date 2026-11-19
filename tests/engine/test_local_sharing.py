"""Local sharing on small random networks, against the oracle (`tests/reference/`).

Each case is a network of a few stores (stocked, empty, full, and `[0, 0]` junctions) and a few
directed flows between them and the outside, with random requests and capacities, and endpoints with
capacities, requests and `priority(...)` or `proportional()` allocations. The oracle runs the same
program in exact fractions by the selection order, so it is an independent second reading of the
rules. The rates and the levels must agree at the start and at moments after it; where the oracle
has no answer (`NotCovered`: a ring of empty stores, room passed upstream through two full stores),
the engine stops with a failure that names the stores.
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
    named,
    priority,
    proportional,
    q,
    value,
)
from napkin.program.config import Configuration, Request
from napkin.program.record import Key
from tests.reference.errors import NotCovered
from tests.reference.from_program import run_of, value_at

UNITS = {'h': {'time': 1}, 'L': {'volume': 1}}
TIMES = (0, 0.5, 1, 2, 3)
STORES = {  # start, lower, upper
    'stocked': (10, 0, 100),
    'empty': (0, 0, 100),
    'full': (10, 0, 10),
    'junction': (0, 0, 0),
}


def network(seed):
    """A random program: its stores, its flows (each owned by an entity `f<k>` as `pipe`), and the
    paths to read."""
    rng = random.Random(seed)
    count = rng.randint(2, 4)
    kinds = [rng.choice(list(STORES)) for _ in range(count)]
    ends = list(range(count))
    flows = []
    for _ in range(rng.randint(2, 6)):
        source = rng.choice([None, *ends])
        sink = rng.choice([s for s in [None, *ends] if s != source or s is None])
        if source is None and sink is None:
            sink = rng.choice(ends)
        request = rng.choice([0, 0.5, 1, 2, 3])
        capacity = rng.choice([None, None, 1, 2, 4, 'request'])
        flows.append((source, sink, request, request if capacity == 'request' else capacity))
    b = Builder(UNITS)
    incident = {(s, side): [] for s in ends for side in ('outflow', 'inflow')}
    for k, (source, sink, _, _) in enumerate(flows):
        if source is not None:
            incident[(source, 'outflow')].append(k)
        if sink is not None:
            incident[(sink, 'inflow')].append(k)
    for s, kind in enumerate(kinds):
        start, lower, upper = STORES[kind]
        settings = {}
        for side in ('outflow', 'inflow'):
            if rng.random() < 0.4:
                mine = incident[(s, side)]
                allocation = proportional()
                if len(mine) >= 2 and rng.random() < 0.6:
                    ranked = rng.sample(mine, rng.randint(1, len(mine)))
                    allocation = priority(*(named(f'f{k}').pipe for k in ranked))
                settings[side] = endpoint(
                    capacity=rng.choice([None, q(1.5, 'L/h'), q(3, 'L/h')]),
                    request=rng.choice([None, None, q(2, 'L/h'), q(5, 'L/h')]),
                    allocation=allocation,
                )
        b.entity(f's{s}', value('water', 'L', start, lower=lower, upper=upper, **settings))
    for k, (source, sink, request, capacity) in enumerate(flows):
        source_path = SOURCE if source is None else named(f's{source}').water
        sink_path = SINK if sink is None else named(f's{sink}').water
        b.entity(
            f'f{k}',
            flow(
                'pipe',
                source_path,
                sink_path,
                request=q(request, 'L/h'),
                capacity=None if capacity is None else q(capacity, 'L/h'),
                unit='L/h',
            ),
        )
    keys = [Key(f'f{k}', ('pipe', 'actual_rate')) for k in range(len(flows))]
    keys += [Key(f's{s}', ('water',)) for s in ends]
    return b.finish(), keys


def compare(seed):
    program, keys = network(seed)
    configuration = Configuration(Request(TIMES[-1]))
    try:
        oracle, failed = run_of(program, configuration)
    except NotCovered:
        record = run(program, configuration)
        assert record.failure is not None
        message = record.failure.detail('message')
        assert 'ring of stores' in message or 'two full stores' in message, message
        return
    record = run(program, configuration)
    if failed is not None:
        assert record.failure is not None, failed
        return
    assert record.failure is None, record.failure.detail('message')
    for key in keys:
        found = read(record, program, [key], list(TIMES))[0].values
        for t, number in zip(TIMES, found):
            expected = float(value_at(oracle, program, key, t))
            assert number == pytest.approx(expected, rel=1e-7, abs=1e-7), (seed, str(key), t)


@pytest.mark.parametrize('seed', range(300))
def test_a_small_random_network_shares_as_the_oracle_does(seed):
    compare(seed)


@pytest.mark.deep
@pytest.mark.parametrize('seed', range(300, 2300))
def test_more_random_networks_share_as_the_oracle_does(seed):
    compare(seed)
