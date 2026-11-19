"""A rate that tests a tally against its lower bound, at the start of a segment in which the tally
leaves that bound.

A valve opens at t = 2 h: a clock starts an event whose stage opens it, and the moment builds the set
again. Material escapes at held / (1 h) * exp(-(t - 2 h) / 1 h), so held(t) = n * exp(-(1 -
exp(-(t - 2)))) for t >= 2, and released = n - held. An hour count runs while anything has escaped:
its rate is 1 if released > 0, else 0, so it equals t - 2 after the opening. The count's rate at the
start of the segment is the limit from the right, where the tally has left its bound (the continuous
engine's departing ledgers); taking it from the bound (0) made the solver fail for the scales 1 and 100.
"""

from __future__ import annotations

import math

import pytest

from napkin.engine import read, run
from napkin.program.build import (
    BOOL,
    SOURCE,
    Builder,
    after,
    assign,
    call,
    event,
    flow,
    formula,
    ifelse,
    q,
    reset_when,
    start,
    t,
    this,
    value,
    when,
)
from napkin.program.config import Configuration, Request

OPEN_H = 2.0


def valve(held=100, scale=100):
    b = Builder({'h': {'time': 1}, 'person': {'people': 1}})
    escape = this.held / q(1, 'h') * call('exp', -(t - q(OPEN_H, 'h')) / q(1, 'h'))
    b.entity(
        's',
        value('held', 'person', held, lower=0, scale=scale),
        value('hours', '', 0, lower=0, scale=10),
        value('released', 'person', 0, lower=0, scale=scale),
        value('open', BOOL, False),
        flow(
            'escape', this.held, this.released, request=formula(ifelse(this.open, escape, q(0, 'person/h')))
        ),
        flow(
            'count',
            SOURCE,
            this.hours,
            request=formula(ifelse(this.released > q(0, 'person'), 1, 0) / q(1, 'h')),
        ),
        event(
            'opening',
            when(t >= q(OPEN_H, 'h'), start(this.opening), reset=reset_when(False)),
            after(q(0, 'h'), assign(this.open, True)),
        ),
    )
    program = b.finish()
    return program, run(program, Configuration(Request(10)))


@pytest.mark.parametrize('scale', [1, 100, 70000])
def test_a_tally_that_leaves_its_bound_switches_the_rate_at_once(scale):
    program, record = valve(scale=scale)
    assert record.failure is None, record.failure
    times = [1.0, OPEN_H, 2.5, 4.0, 10.0]
    held, hours, released = read(record, program, ['s.held', 's.hours', 's.released'], times)
    for k, at in enumerate(times):
        expected = 100 * math.exp(-(1 - math.exp(-(at - OPEN_H)))) if at >= OPEN_H else 100
        assert hours.values[k] == pytest.approx(max(0.0, at - OPEN_H), abs=1e-9)
        assert held.values[k] == pytest.approx(expected, rel=1e-7)
        assert held.values[k] + released.values[k] == pytest.approx(100, abs=1e-9 * scale)


def test_a_tally_that_stays_on_its_bound_keeps_the_rate_off():
    # Nothing is held, so nothing escapes when the valve opens: the count must not start.
    program, record = valve(held=0)
    released, hours = read(record, program, ['s.released', 's.hours'], [OPEN_H, 4.0, 10.0])
    assert released.values == (0.0, 0.0, 0.0)
    assert hours.values == (0.0, 0.0, 0.0)
