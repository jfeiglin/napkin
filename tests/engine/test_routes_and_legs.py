"""Reversible routes and flows with legs on the engine (S3), beyond the worked examples of the spec.

A route has one signed rate within [-capacity, capacity], and its legs `forward` and `backward` carry
its positive parts in the stores' collections; a flow with legs has one served fraction, and each leg
carries the fraction times its own request (spec, "Flows and algebraic solvers" and "Shared resources
and competing invocations"). The expected values are worked by hand from the rules of local sharing,
or are the oracle's (`tests/reference/`), which runs the same program in exact fractions.
"""

from __future__ import annotations

import math
from fractions import Fraction

import pytest

from napkin.engine import read, run
from napkin.engine.timeline import Outside
from napkin.program.build import (
    SINK,
    SOURCE,
    Builder,
    endpoint,
    flow,
    formula,
    legs,
    priority,
    q,
    route,
    t,
    this,
    value,
)
from napkin.program.config import Configuration, Request
from napkin.program.record import Key
from tests.reference.from_program import run_of, value_at

UNITS = {'h': {'time': 1}, 'L': {'volume': 1}}


def rate(number):
    return q(number, 'L/h')


def values(program, horizon, keys, times):
    record = run(program, Configuration(Request(horizon)))
    assert record.failure is None, record.failure.detail('message')
    return [reading.values for reading in read(record, program, keys, times)]


def agrees_with_the_oracle(program, horizon, keys, times):
    configuration = Configuration(Request(horizon))
    oracle, failed = run_of(program, configuration)
    assert failed is None
    found = values(program, horizon, keys, times)
    for key, numbers in zip(keys, found):
        expected = [float(value_at(oracle, program, key, Fraction(time))) for time in times]
        assert list(numbers) == pytest.approx(expected, rel=1e-9, abs=1e-12), str(key)


def test_a_route_request_that_crosses_zero_stops_no_run():
    """The route asks 3 - t L/h, west to east: positive until 3 h, then negative. Nothing limits it,
    so its rate is its request, and west holds 10 - (3t - t^2 / 2) L: 5.5 at 3 h and 10 again at 6 h.
    Its forward leg reads the positive part and its backward leg the negative part."""
    b = Builder(UNITS)
    west = b.entity('west', value('water', 'L', 10, lower=0, upper=20))
    east = b.entity('east', value('water', 'L', 10, lower=0, upper=20))
    b.entity('channel', route('link', west.water, east.water, request=formula(rate(3) - q(1, 'L/h/h') * t)))
    program = b.finish()
    times = [1, 3, 5, 6]
    keys = [Key('west', ('water',)), Key('east', ('water',))]
    keys += [Key('channel', ('link', *steps, 'actual_rate')) for steps in ((), ('forward',), ('backward',))]
    water_west, water_east, signed, forward, backward = values(program, 6, keys, times)
    assert water_west == pytest.approx([10 - (3 * x - x * x / 2) for x in times], rel=1e-7)
    assert water_east == pytest.approx([10 + (3 * x - x * x / 2) for x in times], rel=1e-7)
    assert signed == pytest.approx([2, 0, -2, -3], abs=1e-7)
    assert forward == pytest.approx([2, 0, 0, 0], abs=1e-7)
    assert backward == pytest.approx([0, 0, 2, 3], abs=1e-7)


def test_a_route_is_held_by_its_capacity_and_by_a_store_that_meets_its_bound():
    """The route asks -5 L/h with a capacity of 2: it moves 2 L/h east to west. East holds 3 L and
    gets 1 L/h of rain, so it is empty at 3 h; from then on the route passes on the rain, 1 L/h."""
    b = Builder(UNITS)
    west = b.entity('west', value('water', 'L', 0, lower=0))
    east = b.entity(
        'east',
        value('water', 'L', 3, lower=0),
        flow('rain', SOURCE, this.water, request=rate(1), capacity=rate(1)),
    )
    b.entity('channel', route('link', west.water, east.water, request=rate(-5), capacity=rate(2)))
    program = b.finish()
    keys = [Key('channel', ('link', 'actual_rate')), Key('east', ('water',)), Key('west', ('water',))]
    times = [0, 1, 2, 3, 4]
    signed, water_east, water_west = values(program, 4, keys, times)
    assert signed == pytest.approx([-2, -2, -2, -1, -1])
    assert water_east == pytest.approx([3, 2, 1, 0, 0], abs=1e-12)
    assert water_west == pytest.approx([0, 2, 4, 6, 7])
    agrees_with_the_oracle(program, 4, keys, [0, 1, 2.5, 3, 3.5, 4])


