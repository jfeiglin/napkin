"""A crossing of a store that only rises or only falls between moments (spec, "Monitoring a threshold").

The rate of such a store can read the store, so its set runs on a curve: here the continuous engine's
closed form of an exponential decay. Between moments the store less its threshold changes its sign
once at most, so a trigger's first contact is bracketed on the curve and located by bisection
(`timeline/triggers.py`). A comparison on a curve that the engine cannot certify stops the run with a
diagnostic. The expected times come from the closed form of exponential decay, not from the engine.
"""

from __future__ import annotations

import math

import pytest

from napkin.engine import run
from napkin.program.build import (
    SOURCE,
    Builder,
    add,
    after,
    event,
    flow,
    formula,
    input_,
    q,
    reset_when,
    start,
    this,
    value,
    when,
)
from napkin.program.config import Configuration, Numerics, Request

START = 100  # people in the tank
RATE = 0.1  # per hour: the drain takes this share of the water each hour


def tank(*parts, horizon=30):
    """A tank that drains in proportion to its water into a tally of what it drained, and an alarm
    event whose trigger watches `test`."""
    b = Builder({'h': {'time': 1}, 'person': {'people': 1}})
    b.entity(
        'tank',
        value('water', 'person', START, lower=0, scale=START),
        value('drained', 'person', 0, lower=0, scale=START),
        input_('k', '1/h', RATE, lower=0.01, upper=1),
        value('alarms', '', 0),
        flow('drain', this.water, this.drained, request=formula(this.water * this.k)),
        *parts,
    )
    return b.finish(), Configuration(Request(horizon))


def alarm(test):
    """An event that its trigger starts once, when `test` first holds."""
    return event(
        'low', when(test, start(this.low), reset=reset_when(False)), after(q(0, 'h'), add(this.alarms, 1))
    )


def fired(record):
    return [entry.t for entry in record.entries('fire', 'tank.low.when[0]')]


def decay_time(level):
    """When 100 people that leave at 10% an hour fall to `level` people."""
    return math.log(START / level) / RATE


def test_a_falling_store_triggers_where_it_reaches_its_value():
    record = run(*tank(alarm(this.water <= q(50, 'person'))))
    assert record.failure is None
    (at,) = fired(record)
    assert at == pytest.approx(decay_time(50), rel=1e-6)


def test_a_rising_tally_triggers_where_it_reaches_its_value():
    record = run(*tank(alarm(this.drained >= q(50, 'person'))))
    (at,) = fired(record)
    assert at == pytest.approx(decay_time(50), rel=1e-6)


def test_a_store_that_only_approaches_its_value_triggers_within_its_tolerance():
    # Water that drains in proportion to itself never reaches 0 people. The trigger holds once the
    # water is within its tolerance of 0 people (its scale, 100 people, times the tolerance factor),
    # so it fires by then, not at some later moment.
    horizon = 300
    record = run(*tank(alarm(this.water <= q(0, 'person')), horizon=horizon))
    tolerance = Numerics().atol_factor * START
    (at,) = fired(record)
    assert decay_time(tolerance) * (1 - 1e-6) <= at <= decay_time(tolerance / 2) * (1 + 1e-6)
    assert at < horizon


def test_a_store_that_both_rises_and_falls_on_a_curve_is_a_diagnostic():
    # An inflow and an outflow that reads the water: no rule of its set says which way the water
    # moves, so the first contact of the trigger cannot be certified, and the run says so.
    record = run(
        *tank(
            flow('fill', SOURCE, this.water, request=q(5, 'person/h')), alarm(this.water <= q(60, 'person'))
        )
    )
    assert 'cannot be certified' in record.failure.detail('message')
    assert record.failure.t == 0
