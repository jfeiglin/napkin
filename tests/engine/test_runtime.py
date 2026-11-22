"""The closed-form runs of the old runtime that are no events (its event cases are in
`test_runtime_events.py`): decay that conserves what it moves, local sharing under endpoint limits
and orders, flows with legs that a short leg holds back, running totals of a drain, and linear
systems with straight lines beside them.

Each expected value is worked by hand: lines and exponentials, and the shares of the spec's local
allocation ("Local allocation": a store at its lower bound shares what flows in by its endpoint's
rule; `priority(a, b)` serves `a` first, and `proportional()` equal fractions of each claim). The
old models' rates were hard; a request is soft (D15), so a supply that must not carry more than it
asks for has its capacity at its request.
"""

from __future__ import annotations

import math

import pytest

from napkin.engine import read, run
from napkin.program.build import (
    SINK,
    SOURCE,
    Builder,
    endpoint,
    flow,
    formula,
    input_,
    legs,
    priority,
    q,
    this,
    value,
)
from napkin.program.config import Configuration, InputValue, Quantity, Request

UNITS = {'h': {'time': 1}, 'L': {'volume': 1}}


def rate(number):
    return q(number, 'L/h')


def run_for(program, horizon):
    record = run(program, Configuration(Request(horizon)))
    assert record.failure is None, record.failure.detail('message')
    return record


def at(record, program, path, *times):
    (reading,) = read(record, program, [path], [float(time) for time in times])
    return list(reading.values)


@pytest.mark.parametrize('hazard', [0, 1e-14, 1e-9, 0.1, 2, 1000])
def test_a_hazard_conserves_what_it_moves_and_matches_expm1(hazard):
    """alive' = -hazard alive: dead holds 1e6 (1 - e^(-10 hazard)) at 10 h, and the two hold 1e6."""
    b = Builder(UNITS)
    b.entity(
        'cohort',
        input_('hazard', '1/h', hazard),
        value('alive', 'L', 1_000_000, lower=0, scale=q(1_000_000, 'L')),
        value('dead', 'L', 0, lower=0, scale=q(1_000_000, 'L')),
        flow('death', this.alive, this.dead, request=formula(this.hazard * this.alive)),
    )
    program = b.finish()
    record = run_for(program, 10)
    expected = 1_000_000 * -math.expm1(-hazard * 10)
    assert at(record, program, 'cohort.dead', 10) == pytest.approx([expected], rel=1e-8, abs=1e-6)
    times = [0, 0.1, 1, 3.25, 10]
    alive, dead = at(record, program, 'cohort.alive', *times), at(record, program, 'cohort.dead', *times)
    for a, d in zip(alive, dead):
        assert a >= 0 and d >= 0
        assert a + d == pytest.approx(1_000_000, abs=1e-6)


def scarce(*order):
    """A store at 0 L that gets 6 L/h, and flows out of it that ask 8 and 4 L/h, under an outflow
    capacity of 12 L/h with the order given (proportional with none)."""
    b = Builder(UNITS)
    allocation = {'allocation': priority(*(getattr(this, name) for name in order))} if order else {}
    b.entity(
        'site',
        value('stock', 'L', 0, lower=0, outflow=endpoint(capacity=rate(12), **allocation)),
        value('a', 'L', 0),
        value('b', 'L', 0),
        flow('supply', SOURCE, this.stock, request=rate(6), capacity=rate(6)),
        flow('to_a', this.stock, this.a, request=rate(8)),
        flow('to_b', this.stock, this.b, request=rate(4)),
    )
    return b.finish()


@pytest.mark.parametrize(
    'order, shares', [((), (4, 2)), (('to_a', 'to_b'), (6, 0)), (('to_b', 'to_a'), (2, 4))]
)
def test_proportional_and_priority_share_what_reaches_an_empty_store(order, shares):
    """The empty store passes on its 6 L/h: in proportion to the requests, 4 and 2 L/h; by priority,
    the first its request up to 6 L/h and the other the rest."""
    program = scarce(*order)
    record = run_for(program, 1)
    assert [at(record, program, f'site.{name}', 1)[0] for name in ('a', 'b')] == pytest.approx(list(shares))


