"""A value at a time reads the same in a run that ends there as in one that goes on (the readiness
fixes, agent R's finding; `ways.Ways.finish`, `component.ComponentWay.finish`, `sparse.Sparse.finish`).

The horizon is an inclusive cutoff, and a read at a moment sees what its last round committed
(`program/record.py`). At a moment a commit can change a rate, and the settling builds the set
again: its rates there are those that its next segment starts with, which a run that goes on
records from there. A run whose horizon is that moment records the same: its sets stand at the
horizon with the rates of their state there, on the bounds that it rests on. So does a moment at
which a store empties, where a rate falls to zero.

The rule test: a plant on each way of running a set (arrays, lines, a component, the sparse
integrator, a declared solver, and a declared solver whose problem moves), whose pipe's request a
stage lowers from 2 L/h to 1 L/h at 1 h, and a first tank that empties: on the ways whose stores move
on lines, at 2 h, so that a run to 2 h ends as the store meets its bound; on curves at 2.25 h, between
the times read, since the time at which a curve meets a bound is known to within the crossing
tolerance, on either side of it (`moment.Clock`); a moving solver bounds the pipe by its tank, which
it reads as it moves, and the tank never empties: each value read at each moment and between them, in a run to that
time and in a run to 4 h, agree, exactly on lines and within the integration's tolerance on curves.
Worked by hand: the pipe carries 1 L/h at 1 h in both.
"""

from __future__ import annotations

import pytest

from napkin.engine.timeline import Plan, Run, read
from napkin.engine.timeline.plan import COMPONENT, DECLARED, FAMILY, LINES, SPARSE
from napkin.program.build import (
    SINK,
    Builder,
    after,
    assign,
    constraint,
    endpoint,
    event,
    flow,
    formula,
    given,
    local,
    maximize,
    named,
    q,
    solve_for,
    solver,
    start,
    this,
    value,
)
from napkin.program.config import Configuration, Request

UNITS = {'h': {'time': 1}, 'L': {'volume': 1}}
TIMES = [0.5, 1, 1.5, 2, 2.5, 3]
LONGER = 4
MOVING = 'moving solver'
WAYS = [FAMILY, LINES, COMPONENT, SPARSE, DECLARED, MOVING]
CURVED = {COMPONENT, SPARSE, MOVING}


def plant(way):
    """The plant of a way (see the module): `w0` of 3 L (3.25 L on curves, 7 L for a moving solver)
    feeds the pipe at the request `want`, which the tick lowers at 1 h. On arrays the pipe ends at SINK; else it fills `w1`, which drains, on
    lines at 1 L/h, on a component at half of `w1` an hour (each flow with its capacity at its
    request), on the sparse integrator so with an endpoint setting. A declared solver serves the
    pipe's rate up to `want`; a moving one up to `want` and to `w0` over an hour, which moves (and
    stays above `want`: from 7 L, `w0` holds 1 L at 5 h)."""
    b = Builder(UNITS)
    settings = {'outflow': endpoint(capacity=q(100, 'L/h'))} if way == SPARSE else {}
    parts = [
        value('w0', 'L', {MOVING: 7, COMPONENT: 3.25, SPARSE: 3.25}.get(way, 3), lower=0),
        value('w1', 'L', 1, lower=0, **settings),
        value('want', 'L/h', 2),
        event('tick', after(q(1, 'h'), assign(this.want, q(1, 'L/h')))),
    ]
    if way == FAMILY:
        parts.append(flow('pipe', this.w0, SINK, request=formula(this.want)))
    elif way in (DECLARED, MOVING):
        parts.append(flow('pipe', this.w0, SINK, request=q(10, 'L/h')))
    elif way == LINES:
        parts.append(flow('pipe', this.w0, this.w1, request=formula(this.want)))
        parts.append(flow('drain', this.w1, SINK, request=q(1, 'L/h')))
    else:
        want, drain = formula(this.want), formula(this.w1 / q(2, 'h'))
        parts.append(flow('pipe', this.w0, this.w1, request=want, capacity=want))
        parts.append(flow('drain', this.w1, SINK, request=drain, capacity=drain))
    member = b.entity('plant', *parts)
    if way in (DECLARED, MOVING):
        bounds = [constraint(local.use.actual_rate <= local.cap)]
        if way == MOVING:
            bounds.append(constraint(local.use.actual_rate <= local.left / q(1, 'h')))
        b.entity(
            'provider',
            solver(
                'share',
                given('use', member.pipe),
                given('cap', member.want),
                given('left', member.w0),
                solve_for(local.use.actual_rate),
                *bounds,
                maximize(local.use.actual_rate),
            ),
        )
    b.setup(start(named('plant').tick))
    return b.finish()


def paths(way):
    found = ['plant.w0', 'plant.w1', 'plant.want', 'plant.pipe.actual_rate']
    return found + ([] if way in (FAMILY, DECLARED, MOVING) else ['plant.drain.actual_rate'])


def ran(program, horizon):
    made = Run(Plan.of(program, Configuration(Request(horizon))))
    record = made.run()
    assert record.failure is None, record.failure.detail('message')
    return record, made


@pytest.mark.parametrize('way', WAYS)
def test_a_value_at_a_time_reads_the_same_in_a_run_that_ends_there_and_in_one_that_goes_on(way):
    program = plant(way)
    longer, made = ran(program, LONGER)
    found = {
        MOVING if connected.way == DECLARED and connected.moves else connected.way
        for connected, _ in made.ways.sets.values()
    }
    assert found == {way}
    keys = paths(way)
    for t in TIMES:
        ended, _ = ran(program, t)
        here = [reading.values[0] for reading in read(ended, program, keys, [t])]
        there = [reading.values[0] for reading in read(longer, program, keys, [t])]
        if way in CURVED:
            assert here == pytest.approx(there, rel=1e-7, abs=1e-7), (t, keys)
        else:
            assert here == there, (t, keys)
        if t == 1:
            # The commit of the moment lowers the request: the pipe carries 1 L/h there.
            assert here[keys.index('plant.pipe.actual_rate')] == pytest.approx(1, abs=1e-9)
