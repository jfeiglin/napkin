"""The structure of sharing is that of the connections that can carry flow at the instant
(`network.carrying`; re-audit row 05): a pipe whose capacity is zero passes neither supply nor room,
is no member of a priority class (spec: `priority(a, b)` "gives `a` first access when both are
eligible"), closes no ring and links no claims, and the structure is found again when a capacity
changes.

The rule, on the small random networks of `test_claim_order` (with priorities, routes and legs), by
local sharing alone and with a solver that names a random subset of the flows: a closed pipe added
between two random ends, with a random request, changes no value of the run and how it ends, and it
carries nothing. Then the audit's case and its variants, worked by hand.
"""

from __future__ import annotations

import random
from dataclasses import replace

import pytest

from napkin.engine import read, run
from napkin.program.build import (
    SINK,
    SOURCE,
    Builder,
    after,
    assign,
    event,
    flow,
    given,
    local,
    q,
    solve_for,
    solver,
    start,
    this,
    value,
)
from napkin.program.config import Configuration, Request
from napkin.program.record import Key
from tests.engine.test_claim_order import TIMES, chosen, drawn, network

UNITS = {'h': {'time': 1}, 'L': {'volume': 1}}


def values(program, keys, configuration):
    """The values of `keys` at TIMES, or the failure that ended the run."""
    record = run(program, configuration)
    if record.failure is not None:
        return None, record.failure
    return {name: read(record, program, [key], list(TIMES))[0].values for name, key in keys.items()}, None


def closed_pipe_changes_nothing(seed, routes, solved):
    _, keys, _, names = network(seed, routes, solved=solved)
    rng = random.Random(20_000 + seed)
    _, kinds, pipes, _, _ = drawn(seed, routes)
    between = [(sink, source) for source, sink, _, _ in pipes if source is not None and sink is not None]
    if between and rng.random() < 0.8:
        source, sink = rng.choice(between)  # back along a pipe between two stores: a ring if it carried
    else:
        source = rng.choice([None, *range(len(kinds))])
        sink = rng.choice([s for s in [None, *range(len(kinds))] if s is None or s != source])
    extra = (source, sink if source is not None or sink is not None else 0, rng.choice([0, 1, 3]))
    mine = chosen(seed, [*names, 'x']) if solved else set()
    configuration = Configuration(Request(TIMES[-1]))
    before, failed = values(network(seed, routes, mine - {'x'}, solved=solved)[0], keys, configuration)
    keys = {**keys, 'x': Key('x', ('pipe', 'actual_rate'))}
    found, failed_now = values(
        network(seed, routes, mine, extra=extra, solved=solved)[0], keys, configuration
    )
    if failed is not None:
        assert failed_now is not None, (seed, extra, failed)
        assert failed_now.t == pytest.approx(failed.t, rel=0, abs=configuration.numerics.crossing)
        assert replace(failed_now, t=failed.t) == failed, (seed, extra)
        return
    assert failed_now is None, (seed, extra, failed_now)
    assert found['x'] == (0,) * len(TIMES), (seed, extra)
    for name, expected in before.items():
        assert found[name] == pytest.approx(expected, rel=1e-9, abs=1e-9), (seed, extra, name)


@pytest.mark.parametrize('seed', range(40))
@pytest.mark.parametrize('routes', [False, True], ids=['pipes', 'routes'])
@pytest.mark.parametrize('solved', [False, True], ids=['local', 'solver'])
def test_a_closed_pipe_changes_nothing(seed, routes, solved):
    closed_pipe_changes_nothing(seed, routes, solved)


@pytest.mark.deep
@pytest.mark.parametrize('seed', range(40, 640))
@pytest.mark.parametrize('routes', [False, True], ids=['pipes', 'routes'])
@pytest.mark.parametrize('solved', [False, True], ids=['local', 'solver'])
def test_more_closed_pipes_change_nothing(seed, routes, solved):
    closed_pipe_changes_nothing(seed, routes, solved)


# ---- the audit's case and its variants, worked by hand ----------------------------------------------


