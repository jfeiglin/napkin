"""The balance of a stock that rests on a bound (`engine/allocation.Allocation.balance`).

A stock on a bound whose inflow equals its outflows has a rate of zero. The sum of its flows keeps
the roundoff of its terms, so the computed rate is a few units in the last place of those flows,
of either sign. On the lower bound the balance sets the rate to exactly zero and gives the
residual to a leg of the stock. This file is for the upper bound: without the balance, a residual
above zero carries the stock past its bound in an exact segment, and the run stops.

The model is a tank that starts full, with one inflow from outside and two outflows that share it.
The inflow is 1.1 times the first outflow, the second outflow is a tenth of the first, and all the
rates are constant: the three numbers do not add to zero in doubles for every demand.
"""

from types import SimpleNamespace

import numpy as np
import pytest

from napkin.engine.allocation import Allocation
from napkin.engine.runtime import simulate
from tests import build as b

HORIZON = 40
EPS = np.finfo(float).eps


def tank(demand, order='proportional'):
    text = b.system(
        b.parameter('demand', demand, 'people/h', 0, 1e9),
        b.stock('tank', 100, maximum=100),
        b.stock('used', 0, kind='tally', size=None),
        b.stock('lost', 0, kind='tally', size=None),
        b.flow('fill', b.move(None, 'tank'), 'demand * 1.1'),
        b.flow('deliver', b.move('tank', 'used'), 'demand'),
        b.flow('leak', b.move('tank', 'lost'), 'demand / 10'),
        b.share('tank', '1e12 people/h', order),
        horizon=HORIZON,
        outputs=(b.output('used', 's.used', 'people'),),
    )
    model = b.compiled(text)
    return model.resolve(next(iter(model.runs))), model.library


# The first demand leaves a residual above zero (1.1 d - d - d / 10 is 1.9e-9 in doubles): the run
# stopped with it. The others leave none, or one below zero.
@pytest.mark.parametrize('demand', [10304732.104954248, 1e7 / 3, 12345.678, 0.7, 7.0])
@pytest.mark.parametrize('order', ['proportional', ['deliver', 'leak'], ['leak', 'deliver']])
def test_a_full_tank_whose_inflow_equals_its_outflows_stays_full(demand, order):
    """The tank stays at its bound, exactly, and each outflow moves its rate times the time. What
    came in is what went out: the residual of the roundoff is in one of the outflows, and it is far
    below the last place that the closed form can tell."""
    end = simulate(*tank(demand, order)).env_at(float(HORIZON))
    assert end['s.tank'] == 100.0
    assert end['s.used'] == pytest.approx(demand * HORIZON, rel=1e-12)
    assert end['s.lost'] == pytest.approx(demand / 10 * HORIZON, rel=1e-12)
    assert end['s.used'] + end['s.lost'] == pytest.approx(demand * 1.1 * HORIZON, rel=1e-12)


# ---- the rule, on one stock with one inflow from outside and one outflow to a tally ---------------


def one_stock(kind='cumulative'):
    """What the balance reads of a system: a stock (state 0) with the flow 0 from outside and the
    flow 1 to a tally (state 1), each with a coefficient of 1."""
    quantities = {'tank': SimpleNamespace(kind='stock'), 'used': SimpleNamespace(kind=kind)}
    return SimpleNamespace(
        state_ids=('tank', 'used'),
        index={'tank': 0, 'used': 1},
        quantities=quantities,
        lower=np.array([0.0, 0.0]),
        upper=np.array([100.0, np.inf]),
        atol=np.array([1e-8, 1e-8]),
        legs={'tank': ([(1, 'used')], [(0, None)], [0]), 'used': ([], [(1, 'tank')], [])},
        abs_flow_matrix=np.array([[1.0, 1.0], [0.0, 1.0]]),
    )


def balanced(residual, *, level=100.0, active=((0, 'max'),), rate=1e7, kind='cumulative'):
    """The rates of the two states after the balance, from a tank at `level` whose computed rate is
    `residual` while its flows move `rate`."""
    base = np.zeros(2)
    requested = np.array([rate, rate])
    derivative = np.array([residual, rate])
    state = np.array([level, 5.0])
    Allocation(one_stock(kind)).balance(state, base, requested, derivative, set(), set(active), set())
    return derivative.tolist()


@pytest.mark.parametrize('sign', [1, -1])
def test_a_residual_of_roundoff_on_the_upper_bound_goes_to_a_leg_of_the_stock(sign):
    """The flows are 1e7 in and 1e7 out: their size is 2e7, and one unit in its last place is about
    4e-9. A residual of that size is no rate: the tank gets exactly zero, and the tally of the
    outflow takes the residual, so the two rates add to what they added to before."""
    residual = sign * 2e7 * EPS
    assert balanced(residual) == [0.0, 1e7 + residual]
    # The limit is 32 units in the last place of the size of the flows.
    assert balanced(sign * 31 * 2e7 * EPS)[0] == 0.0
    assert balanced(sign * 33 * 2e7 * EPS) == [sign * 33 * 2e7 * EPS, 1e7]


def test_a_rate_that_is_more_than_roundoff_stays_a_rate():
    """An excess that the flows can tell (one part in a million of them) is no residual: the balance
    leaves it, and the bound allocation and the checks of the state answer for it. So does a
    residual of a tank that is not exactly on its bound, or whose bound is not active."""
    assert balanced(10.0) == [10.0, 1e7]
    small = 2e7 * EPS
    assert balanced(small, level=99.5) == [small, 1e7]
    assert balanced(small, level=100.0 - 1e-9) == [small, 1e7]
    assert balanced(small, active=()) == [small, 1e7]
    assert balanced(small, active=((0, 'min'),)) == [small, 1e7]


def test_a_residual_below_zero_does_not_make_a_tally_fall():
    """A residual below zero takes from the leg that it goes to. A tally never falls: when the
    outflow moves nothing that could absorb it, the tally is no partner, and the inflow from
    outside is the leg, so the tank gets zero and no other rate changes."""
    residual = -2e7 * EPS
    base = np.zeros(2)
    requested = np.array([1e7, 1e7])
    derivative = np.array([residual, 0.0])  # the tally has no rate to take from
    state = np.array([100.0, 5.0])
    Allocation(one_stock()).balance(state, base, requested, derivative, set(), {(0, 'max')}, set())
    assert derivative.tolist() == [0.0, 0.0]
    # A partner that is no tally can fall: it takes the residual.
    assert balanced(residual, kind='stock') == [0.0, 1e7 + residual]
