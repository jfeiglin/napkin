"""A run whose rates switch back and forth at a condition stops with `chattering`
(`napkin/engine/continuous/integrate.py`, `Limit.accepted`, `chattering`).

The model: a tank whose two outflows are cut off when it is empty (`... if tank > 0 else 0`), with
an inflow that is less than what they ask. Above zero the tank falls; at zero the outflows stop and
the tank rises. The oracles: the closed form of the time at which the tank empties, and the closed
form of the same tank without the condition, whose outflows get what comes in when it is empty.
"""

import warnings

import pytest

from napkin.engine.continuous import integrate
from napkin.engine.continuous.integrate import STALLED_STEPS, Limit
from napkin.engine.runtime import SimulationError, simulate
from napkin.model.ir import EVENT_TIME_TOLERANCE_H
from tests import build as b
from tests.engine.test_roundoff_properties import model_of

DEMAND = 1e5  # people/h
SHARES = (1 / 3, 2 / 7)
FILL = 0.9  # the inflow, as a part of what the outflows ask
HORIZON = 40.0


def tank(level, cut):
    """The text of the model of a tank that starts at `level`; with `cut`, each outflow is cut off
    when the tank is empty."""
    flows = [
        b.flow(
            f'out{k}',
            b.move('tank', f'used{k}'),
            f'demand * {share!r} if tank > 0 else 0 people/h' if cut else f'demand * {share!r}',
        )
        for k, share in enumerate(SHARES)
    ]
    fill = '(' + ' + '.join(f'demand * {share!r}' for share in SHARES) + f') * {FILL!r}'
    return b.system(
        b.parameter('demand', DEMAND, 'people/h', 0, 1e12),
        b.stock('tank', level),
        *[b.stock(f'used{k}', 0, kind='tally', size=None) for k in range(len(SHARES))],
        b.flow('fill', b.move(None, 'tank'), fill),
        *flows,
        b.share('tank', '1e15 people/h', 'proportional'),
        horizon=HORIZON,
    )


def stopped(text, settings=None):
    """The last diagnostic of the run of `text`, which must stop."""
    with warnings.catch_warnings():
        # SciPy's Jacobian by differences overflows near the switch.
        warnings.simplefilter('ignore', RuntimeWarning)
        with pytest.raises(SimulationError) as caught:
            simulate(*model_of(text), settings)
    return caught.value.diagnostics[-1]


def test_a_tank_that_starts_empty_on_its_condition_stops_with_chattering():
    """The tank starts at zero, at the switch of its condition: the steps of the solver get shorter
    than the event time tolerance and stay so. The run stops after `STALLED_STEPS` of them, not on
    the budget of evaluations, and names the condition and the tank."""
    found = stopped(tank(0, cut=True))
    assert found['code'] == 'chattering'
    assert found['quantities'] == ['s.tank'] and len(found['surfaces']) == 1
    assert 0 <= found['from_h'] <= found['at_h'] <= found['from_h'] + STALLED_STEPS * EVENT_TIME_TOLERANCE_H


def test_a_tank_that_empties_stops_with_chattering_at_the_time_that_it_empties():
    """The tank empties at level / (what goes out - what comes in); there its condition switches
    back and forth, and the run stops there with `chattering`."""
    level = 5e4
    asked = DEMAND * sum(SHARES)
    empty = level / (asked * (1 - FILL))
    found = stopped(tank(level, cut=True))
    assert found['code'] == 'chattering' and found['quantities'] == ['s.tank']
    assert found['at_h'] == pytest.approx(empty, rel=1e-9)


def test_the_tank_without_the_condition_gives_its_outflows_what_comes_in_when_it_is_empty():
    """The advice of the diagnostic: without the condition, the tank empties at the same time, and
    after it each outflow gets its share of the inflow."""
    level = 5e4
    asked = DEMAND * sum(SHARES)
    empty = level / (asked * (1 - FILL))
    trajectory = simulate(*model_of(tank(level, cut=False)))
    end = trajectory.env_at(HORIZON)
    assert end['s.tank'] == pytest.approx(0.0, abs=1e-6)
    for k, share in enumerate(SHARES):
        expected = DEMAND * share * empty + DEMAND * share * FILL * (HORIZON - empty)
        assert end[f's.used{k}'] == pytest.approx(expected, rel=1e-9)


def test_a_segment_is_stalled_after_so_many_accepted_steps_in_a_row_that_are_too_short():
    short = EVENT_TIME_TOLERANCE_H / 2
    limit = Limit(1.0, 8.0)
    t = 3.0
    for _ in range(STALLED_STEPS - 1):
        assert not limit.accepted(t, t + short)
        t += short
    assert limit.accepted(t, t + short)
    assert limit.brief_from == 3.0
    # A longer step starts the count again.
    limit = Limit(1.0, 8.0)
    for _ in range(STALLED_STEPS - 1):
        limit.accepted(t, t + short)
        t += short
    assert not limit.accepted(t, t + 2 * EVENT_TIME_TOLERANCE_H)
    t += 2 * EVENT_TIME_TOLERANCE_H
    for _ in range(STALLED_STEPS - 1):
        assert not limit.accepted(t, t + short)
        t += short
    assert limit.accepted(t, t + short)


def test_without_the_count_the_tank_runs_until_its_budget(monkeypatch):
    """The rule is what stops the run: with a count that is never reached, the tank that starts on its
    condition runs on until the budget of evaluations (here a small one) ends it."""
    monkeypatch.setattr(integrate, 'STALLED_STEPS', 10**9)
    found = stopped(tank(0, cut=True), {'max_evaluations': 20_000})
    assert found.get('code') != 'chattering' and 'budget' in found['message']
