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

4. A series of moves that takes the whole of a store leaves it exactly empty, and the times of
   clocks, delays and a crossing are their exact times within the roundoff of their arithmetic.

The arguments of the old engine about a stock face that runs out within the ulp of the time and
about a stock that leaves its zero face read the faces of its continuous tier, which local sharing
and the lines replace (S2, S3); they are not ported.
"""

import math
from fractions import Fraction
from itertools import pairwise

import numpy as np
import pytest

from napkin.engine import read, run
from napkin.program import build
from napkin.program.build import (
    BOOL,
    SOURCE,
    Builder,
    after,
    assign,
    endpoint,
    event,
    flow,
    formula,
    ifelse,
    input_,
    move,
    priority,
    proportional,
    q,
    reset_when,
    t,
    this,
    value,
    when,
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


def written(x):
    """The decimal that writes a double (its `repr`): the number that a model's text holds, which the
    clock adds exactly (`moment.Clock`)."""
    return Fraction(repr(x))


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


# ---- 4. Moves and the times of events ---------------------------------------------------------------------

# How a whole is cut into the parts that a series of moves takes: (the number of moves, the part).
PARTS = {
    '/ 7': (7, lambda whole: whole / 7),
    '/ 21': (21, lambda whole: whole / 21),
    '* 0.1': (10, lambda whole: whole * 0.1),
    '* (1 / 3)': (3, lambda whole: whole * (1 / 3)),
}
TANKS = 12


def clock(name, at, *body):
    """An event that a clock starts once, at `at` hours, and whose stage runs `body` then."""
    return event(
        name,
        when(t >= q(at, 'h'), build.start(getattr(this, name)), reset=reset_when(False)),
        after(q(0, 'h'), *body),
    )


def emptied(wholes, parts, begin):
    """Tanks that a series of moves empties into their sinks: tank i holds `wholes[i]`, and at
    `begin + k / 3` h the k-th move takes its part of the whole (`whole / 7`, for example)."""
    members, moves = [], {}
    for i, (whole, part) in enumerate(zip(wholes, parts)):
        members += [
            input_(f'whole{i}', 'people', whole),
            value(f'tank{i}', 'people', whole, lower=0, scale=whole),
            value(f'sink{i}', 'people', 0, lower=0, scale=whole),
        ]
        piece = PARTS[part][1](getattr(this, f'whole{i}'))
        for k in range(PARTS[part][0]):
            moves.setdefault(k, []).append(move(piece, getattr(this, f'tank{i}'), getattr(this, f'sink{i}')))
    events = [clock(f'move{k}', begin + k / 3, *rows) for k, rows in sorted(moves.items())]
    b = Builder(UNITS)
    b.entity('s', *members, *events)
    return b.finish()


@pytest.mark.parametrize('seed', [1, 2])
def test_a_series_of_moves_that_takes_the_whole_leaves_a_store_exactly_empty(seed):
    """The parts of each whole add up to the whole in exact arithmetic, so the tank is empty after
    the last move. In doubles the parts leave a residue of a few units in the last place in most
    tanks (the generator checks it), always below the tank's absolute tolerance, 1e-10 times its
    size. The last move takes the residue too (`moment.py`): the tank is exactly zero, it never falls
    below zero, and the sink holds the whole within one rounding for each move."""
    rng = np.random.default_rng(seed)
    left, count = 0, 0
    for _ in range(4):
        wholes = [ratio(rng, 10**6) * 10 ** float(rng.integers(-6, 4)) for _ in range(TANKS)]
        parts = [str(rng.choice(list(PARTS))) for _ in range(TANKS)]
        begin = ratio(rng, 10**6) / 1000
        for whole, part in zip(wholes, parts):
            moves, one = PARTS[part]
            residue = exact(whole) - moves * exact(one(whole))
            # The argument applies: the residue is below the tolerance of the tank.
            assert abs(residue) < Fraction(1, 10**10) * exact(whole)
            left += residue != 0
        count += TANKS
        program = emptied(wholes, parts, begin)
        horizon = begin + 12
        names = [name for i in range(TANKS) for name in (f'tank{i}', f'sink{i}')]
        times = [begin + k / 3 + 1 / 6 for k in range(21)]
        found = values(program, horizon, names, times)
        for i, (whole, part) in enumerate(zip(wholes, parts)):
            moves = PARTS[part][0]
            tank, sink = found[2 * i], found[2 * i + 1]
            assert min(tank) >= 0
            assert tank[moves - 1] == 0.0
            bound = moves * EPS * exact(whole)
            assert abs(exact(sink[moves - 1]) - exact(whole)) <= bound
    assert left > count / 2


def timed(first, delay1, delay2, switch, level, rate, threshold, tick):
    """`a` at its clock `first`, `b` `delay1` after it, `c` `delay2` after that; a switch at its clock
    that starts a level rising at `rate` from `level`; `crossed` when the level reaches `threshold`,
    which starts a tally at `tick`."""
    b = Builder(UNITS)
    b.entity(
        's',
        value('on', BOOL, False),
        value('ticking', BOOL, False),
        value('level', 'people', level),
        value('after', 'people', 0),
        flow(
            'rise',
            SOURCE,
            this.level,
            request=formula(ifelse(this.on, q(rate, 'people/h'), q(0, 'people/h'))),
        ),
        flow(
            'tally',
            SOURCE,
            this.after,
            request=formula(ifelse(this.ticking, q(tick, 'people/h'), q(0, 'people/h'))),
        ),
        clock('a', first, build.start(this.b)),
        event('b', after(q(delay1, 'h'), build.start(this.c))),
        event('c', after(q(delay2, 'h'))),
        clock('switch', switch, assign(this.on, True)),
        event(
            'crossed',
            when(this.level >= q(threshold, 'people'), build.start(this.crossed), reset=reset_when(False)),
            after(q(0, 'h'), assign(this.ticking, True)),
        ),
    )
    return b.finish()


@pytest.mark.parametrize('seed', [11, 12])
def test_the_times_of_clocks_delays_and_a_crossing_are_the_exact_times_within_their_roundoff(seed):
    """The exact times: a clock at its double; a delay after the time of the stage before it, so `c`
    finishes at first + delay1 + delay2, the sum of the decimals that write them (`moment.Clock`, the
    re-audit's 04); the crossing at switch + (threshold - level) / rate. The bounds are of the
    arithmetic of doubles, far inside the crossing tolerance of 1e-8 h: the first delay's sum rounds
    once, to half an ulp, and each delay after it reads the time that it starts from as its decimal,
    within half an ulp of that time, so a chain of k delays is within k - 1/2 ulps; the crossing
    rounds the difference, the quotient and the sum, each to half a unit of roundoff of the threshold
    over the rate or of the time (`triggers.py`, the root of a line). At the horizon the level and the
    tally are their exact values within 1e-13 of them."""
    rng = np.random.default_rng(seed)
    checked = 0
    for _ in range(30):
        scale = 10 ** float(rng.integers(0, 5))
        first, switch = ratio(rng, 1000) * scale, ratio(rng, 1000) * scale
        delay1, delay2 = ratio(rng, 1000) * scale / 10, ratio(rng, 1000) * scale / 10
        rate = ratio(rng, 10**4) * 10 ** float(rng.integers(-3, 4))
        level = ratio(rng, 1000) * rate
        threshold = level + rate * ratio(rng, 1000) * scale / 10
        tick = ratio(rng, 1000)
        crossing = exact(switch) + (exact(threshold) - exact(level)) / exact(rate)
        times = {
            'a': exact(first),
            'b': written(first) + written(delay1),
            'c': written(first) + written(delay1) + written(delay2),
            'switch': exact(switch),
            'crossed': crossing,
        }
        ordered = sorted(times.values())
        if min(later - earlier for earlier, later in pairwise(ordered)) < Fraction(1, 10**6):
            continue  # two events at one moment: the cases test times, not the order of a moment
        checked += 1
        horizon = float(max(ordered)) * 1.5 + 1
        record = run(
            timed(first, delay1, delay2, switch, level, rate, threshold, tick),
            Configuration(Request(horizon)),
        )
        assert record.failure is None, record.failure
        fired = {entry.part.split('.')[1]: entry.t for entry in record.entries('fire')}
        finished = {entry.part.split('.')[1]: entry.t for entry in record.entries('finish')}
        assert fired['a'] == first and fired['switch'] == switch
        for name, delays in (('b', 1), ('c', 2)):
            ulp = exact(math.ulp(float(times[name])))
            assert abs(exact(finished[name]) - times[name]) <= (delays - Fraction(1, 2)) * ulp
        between = sum(exact(switch) < times[name] < crossing for name in ('a', 'b', 'c'))
        roundoff = exact(EPS) * (crossing + exact(threshold) / exact(rate))
        assert abs(exact(fired['crossed']) - crossing) <= (1 + between) * roundoff
        risen = exact(level) + exact(rate) * (exact(horizon) - exact(switch))
        ticked = exact(tick) * (exact(horizon) - crossing)
        ends = read(
            record,
            timed(first, delay1, delay2, switch, level, rate, threshold, tick),
            ['s.level', 's.after'],
            [horizon],
        )
        assert abs(exact(ends[0].values[0]) - risen) <= Fraction(1, 10**13) * risen
        assert abs(exact(ends[1].values[0]) - ticked) <= Fraction(1, 10**13) * ticked
    assert checked >= 25