def chain(back=0, opens=None, solved=False):
    """Two full tanks in series (`test_full_stores`): 1 L/h fills the upper one, which passes 1 L/h to
    the lower one, which drains 1 L/h; and a return pipe from the lower to the upper tank, which asks
    nothing, of capacity `back` L/h, set to 1 L/h at `opens` (hours), and a solver of every flow
    with `solved`. Its record."""
    b = Builder(UNITS)
    down = b.entity(
        'down',
        value('water', 'L', 10, lower=0, upper=10),
        flow('drain', this.water, SINK, request=q(1, 'L/h')),
    )
    up = b.entity(
        'up',
        value('water', 'L', 10, lower=0, upper=10),
        flow('fill', SOURCE, this.water, request=q(1, 'L/h')),
        flow('pass_on', this.water, down.water, request=q(1, 'L/h')),
    )
    parts = [flow('pipe', down.water, up.water, capacity=q(back, 'L/h'))]
    if opens is not None:
        parts.append(event('open', after(q(opens, 'h'), assign(this.pipe.capacity, q(1, 'L/h')))))
    back_pipe = b.entity('back', *parts)
    if opens is not None:
        b.setup(start(back_pipe.open))
    if solved:
        paths = {'drain': down.drain, 'fill': up.fill, 'pass_on': up.pass_on, 'pipe': back_pipe.pipe}
        made = [given(name, path) for name, path in paths.items()]
        made += [solve_for(getattr(local, name).actual_rate) for name in paths]
        b.entity('provider', solver('plan', *made))
    program = b.finish()
    return program, run(program, Configuration(Request(2)))


def rate(program, record, owner, name, t):
    return read(record, program, [Key(owner, (name, 'actual_rate'))], [t])[0].values[0]


@pytest.mark.parametrize('solved', [False, True], ids=['local', 'solver'])
def test_a_closed_return_pipe_closes_no_ring_of_full_tanks(solved):
    """Re-audit row 05: the return pipe cannot carry flow, so the two full tanks are a chain and no
    ring: each request is served, 1 L/h, and the pipe carries nothing (the run once stopped at setup
    with "a ring of stores at their upper bound")."""
    program, record = chain(solved=solved)
    assert record.failure is None, record.failure
    for owner, name in (('up', 'fill'), ('up', 'pass_on'), ('down', 'drain')):
        assert rate(program, record, owner, name, 1.5) == pytest.approx(1, abs=1e-9)
    assert rate(program, record, 'back', 'pipe', 1.5) == 0


def test_a_return_pipe_that_opens_makes_the_ring_when_it_opens():
    """The structure is found again when a capacity changes: once the return pipe opens at 1 h, the
    two full tanks pass room around a ring, which local sharing has no answer for; the run stops then,
    by name, and serves each request until then."""
    program, record = chain(opens=1)
    assert record.failure is not None and record.failure.t == 1
    assert 'a ring of stores at their upper bound passes room around' in record.failure.detail('message')
    assert rate(program, record, 'up', 'pass_on', 0.5) == pytest.approx(1, abs=1e-9)


def test_a_solver_of_the_ring_decides_it_when_the_pipe_opens():
    """With every flow of the ring named, the solver decides what passes around it, and with no
    request on the return pipe, its nearest rates send nothing back: the run goes on past 1 h with
    each request served (spec: "A preference alone creates no circulation")."""
    program, record = chain(opens=1, solved=True)
    assert record.failure is None, record.failure
    assert rate(program, record, 'up', 'pass_on', 1.5) == pytest.approx(1, abs=1e-6)
    assert rate(program, record, 'back', 'pipe', 1.5) == pytest.approx(0, abs=1e-6)


def test_a_closed_pipe_closes_no_ring_of_empty_tanks():
    """Two empty tanks, the first filled 2 L/h, which passes 1 L/h on to the second, which drains it;
    a closed pipe back from the second to the first would make a ring of stores at their lower
    bound, which it cannot: the first tank rises at 1 L/h, and each request is served."""
    b = Builder(UNITS)
    second = b.entity(
        'second',
        value('water', 'L', 0, lower=0, upper=10),
        flow('drain', this.water, SINK, request=q(1, 'L/h')),
    )
    first = b.entity(
        'first',
        value('water', 'L', 0, lower=0, upper=10),
        flow('fill', SOURCE, this.water, request=q(2, 'L/h'), capacity=q(2, 'L/h')),
        flow('there', this.water, second.water, request=q(1, 'L/h')),
    )
    b.entity('back', flow('pipe', second.water, first.water, request=q(1, 'L/h'), capacity=q(0, 'L/h')))
    program = b.finish()
    record = run(program, Configuration(Request(2)))
    assert record.failure is None, record.failure
    assert rate(program, record, 'second', 'drain', 0.5) == pytest.approx(1, abs=1e-9)
    assert read(record, program, [Key('first', ('water',))], [1])[0].values == pytest.approx((1,), abs=1e-9)
