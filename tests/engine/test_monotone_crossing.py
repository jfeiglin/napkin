"""A crossing of a quantity that only rises or only falls between moments (docs/engine.md, Triggers).

The rate of such a quantity can read the state, so the solver integrates it numerically. Between
moments the quantity less its threshold changes sign at most once, so the solver's sign test at its
accepted steps brackets the crossing. Expected times come from the closed form of exponential decay,
not from the engine."""

from __future__ import annotations

import math

import pytest

from napkin.engine.runtime import NumericalSettings
from napkin.model import ModelError
from tests.build import document, entity, event, flow, library, named, parameter, run, stock

START = 100  # people in the tank
RATE = 0.1  # per hour: the drain takes this share of the water each hour


def tank(*members, horizon=30):
    """A tank that drains in proportion to its water, with a tally of what it drained."""
    return document(
        'Monotone crossing fixture',
        entity(
            'tank',
            stock('water', START, 'people', size=START),
            stock('drained', 0, 'people', kind='tally', size=START),
            parameter('k', RATE, 'per_h', 0.01, 1),
            named('alarm', 'off', 'on'),
            flow('drain', 'water -> drained', 'water * k'),
            *members,
        ),
        horizon=horizon,
    )


def fired(trajectory, rule):
    return [entry['t'] for entry in trajectory.trace if entry['rule'] == rule]


def decay_time(level):
    """When 100 people that leave at 10% an hour fall to `level` people."""
    return math.log(START / level) / RATE


def test_a_falling_quantity_triggers_where_it_reaches_its_value():
    _, trajectory = run(tank(event('low', 'water <= 50 people', 'alarm = "on"')))
    (at,) = fired(trajectory, 'tank.low')
    assert at == pytest.approx(decay_time(50), rel=1e-6)


def test_a_rising_tally_triggers_where_it_reaches_its_value():
    _, trajectory = run(tank(event('half', 'drained >= 50 people', 'alarm = "on"')))
    (at,) = fired(trajectory, 'tank.half')
    assert at == pytest.approx(decay_time(50), rel=1e-6)


def test_a_quantity_that_only_approaches_its_value_triggers_within_its_tolerance():
    # Water that drains in proportion to itself never reaches 0 people. The rule holds once the water is
    # within its tolerance of 0 people; the solver watches half that tolerance, so the rule fires by then,
    # not at some later moment.
    horizon = 300
    _, trajectory = run(tank(event('dry', 'water <= 0 people', 'alarm = "on"'), horizon=horizon))
    tolerance = NumericalSettings().atol_factor * START
    (at,) = fired(trajectory, 'tank.dry')
    assert decay_time(tolerance) * (1 - 1e-6) <= at <= decay_time(tolerance / 2) * (1 + 1e-6)
    assert at < horizon


def test_a_quantity_that_both_rises_and_falls_is_still_rejected():
    # An inflow and an outflow that reads the water: no proof says which way the water moves.
    text = tank(
        flow('fill', '-> water', '5 people/h'),
        event('low', 'water <= 60 people', 'alarm = "on"'),
    )
    with pytest.raises(ModelError) as raised:
        run(text, lib=library())
    assert any(d['code'] == 'unsupported_condition' for d in raised.value.diagnostics)