def test_a_priority_keeps_every_other_flow_at_its_most():
    """1 + 1 L/h reach mid under the source's limit of 2 L/h; mid's drain asks 3 L/h and passes on
    the 2 L/h, and end passes on its 1 L/h burn: at 4 h the source holds 92 L, mid 0, end 4 L and
    out 4 L."""
    b = Builder(UNITS)
    b.entity(
        'line',
        value(
            'source',
            'L',
            100,
            lower=0,
            outflow=endpoint(capacity=rate(2), allocation=priority(this.p1, this.p2)),
        ),
        value('mid', 'L', 0, lower=0),
        value('end', 'L', 0, lower=0),
        value('out', 'L', 0, lower=0),
        flow('p1', this.source, this.mid, request=rate(1)),
        flow('p2', this.source, this.mid, request=rate(1)),
        flow('drain', this.mid, this.end, request=rate(3)),
        flow('burn', this.end, this.out, request=rate(1)),
    )
    program = b.finish()
    record = run_for(program, 4)
    found = [at(record, program, f'line.{name}', 4)[0] for name in ('source', 'mid', 'end', 'out')]
    assert found == pytest.approx([92, 0, 4, 4], abs=1e-9)


@pytest.mark.parametrize('order', [('to_full', 'to_empty'), ('to_empty', 'to_full'), ()])
def test_a_flow_that_a_bound_holds_back_leaves_its_share_of_the_limit_to_the_others(order):
    """Two flows of 10 L/h draw on a store under a limit of 10 L/h; one goes into a full stock and
    moves nothing, so the other takes the whole limit, in any order and in proportion."""
    b = Builder(UNITS)
    allocation = {'allocation': priority(*(getattr(this, name) for name in order))} if order else {}
    b.entity(
        'site',
        value('store', 'L', 100, lower=0, outflow=endpoint(capacity=rate(10), **allocation)),
        value('full', 'L', 5, lower=0, upper=5),
        value('empty', 'L', 0, lower=0),
        flow('to_full', this.store, this.full, request=rate(10)),
        flow('to_empty', this.store, this.empty, request=rate(10)),
    )
    program = b.finish()
    record = run_for(program, 1)
    found = [at(record, program, f'site.{name}', 1)[0] for name in ('empty', 'full', 'store')]
    assert found == pytest.approx([10, 5, 90])


def test_priority_is_served_upstream_first():
    """1 L/h reaches the empty a, whose outflow serves `high` before the leg of `feed`, a flow with
    legs that carries a to b together with a reserve to used; b's outflow orders `out` before
    `other`. a decides first: high takes the 1 L/h, so feed and all after it carry nothing."""
    b = Builder(UNITS)
    b.entity(
        'plant',
        value(
            'a',
            'L',
            0,
            lower=0,
            outflow=endpoint(capacity=rate(100), allocation=priority(this.high, this.feed.people)),
        ),
        value(
            'b',
            'L',
            0,
            lower=0,
            outflow=endpoint(capacity=rate(100), allocation=priority(this.out, this.other)),
        ),
        value('reserve', 'L', 100, lower=0),
        *(value(name, 'L', 0, lower=0) for name in ('h', 'o', 'p', 'used')),
        flow('supply', SOURCE, this.a, request=rate(1), capacity=rate(1)),
        flow('high', this.a, this.h, request=rate(1)),
        legs(
            'feed',
            flow('people', this.a, this.b, request=rate(1)),
            flow('material', this.reserve, this.used, request=rate(1)),
        ),
        flow('out', this.b, this.o, request=rate(1)),
        flow('other', this.b, this.p, request=rate(1)),
    )
    program = b.finish()
    record = run_for(program, 1)
    found = [at(record, program, f'plant.{name}', 1)[0] for name in ('h', 'o', 'p', 'used')]
    assert found == pytest.approx([1, 0, 0, 0], abs=1e-9)