def ranked_legs():
    """West gives at most 3 L/h, first to the forward leg of the route to east and then to a pipe;
    east takes in at most 1 L/h, first from the leg `b` of a flow with legs and then from the
    route's forward leg."""
    b = Builder(UNITS)
    b.entity(
        'm',
        value(
            'west',
            'L',
            50,
            lower=0,
            outflow=endpoint(capacity=rate(3), allocation=priority(this.link.forward, this.pipe)),
        ),
        value(
            'east',
            'L',
            10,
            lower=0,
            inflow=endpoint(capacity=rate(1), allocation=priority(this.restore.b, this.link.forward)),
        ),
        value('far', 'L', 0, lower=0),
        flow('pipe', this.west, SINK, request=rate(2)),
        route('link', this.west, this.east, request=rate(2)),
        legs(
            'restore',
            flow('a', SOURCE, this.far, request=rate(2)),
            flow('b', SOURCE, this.east, request=rate(2)),
        ),
    )
    return b.finish()


def test_priority_names_the_leg_of_a_route_and_a_leg_of_a_flow_with_legs():
    """The leg `b` comes first at east: its fraction is 1/2, so each leg carries 1 L/h, which fills
    east's inflow. The route's forward leg comes next there and gets nothing, so the route carries
    nothing, though west ranks it first; the pipe then gets its 2 L/h of west's 3."""
    program = ranked_legs()
    keys = [
        Key('m', ('restore', 'served_fraction')),
        Key('m', ('restore', 'a', 'actual_rate')),
        Key('m', ('link', 'actual_rate')),
        Key('m', ('pipe', 'actual_rate')),
    ]
    found = values(program, 1, keys, [0, 1])
    assert [numbers[0] for numbers in found] == pytest.approx([0.5, 1, 0, 2])
    agrees_with_the_oracle(program, 1, [*keys, Key('m', ('west',)), Key('m', ('east',))], [0, 0.5, 1])


def legs_ranked_apart():
    """A flow with legs out of two stores, which the two outflows rank apart: `a` first at A, ahead
    of P; Q first at B, ahead of `b`."""
    b = Builder(UNITS)
    b.entity(
        'm',
        value(
            'one',
            'L',
            100,
            lower=0,
            outflow=endpoint(capacity=rate(2), allocation=priority(this.both.a, this.p)),
        ),
        value(
            'two',
            'L',
            100,
            lower=0,
            outflow=endpoint(capacity=rate(2), allocation=priority(this.q, this.both.b)),
        ),
        legs('both', flow('a', this.one, SINK, request=rate(2)), flow('b', this.two, SINK, request=rate(2))),
        flow('p', this.one, SINK, request=rate(2)),
        flow('q', this.two, SINK, request=rate(2)),
    )
    return b.finish()


def test_legs_that_two_endpoints_rank_differently_wait_for_every_claim_ranked_ahead():
    """R-A2-12: a claim waits for every claim that any endpoint ranks ahead of it. Q is ahead of the
    flow with legs at B, which is ahead of P at A: Q takes all 2 L/h of B, so the flow with legs gets
    a fraction of zero, and then P takes 2 L/h of A."""
    program = legs_ranked_apart()
    keys = [
        Key('m', ('q', 'actual_rate')),
        Key('m', ('both', 'served_fraction')),
        Key('m', ('p', 'actual_rate')),
    ]
    found = values(program, 1, keys, [0, 1])
    assert [numbers[0] for numbers in found] == pytest.approx([2, 0, 2])
    agrees_with_the_oracle(program, 1, keys, [0, 0.5, 1])


