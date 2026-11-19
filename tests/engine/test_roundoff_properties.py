"""Adversarial properties of roundoff at the bounds of stores, under local sharing.

Each test here gives one argument many cases from a seeded generator. The numbers are not dyadic
(thirds, sevenths, tenths and their products) and their sizes go from 1e-3 to 1e7, so the arithmetic
of doubles leaves roundoff. The oracles are independent of the engine: exact fractions of the doubles
that the file writes, and laws that follow from the model (a store on its bound is exactly on it, the
tallies together hold what came in). No expectation comes from a run of the engine.

1. A store on a bound whose flows balance but for roundoff stays exactly on it, while the rates hold
   between moments (`timeline/lines.py`, `Lines._lines`: a slope within the roundoff of its flows
   is no rate), and its outflows share what comes in by the allocation of its outflow.
2. A residual of roundoff above zero at an empty store is no rate: the store stays empty.
3. With rates that rise with time (`timeline/sparse.py`), a full or an empty store stays on its
   bound and each tally moves its exact share of the integral of its rate.

The arguments of the old engine about moves, about a stock face that runs out within the ulp of the
time, about a stock that leaves its zero face, and about the closed-form times of timers, delays and
crossings need events (S4), and come back with them.
"""

from fractions import Fraction

import numpy as np
import pytest

from napkin.engine import read, run
from napkin.program.build import (
    SOURCE,
    Builder,
    endpoint,
    flow,
    formula,
    input_,
    priority,
    proportional,
    q,
    t,
    this,
    value,
)
from napkin.program.config import Configuration, Request
from napkin.program.record import Key

EPS = np.finfo(float).eps
# The denominators of the generated numbers: none is a power of two.
DENOMINATORS = (3, 7, 10, 21, 30, 70)
UNITS = {'h': {'time': 1}, 'people': {'people': 1}}


def ratio(rng, high, low=1):
    """A number that is not dyadic: an integer from `low` to `high` over one of the denominators."""
    return float(rng.integers(low, high)) / float(rng.choice(DENOMINATORS))


def exact(x):
    """The exact value of a double."""
    return Fraction(x)


def shared_tank(demand, factors, start, top, fill_factor, order, rising=False):
    """A tank with an inflow from outside and outflows that share it, each to its own tally. Flow i
    asks `demand * factors[i]` (times 1 + t / 30 h when `rising`); the inflow asks the sum of the
    outflows, written as a sum, times `fill_factor`, and carries no more than it asks."""
    factor = 1 + t / q(30, 'h') if rising else 1
    asked = [this.demand * c * factor for c in factors]
    total = asked[0]
    for part in asked[1:]:
        total = total + part
    fill = total * fill_factor
    allocation = (
        proportional() if order == 'proportional' else priority(*(getattr(this, name) for name in order))
    )
    b = Builder(UNITS)
    b.entity(
        's',
        input_('demand', 'people/h', demand, lower=0, upper=1e12),
        value(
            'tank',
            'people',
            start,
            lower=0,
            upper=top,
            outflow=endpoint(capacity=q(1e15, 'people/h'), allocation=allocation),
        ),
        *(value(f'used{i}', 'people', 0, lower=0) for i in range(len(factors))),
        flow('fill', SOURCE, this.tank, request=formula(fill), capacity=formula(fill)),
        *(
            flow(f'out{i}', this.tank, getattr(this, f'used{i}'), request=formula(rate))
            for i, rate in enumerate(asked)
        ),
    )
    return b.finish()


def served(demand, factors, fill_factor, order):
    """The exact rate that each outflow gets: all that it asks when the inflow is at least what they
    all ask, else its share of the inflow by the order of the share."""
    asked = [exact(demand) * exact(c) for c in factors]
    supply = exact(fill_factor) * sum(asked)
    if supply >= sum(asked):
        return asked
    if order == 'proportional':
        return [supply * a / sum(asked) for a in asked]
    rates, remaining = [None] * len(asked), supply
    for name in order:
        i = int(name[3:])
        rates[i] = min(asked[i], remaining)
        remaining -= rates[i]
    return rates


def generated_tanks(rng, cases):
    for case in range(cases):
        demand = float(10 ** rng.uniform(-3, 7)) / 3
        factors = [ratio(rng, 50) for _ in range(int(rng.integers(2, 9)))]
        order = 'proportional' if case % 3 == 0 else [f'out{i}' for i in rng.permutation(len(factors))]
        yield demand, factors, order


def values(program, horizon, names, times):
    record = run(program, Configuration(Request(horizon)))
    assert record.failure is None, record.failure.detail('message')
    keys = [Key('s', (name,)) for name in names]
    return [reading.values for reading in read(record, program, keys, times)]