def test_a_flow_with_legs_that_runs_short_leaves_its_share_of_the_limit_to_the_others():
    """The first flow under the limit moves the store together with items from an empty stock, so it
    moves nothing; the second takes the whole limit of 10 L/h."""
    b = Builder(UNITS)
    b.entity(
        'site',
        value(
            'store',
            'L',
            100,
            lower=0,
            outflow=endpoint(capacity=rate(10), allocation=priority(this.both.x_leg, this.other)),
        ),
        value('items', 'L', 0, lower=0),
        *(value(name, 'L', 0, lower=0) for name in ('x', 'y', 'out')),
        legs(
            'both',
            flow('x_leg', this.store, this.x, request=rate(10)),
            flow('y_leg', this.items, this.y, request=rate(10)),
        ),
        flow('other', this.store, this.out, request=rate(10)),
    )
    program = b.finish()
    record = run_for(program, 1)
    found = [at(record, program, f'site.{name}', 1)[0] for name in ('out', 'x', 'store')]
    assert found == pytest.approx([10, 0, 90], abs=1e-9)


def test_the_running_total_of_a_drain_with_legs_is_exact_and_stops_when_the_stock_is_empty():
    """The stock falls 10 L/h from 100 L and is empty at 10 h; its running total is 100 t - 5 t^2 L h,
    375 at 5 h and 500 from 10 h on. The spares that go with it stop with it, at 900 L."""
    b = Builder(UNITS)
    b.entity(
        'depot',
        value('stock', 'L', 100, lower=0),
        value('spares', 'L', 1000, lower=0),
        value('shipped', 'L', 0, lower=0),
        value('used', 'L', 0, lower=0),
        value('exposure', 'L*h', 0, lower=0),
        legs(
            'shipment',
            flow('goods', this.stock, this.shipped, request=rate(10)),
            flow('parts', this.spares, this.used, request=rate(10)),
        ),
        flow('accrue', SOURCE, this.exposure, request=formula(this.stock)),
    )
    program = b.finish()
    record = run_for(program, 20)
    assert at(record, program, 'depot.exposure', 5, 10, 20) == pytest.approx([375, 500, 500], rel=1e-9)
    assert at(record, program, 'depot.stock', 10, 20) == pytest.approx([0, 0], abs=1e-9)
    assert at(record, program, 'depot.spares', 10, 20) == pytest.approx([900, 900], rel=1e-9)
    assert at(record, program, 'depot.used', 20) == pytest.approx([100], rel=1e-9)


def test_an_empty_store_passes_on_what_comes_in_and_feeds_an_exact_quadratic_total():
    """mid stays empty, so its outflow of 8 L/h passes on only the 5 L/h that comes in: end = 5 t,
    and its running total is 2.5 t^2."""
    b = Builder(UNITS)
    b.entity(
        'line',
        value('mid', 'L', 0, lower=0),
        value('end', 'L', 0, lower=0),
        value('exposure', 'L*h', 0, lower=0),
        flow('supply', SOURCE, this.mid, request=rate(5), capacity=rate(5)),
        flow('pass_on', this.mid, this.end, request=rate(8)),
        flow('accrue', SOURCE, this.exposure, request=formula(this.end)),
    )
    program = b.finish()
    record = run_for(program, 10)
    assert at(record, program, 'line.mid', 10) == pytest.approx([0], abs=1e-9)
    assert at(record, program, 'line.end', 10) == pytest.approx([50], rel=1e-12)
    assert at(record, program, 'line.exposure', 10) == pytest.approx([250], rel=1e-12)


