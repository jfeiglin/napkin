"""The closed-form runs of the old timeline engine on templates and tables that are no events (its
event cases are in `test_timeline_events.py`): the flows out of a tank that empties share what comes
in by its outflow's rule, an empty tank limits the tank after it, the legs of a flow with legs are cut
together when one of their sources is empty, and a reduction in the rate of every member of a table
gives the logistic curve.

Each expected value is worked by hand from lines and from the logistic equation. A request is soft
(D15): a supply that must carry no more than it asks for has its capacity at its request.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from napkin.engine import read, run
from napkin.program.build import (
    SOURCE,
    Builder,
    endpoint,
    flow,
    fmax,
    formula,
    fsum,
    input_,
    legs,
    priority,
    q,
    root,
    this,
    value,
)
from napkin.program.config import Configuration, Request

UNITS = {'h': {'time': 1}, 'L': {'volume': 1}}


def rate(number):
    return q(number, 'L/h')


def supply(name, into, number):
    """A supply of `number` L/h that carries no more than it asks for."""
    return flow(name, SOURCE, into, request=rate(number), capacity=rate(number))


def run_for(program, horizon):
    record = run(program, Configuration(Request(horizon)))
    assert record.failure is None, record.failure.detail('message')
    return record


def at(record, program, path, *times):
    (reading,) = read(record, program, [path], [float(time) for time in times])
    return list(reading.values)


@pytest.mark.parametrize('order', [(), ('first', 'second'), ('second', 'first')])
def test_the_flows_out_of_an_empty_tank_share_what_comes_in_as_its_outflow_says(order):
    """The tank of 2 L gets 0.2 L/h, and its flows ask 0.3 and 0.5 L/h: it is empty at 2 / 0.6 h.
    Then they share the 0.2 L/h: in proportion to what they ask (0.075 and 0.125), or by priority
    (the first its request up to 0.2, the other what is left)."""
    b = Builder(UNITS)
    allocation = {'allocation': priority(*(getattr(this, name) for name in order))} if order else {}
    b.entity(
        'tank',
        value('held', 'L', 2, lower=0, outflow=endpoint(capacity=rate(100), **allocation)),
        value('one', 'L', 0, lower=0),
        value('two', 'L', 0, lower=0),
        supply('fill', this.held, 0.2),
        flow('first', this.held, this.one, request=rate(0.3)),
        flow('second', this.held, this.two, request=rate(0.5)),
    )
    program = b.finish()
    record = run_for(program, 10)
    empty = 2 / 0.6
    shares = {
        (): (0.2 * 0.3 / 0.8, 0.2 * 0.5 / 0.8),
        ('first', 'second'): (0.2, 0),
        ('second', 'first'): (0, 0.2),
    }
    one, two = shares[order]
    assert at(record, program, 'tank.one', 10) == pytest.approx([0.3 * empty + one * (10 - empty)], rel=1e-9)
    assert at(record, program, 'tank.two', 10) == pytest.approx([0.5 * empty + two * (10 - empty)], rel=1e-9)
    assert at(record, program, 'tank.held', 10) == pytest.approx([0], abs=1e-9)


def test_an_empty_tank_limits_the_tank_after_it():
    """The first tank (2 L, 0.3 L/h in and 1 L/h out) is empty at 2 / 0.7 h and then passes on 0.3
    L/h. The second (2 L, 1.5 L/h out) loses 0.5 L/h until then and 1.2 L/h after, and is empty in
    its turn; from then 0.3 L/h goes out. What went out is what the tanks held and what came in."""
    b = Builder(UNITS)
    b.entity(
        'line',
        value('first', 'L', 2, lower=0),
        value('second', 'L', 2, lower=0),
        value('out', 'L', 0, lower=0),
        supply('fill', this.first, 0.3),
        flow('hand', this.first, this.second, request=rate(1)),
        flow('leave', this.second, this.out, request=rate(1.5)),
    )
    program = b.finish()
    record = run_for(program, 10)
    first_empty = 2 / 0.7
    second_empty = first_empty + (2 - 0.5 * first_empty) / 1.2
    out = 1.5 * second_empty + 0.3 * (10 - second_empty)
    assert out == pytest.approx(2 + 2 + 0.3 * 10, rel=1e-12)
    assert at(record, program, 'line.out', 10) == pytest.approx([out], rel=1e-9)
    assert at(record, program, 'line.first', 10) + at(record, program, 'line.second', 10) == pytest.approx(
        [0, 0], abs=1e-9
    )


@pytest.mark.parametrize('inflow', [0.0, 0.25])
def test_the_legs_of_a_flow_with_legs_are_cut_together_when_one_source_is_empty(inflow):
    """The legs ask 1 and 2 L/h. The first source (2 L, with `inflow` L/h in) is empty at
    2 / (1 - inflow) h; from then the first leg moves what comes in, the fraction `inflow` of its
    request, and the second leg that fraction of its 2 L/h, though its source has water."""
    b = Builder(UNITS)
    b.entity(
        'plant',
        value('a', 'L', 2, lower=0),
        value('c', 'L', 10, lower=0),
        value('b', 'L', 0, lower=0),
        value('d', 'L', 0, lower=0),
        supply('feed', this.a, inflow),
        legs(
            'make', flow('ab', this.a, this.b, request=rate(1)), flow('cd', this.c, this.d, request=rate(2))
        ),
    )
    program = b.finish()
    record = run_for(program, 10)
    empty = 2 / (1 - inflow)
    moved = 1 * empty + inflow * (10 - empty)
    assert at(record, program, 'plant.b', 10) == pytest.approx([moved], rel=1e-9)
    assert at(record, program, 'plant.d', 10) == pytest.approx([2 * moved], rel=1e-9)
    assert at(record, program, 'plant.c', 10) == pytest.approx([10 - 2 * moved], rel=1e-9)


def test_a_reduction_in_the_rate_of_every_member_gives_the_logistic_curve():
    """Each level grows at `gain * level * (1 - mean)`, so the sum S of the n levels has
    S' = gain S (1 - S / n): S = n / (1 + (n / S0 - 1) e^(-gain t)), and each level keeps its share of
    the sum."""
    starts = [0.05, 0.4, 0.11, 0.27, 0.33, 0.02, 0.19]
    count, gain = len(starts), 0.63
    b = Builder(UNITS)
    cell = b.template(
        'Cell',
        input_('gain', '1/h', gain),
        value('level', 'L', 0.05, lower=0, scale=q(1, 'L')),
        flow(
            'grow',
            SOURCE,
            this.level,
            request=formula(this.gain * this.level * fmax(0, 1 - root.mean / q(1, 'L'))),
        ),
    )
    for k, start in enumerate(starts):
        b.member(cell, f'c{k}', level=q(start, 'L'))
    b.root(value('mean', 'L', formula(fsum(cell.instances.level) / count)))
    program = b.finish()
    record = run_for(program, 10)
    total = count / (1 + (count / sum(starts) - 1) * math.exp(-gain * 10))
    levels = np.array([at(record, program, f'c{k}.level', 10)[0] for k in range(count)])
    assert levels.sum() == pytest.approx(total, rel=1e-7)
    assert levels / levels.sum() == pytest.approx(np.array(starts) / sum(starts), rel=1e-7)
