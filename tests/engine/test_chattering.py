"""A run whose rates switch back and forth at a condition stops with `chattering`
(`napkin/engine/timeline/sparse.py`, `Sparse._failed` and `Sparse._count`; for a component of the
continuous engine, `napkin/engine/continuous/integrate.py`, `Limit.accepted`).

The model: a tank whose two outflows are cut off when it is empty (`... if tank > 0 else 0`), with
an inflow that is less than what they ask. Above zero the tank falls; at zero the outflows stop and
the tank rises. The oracles: the closed form of the time at which the tank empties, and the closed
form of the same tank without the condition, whose outflows get what comes in when it is empty.
"""

import pytest

from napkin.engine import read, run
from napkin.engine.continuous import integrate
from napkin.engine.continuous.integrate import STALLED_STEPS, Limit
from napkin.engine.timeline import sparse
from napkin.program.build import SOURCE, Builder, endpoint, flow, formula, ifelse, input_, q, this, value
from napkin.program.config import Configuration, Numerics, Request
from napkin.program.record import Key

DEMAND = 1e5  # people/h
SHARES = (1 / 3, 2 / 7)
FILL = 0.9  # the inflow, as a part of what the outflows ask
HORIZON = 40.0
UNITS = {'h': {'time': 1}, 'people': {'people': 1}}


def tank(level, cut):
    """The program of a tank that starts at `level`; with `cut`, each outflow is cut off when the
    tank is empty. The inflow carries no more than it asks."""
    asked = [this.demand * share for share in SHARES]
    fill = (asked[0] + asked[1]) * FILL
    parts = [
        input_('demand', 'people/h', DEMAND, lower=0, upper=1e12),
        value('tank', 'people', level, lower=0, outflow=endpoint(capacity=q(1e15, 'people/h'))),
        *(value(f'used{k}', 'people', 0, lower=0) for k in range(len(SHARES))),
        flow('fill', SOURCE, this.tank, request=formula(fill), capacity=formula(fill)),
    ]
    for k, rate in enumerate(asked):
        request = formula(ifelse(this.tank > q(0, 'people'), rate, q(0, 'people/h'))) if cut else rate
        parts.append(flow(f'out{k}', this.tank, getattr(this, f'used{k}'), request=request))
    b = Builder(UNITS)
    b.entity('s', *parts)
    return b.finish()


def stopped(program, numerics=None):
    """The failure of the run of `program`, which must stop."""
    configuration = Configuration(Request(HORIZON), numerics=numerics or Numerics())
    record = run(program, configuration)
    assert record.failure is not None
    return record.failure


def test_a_tank_that_starts_empty_on_its_condition_stops_with_chattering():
    """The tank starts at zero, at the switch of its condition: the run stops with `chattering`,
    and names the tank and its two outflows."""
    failure = stopped(tank(0, cut=True))
    message = failure.detail('message')
    assert 'chattering' in message and 's.tank' in message
    assert 's.out0' in message and 's.out1' in message
    assert 0 <= failure.t < HORIZON


def test_a_tank_that_empties_stops_with_chattering_at_the_time_that_it_empties():
    """The tank empties at level / (what goes out - what comes in); there its condition switches
    back and forth, and the run stops there with `chattering`."""
    level = 5e4
    asked = DEMAND * sum(SHARES)
    empty = level / (asked * (1 - FILL))
    # The hand-built tank has no random seed. Its exact emptying time is 105/13 hours.
    assert empty == pytest.approx(105 / 13)
    failure = stopped(tank(level, cut=True))
    message = failure.detail('message')
    assert all(name in message for name in ('chattering', 's.tank', 's.out0', 's.out1'))
    assert failure.t == pytest.approx(105 / 13, rel=1e-9)


def test_the_tank_without_the_condition_gives_its_outflows_what_comes_in_when_it_is_empty():
    """The advice of the diagnostic: without the condition, the tank empties at the same time, and
    after it each outflow gets its share of the inflow."""
    level = 5e4
    asked = DEMAND * sum(SHARES)
    empty = level / (asked * (1 - FILL))
    program = tank(level, cut=False)
    record = run(program, Configuration(Request(HORIZON)))
    assert record.failure is None
    keys = [Key('s', ('tank',)), *(Key('s', (f'used{k}',)) for k in range(len(SHARES)))]
    end = [reading.values[0] for reading in read(record, program, keys, [HORIZON])]
    assert end[0] == pytest.approx(0.0, abs=1e-6)
    for k, share in enumerate(SHARES):
        expected = DEMAND * share * empty + DEMAND * share * FILL * (HORIZON - empty)
        assert end[1 + k] == pytest.approx(expected, rel=1e-9)


def test_a_run_of_steps_too_short_to_tell_apart_stops_the_run_as_stalled(monkeypatch):
    """Three accepted steps shorter than the crossing tolerance still name a stalled solver.
    The emptying tank has a located physical switch, so it no longer takes short steps to find it.
    Give Radau a known short first and maximum step to exercise the independent stall diagnostic."""
    monkeypatch.setattr(integrate, 'STALLED_STEPS', 3)
    short = Numerics().crossing / 2
    radau = sparse.Radau

    def short_steps(*args, **kwargs):
        return radau(*args, first_step=short, max_step=short, **kwargs)

    monkeypatch.setattr(sparse, 'Radau', short_steps)
    failure = stopped(tank(5e4, cut=True))
    message = failure.detail('message')
    assert 'for 3 steps in a row' in message and 'chattering' in message
    assert 's.tank' in message and 's.out0' in message and 's.out1' in message
    assert f't = {3 * short:g} h' in message


def test_a_segment_is_stalled_after_so_many_accepted_steps_in_a_row_that_are_too_short():
    moment = Numerics().crossing
    short = moment / 2
    limit = Limit(1.0, 8.0, moment)
    t = 3.0
    for _ in range(STALLED_STEPS - 1):
        assert not limit.accepted(t, t + short)
        t += short
    assert limit.accepted(t, t + short)
    assert limit.brief_from == 3.0
    # A longer step starts the count again.
    limit = Limit(1.0, 8.0, moment)
    for _ in range(STALLED_STEPS - 1):
        limit.accepted(t, t + short)
        t += short
    assert not limit.accepted(t, t + 2 * moment)
    t += 2 * moment
    for _ in range(STALLED_STEPS - 1):
        assert not limit.accepted(t, t + short)
        t += short
    assert limit.accepted(t, t + short)