def test_an_inflow_linear_in_a_decaying_stock_matches_its_closed_form():
    """pending = 100 e^(-0.2 t); value' = 3 pending gives 1500 (1 - e^(-0.2 t))."""
    b = Builder(UNITS)
    b.entity(
        'cohort',
        value('pending', 'L', 100, lower=0),
        value('gone', 'L', 0, lower=0),
        value('value', 'L', 0, lower=0, scale=q(1000, 'L')),
        flow('decay', this.pending, this.gone, request=formula(q(0.2, '1/h') * this.pending)),
        flow('accrue', SOURCE, this.value, request=formula(q(3, '1/h') * this.pending)),
    )
    program = b.finish()
    record = run_for(program, 10)
    assert at(record, program, 'cohort.value', 10) == pytest.approx([1500 * -math.expm1(-2)], rel=1e-9)


def test_a_decay_chain_beside_straight_lines_matches_its_closed_form():
    """A first-order chain a -> b -> c with an inflow r into a (Bateman), with k1 = 0.3/h and
    k2 = 0.05/h: a = r/k1 + (a0 - r/k1) e^(-k1 t); b solves b' + k2 b = k1 a; c = a0 + b0 + r t - a - b;
    beside it s = s0 + 4 t, d = 0.5 (s0 t + 2 t^2) that accrues half of s, and u = 3 t."""
    a0, b0, s0, r, k1, k2 = 100.0, 10.0, 2.0, 5.0, 0.3, 0.05
    b = Builder(UNITS)
    b.entity(
        'chain',
        value('a', 'L', a0, lower=0),
        value('b', 'L', b0, lower=0),
        value('c', 'L', 0, lower=0),
        value('s', 'L', s0, lower=0),
        value('d', 'L', 0, lower=0, scale=q(10_000, 'L')),
        value('u', 'L', 0, lower=0),
        flow('inflow', SOURCE, this.a, request=rate(r)),
        flow('first', this.a, this.b, request=formula(q(k1, '1/h') * this.a)),
        flow('second', this.b, this.c, request=formula(q(k2, '1/h') * this.b)),
        flow('grow', SOURCE, this.s, request=rate(4)),
        flow('accrue', SOURCE, this.d, request=formula(q(0.5, '1/h') * this.s)),
        flow('tick', SOURCE, this.u, request=rate(3)),
    )
    program = b.finish()
    record = run_for(program, 100)
    times = [0, 0.5, 3, 20, 100]
    found = {name: at(record, program, f'chain.{name}', *times) for name in 'abcsdu'}
    for k, time in enumerate(times):
        a = r / k1 + (a0 - r / k1) * math.exp(-k1 * time)
        first = (k1 * a0 - r) / (k2 - k1)
        b_ = r / k2 + first * math.exp(-k1 * time) + (b0 - r / k2 - first) * math.exp(-k2 * time)
        assert found['a'][k] == pytest.approx(a, rel=1e-9)
        assert found['b'][k] == pytest.approx(b_, rel=1e-9)
        assert found['c'][k] == pytest.approx(a0 + b0 + r * time - a - b_, rel=1e-9, abs=1e-9)
        assert found['s'][k] == pytest.approx(s0 + 4 * time, rel=1e-12)
        assert found['d'][k] == pytest.approx(0.5 * (s0 * time + 2 * time * time), rel=1e-9, abs=1e-9)
        assert found['u'][k] == pytest.approx(3 * time, rel=1e-12)


def test_a_state_outside_its_bounds_at_the_start_fails_the_run_and_names_it():
    b = Builder(UNITS)
    b.entity(
        'tank',
        input_('initial_water', 'L', 8),
        input_('initial_spare', 'L', 10),
        value('water', 'L', this.initial_water, lower=0),
        value('spare', 'L', this.initial_spare, lower=0, upper=20),
        flow('out', this.water, SINK, request=rate(1)),
    )
    inputs = (
        InputValue('tank', 'initial_water', Quantity(-1, 'L')),
        InputValue('tank', 'initial_spare', Quantity(30, 'L')),
    )
    record = run(b.finish(), Configuration(Request(1), inputs=inputs))
    message = record.failure.detail('message')
    assert record.failure.t == 0 and 'State bounds violated' in message
    assert message.index('tank.water') < message.index('tank.spare')