# ---- 1. A store on a bound stays exactly on it ---------------------------------------------------------


@pytest.mark.parametrize('seed', [3, 4])
def test_a_stock_on_its_upper_or_its_lower_bound_stays_exactly_on_it(seed):
    """Full (it starts at its upper bound) with an inflow that equals its outflows in exact
    arithmetic, the tank stays exactly full. Empty, with an inflow of 0.9 times what the outflows
    ask, it stays exactly empty, and the outflows share the inflow by the order of the share. Each
    tally moves its exact rate times the time, within 64 units of roundoff of the size of the flows,
    as a rate. The tallies together hold what came in, within the same bound."""
    rng = np.random.default_rng(seed)
    for demand, factors, order in generated_tanks(rng, 20):
        top = demand * sum(factors)
        names = ['tank', *(f'used{i}' for i in range(len(factors)))]
        for start, fill_factor in ((top, 1.0), (0.0, 0.9)):
            program = shared_tank(demand, factors, start, top, fill_factor, order)
            found = values(program, 40, names, [1.0, 40 / 3, 40.0])
            assert list(found[0]) == [start, start, start]
            rates = served(demand, factors, fill_factor, order)
            scale = 2 * exact(fill_factor) * sum(exact(demand) * exact(c) for c in factors)
            bound = 64 * exact(EPS) * scale * 40
            for i, rate in enumerate(rates):
                assert abs(exact(found[1 + i][-1]) - rate * 40) <= bound
            total = sum(exact(found[1 + i][-1]) for i in range(len(factors)))
            assert abs(total - sum(rates) * 40) <= bound


def test_a_residual_of_roundoff_above_zero_at_an_empty_stock_is_no_rate():
    """The inflow is written as 0.1 + 0.2, which in doubles is more than the two outflows 0.1 and 0.2
    together by the exact difference of the three doubles (2.8e-17); in doubles, the sum of the two
    outflows is the inflow. The empty tank stays exactly empty: a slope within the roundoff of its
    flows is no rate. Each tally holds its own rate times the time, and the three hold what came in
    within a few units of roundoff."""
    b = Builder(UNITS)
    b.entity(
        's',
        value('tank', 'people', 0, lower=0),
        value('used0', 'people', 0, lower=0),
        value('used1', 'people', 0, lower=0),
        flow('fill', SOURCE, this.tank, request=q(0.1, 'people/h') + q(0.2, 'people/h')),
        flow('out0', this.tank, this.used0, request=q(0.1, 'people/h')),
        flow('out1', this.tank, this.used1, request=q(0.2, 'people/h')),
    )
    tank, used0, used1 = (found[0] for found in values(b.finish(), 40, ['tank', 'used0', 'used1'], [40.0]))
    inflow, first, second = exact(0.1 + 0.2), exact(0.1), exact(0.2)
    assert inflow - first - second > 0
    bound = 8 * exact(EPS) * inflow * 40
    assert tank == 0.0
    assert abs(exact(used0) - first * 40) <= bound
    assert abs(exact(used1) - second * 40) <= bound
    assert abs(exact(tank) + exact(used0) + exact(used1) - inflow * 40) <= bound


# ---- 3. Rates that rise with time ----------------------------------------------------------------------

# The integral of the rate factor 1 + t / 30 h over the run of 20 h.
RISEN = Fraction(80, 3)


@pytest.mark.parametrize('seed', [5, 6])
def test_a_store_on_its_bound_with_rising_rates_moves_each_tally_its_exact_share(seed):
    """The rates rise with time, so the solver asks for the rates many times. A tank, full or empty,
    whose inflow equals its outflows in exact arithmetic stays on its bound, and so does an empty
    tank with 0.9 of what its outflows ask, whose outflows share the inflow by the order of the share.
    Each tally moves its exact share of the integral of the rate, within the tolerance of the solver."""
    rng = np.random.default_rng(seed)
    for demand, factors, order in generated_tanks(rng, 6):
        top = demand * sum(factors)
        names = ['tank', *(f'used{i}' for i in range(len(factors)))]
        for start, fill_factor in ((top, 1.0), (0.0, 1.0), (0.0, 0.9)):
            program = shared_tank(demand, factors, start, top, fill_factor, order, rising=True)
            found = [each[0] for each in values(program, 20, names, [20.0])]
            assert found[0] == pytest.approx(start, abs=1e-9 * top)
            for i, rate in enumerate(served(demand, factors, fill_factor, order)):
                assert found[1 + i] == pytest.approx(float(rate * RISEN), rel=1e-7)