def test_the_ends_of_a_flow_and_of_a_leg_name_their_stores():
    """`.source` and `.sink` of a directed flow, of a leg of a route and of a leg of a flow with legs
    are the stores at those ends: a formula reads their levels as it reads the stores."""
    b = Builder(UNITS)
    b.entity(
        'm',
        value('high', 'L', 10, lower=0),
        value('low', 'L', 4, lower=0),
        flow('pipe', this.high, this.low, request=rate(1)),
        route('link', this.high, this.low, request=rate(0)),
        legs(
            'pair',
            flow('left', this.low, SINK, request=rate(0)),
            flow('right', SOURCE, this.high, request=rate(0)),
        ),
        value('pipe_from', 'L', formula(this.pipe.source)),
        value('back_from', 'L', formula(this.link.backward.source)),
        value('left_from', 'L', formula(this.pair.left.source)),
        value('right_to', 'L', formula(this.pair.right.sink)),
    )
    program = b.finish()
    names = ('pipe_from', 'back_from', 'left_from', 'right_to')
    found = values(program, 2, [Key('m', (name,)) for name in names], [0, 2])
    assert [list(numbers) for numbers in found] == [[10, 8], [4, 6], [4, 6], [10, 8]]


def test_the_end_of_a_flow_at_the_outside_holds_no_value():
    """SOURCE and SINK are no stores: a read of an end there is refused by name."""
    b = Builder(UNITS)
    b.entity(
        'm',
        value('tank', 'L', 1, lower=0),
        flow('fill', SOURCE, this.tank, request=rate(1)),
        value('from', 'L', formula(this.fill.source)),
    )
    program = b.finish()
    with pytest.raises(Outside, match=r'm\.fill\.source is SOURCE, which holds no value'):
        run(program, Configuration(Request(1)))


def test_a_request_at_an_endpoint_that_a_route_meets_has_no_answer_and_names_the_endpoint():
    """The positive part of a route's rate in a claim would make fair sharing maximize a convex
    function; the oracle does not settle it either: the run stops and names the endpoint."""
    b = Builder(UNITS)
    west = b.entity('west', value('water', 'L', 10, lower=0, outflow=endpoint(request=rate(1))))
    east = b.entity('east', value('water', 'L', 10, lower=0))
    b.entity('channel', route('link', west.water, east.water, request=rate(1)))
    record = run(b.finish(), Configuration(Request(1)))
    assert record.failure is not None
    message = record.failure.detail('message')
    assert 'west.water.outflow' in message and 'channel.link' in message


def test_a_store_that_only_receives_elsewhere_can_be_an_end_of_a_route():
    """The language has no mark for a tally: a store is one by its use, when no flow takes from it.
    A route takes from both of its ends, so a store that only a pipe fills elsewhere is an end of a
    route like any other. `used` is empty and gets 2 L/h; the route asks 1 L/h out of it, to `other`,
    which holds 5 L: `used` passes on the route's 1 L/h and keeps the rest."""
    b = Builder(UNITS)
    b.entity(
        'm',
        value('used', 'L', 0, lower=0),
        value('other', 'L', 5, lower=0),
        flow('fill', SOURCE, this.used, request=rate(2), capacity=rate(2)),
        route('link', this.used, this.other, request=rate(1)),
    )
    program = b.finish()
    keys = [Key('m', ('used',)), Key('m', ('other',)), Key('m', ('link', 'actual_rate'))]
    used, other, signed = values(program, 2, keys, [2])
    assert (used[0], other[0], signed[0]) == pytest.approx((2, 7, 1))
    agrees_with_the_oracle(program, 2, keys, [0, 1, 2])


def test_a_leg_request_that_moves_keeps_its_flow_at_its_fraction():
    """The labor leg asks a tenth of the crew's hours each hour, and nothing limits either leg: the
    fraction is 1, the hours fall as 100 exp(-t / 10) and the work leg moves 8 L/h."""
    b = Builder(UNITS)
    b.entity(
        'site',
        value('hours', 'L', 100, lower=0),
        value('used', 'L', 0, lower=0),
        value('work', 'L', 100, lower=0),
        value('done', 'L', 0, lower=0),
        legs(
            'restore',
            flow('labor', this.hours, this.used, request=formula(this.hours / q(10, 'h'))),
            flow('job', this.work, this.done, request=rate(8)),
        ),
    )
    program = b.finish()
    keys = [Key('site', (name,)) for name in ('hours', 'done')] + [
        Key('site', ('restore', 'served_fraction'))
    ]
    hours, done, fraction = values(program, 5, keys, [1, 5])
    assert hours == pytest.approx([100 * math.exp(-x / 10) for x in (1, 5)], rel=1e-7)
    assert done == pytest.approx([8, 40], rel=1e-9)
    assert fraction == pytest.approx([1, 1])
