"""Requests that decay toward zero in floating point, by local sharing.

A rate that follows a decaying quantity passes below the smallest normal number of a float (about
2.2e-308) in a long run: 9 e^-t L/h does at 708 h. No float holds the served fraction of such a
request (one over it overflows), so it is no claim of local sharing (`network.py`), and a part whose
requests are all that small is read in units of one. The expected numbers are worked by hand.
"""

from __future__ import annotations

import math

import pytest

from napkin.engine import read
from napkin.engine.timeline import Plan
from napkin.engine.timeline.plan import SPARSE
from napkin.engine.timeline.run import Run
from napkin.program.build import SINK, SOURCE, Builder, call, endpoint, flow, formula, q, t, this, value
from napkin.program.config import Configuration, Request
from napkin.program.record import Key

UNITS = {'h': {'time': 1}, 'L': {'volume': 1}}


def reservoir(horizon):
    """A reservoir, empty at first, that a storm of 9 e^-t L/h fills and that spills twice what it
    holds each hour; an outflow capacity of 100 L/h, which never binds, puts it on the sparse
    integrator. It holds 9 (e^-t - e^-2t) L."""
    b = Builder(UNITS)
    b.entity(
        'reservoir',
        value('water', 'L', 0, lower=0, outflow=endpoint(capacity=q(100, 'L/h'))),
        flow('storm', SOURCE, this.water, request=formula(q(9, 'L/h') * call('exp', -(t / q(1, 'h'))))),
        flow('spill', this.water, SINK, request=formula(this.water * 2 / q(1, 'h'))),
    )
    return b.finish(), Configuration(Request(horizon))


def test_a_storm_that_decays_past_the_smallest_float_runs_to_its_horizon():
    """To 1000 h the storm's request passes below the smallest normal float, at 708 h; the run goes
    on to its horizon. The reservoir holds 9 (e^-5 - e^-10) L at 5 h, and 9 e^-1000 L at 1000 h,
    below the 1e-10 L limit used here. The storm and spill rates also decay to zero."""
    program, configuration = reservoir(1000)
    made = Run(Plan.of(program, configuration))
    record = made.run()
    assert record.failure is None, record.failure
    assert {connected.way for connected, _ in made.ways.sets.values()} == {SPARSE}
    (water,) = read(record, program, [Key('reservoir', ('water',))], [5.0, 1000.0])
    assert water.values[0] == pytest.approx(9 * (math.exp(-5) - math.exp(-10)), rel=1e-6)
    assert abs(water.values[1]) <= 1e-10
    for name in ('storm', 'spill'):
        (rate,) = read(record, program, [Key('reservoir', (name, 'actual_rate'))], [1000.0])
        assert abs(rate.values[0]) <= 2e-10
