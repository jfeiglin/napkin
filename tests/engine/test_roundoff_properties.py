"""Adversarial properties of the roundoff arguments at bounds, and of the closed-form event times.

docs/engine.md, "Roundoff at bounds: the arguments", states five arguments. Each test here gives
one of them many cases from a seeded generator. The numbers are not dyadic (thirds, sevenths,
tenths and their products), their sizes go from 1e-6 to 1e9, and the times are far from zero, so
the arithmetic of doubles leaves roundoff. The oracles are independent of the engine: exact
fractions of the doubles that the file writes, and laws that follow from the model (what a closed
model holds, a stock on its bound is exactly on it, a tally never falls). No expectation comes from
a run of the engine.

1. A transfer that empties a stock leaves no residue (`timeline/run.py`, the moves of a step).
2. The balance of a stock on a bound onto one of its legs (`Allocation.balance`).
3. The short path of the closed form gives what the closed form gives (`Allocation.served_in_full`).
4. A stock face whose remainder runs out within the ulp of the time (`bounds.rounded_faces`).
5. A stock that leaves its zero face, probed one ulp above zero (`bounds.depart_faces`).

The last test computes the times of timers, delays and one crossing at a constant rate with exact
fractions, and compares them with the trace.
"""

import math
from fractions import Fraction
from itertools import pairwise

import numpy as np
import pytest

from napkin.engine.allocation import Allocation
from napkin.engine.runtime import SimulationError, simulate
from tests import build as b

EPS = np.finfo(float).eps
# The denominators of the generated numbers: none is a power of two.
DENOMINATORS = (3, 7, 10, 21, 30, 70)


def ratio(rng, high, low=1):
    """A number that is not dyadic: an integer from `low` to `high` over one of the denominators."""
    return float(rng.integers(low, high)) / float(rng.choice(DENOMINATORS))


def exact(x):
    """The exact value of a double."""
    return Fraction(x)


def model_of(text):
    model = b.compiled(text)
    return model.resolve(next(iter(model.runs))), model.library


# ---- 1. A transfer that empties a stock leaves no residue -----------------------------------------

# The parts of a whole that a move takes, with the number of moves that take all of it in exact
# arithmetic, and the double that plain arithmetic gives for one part.
PARTS = {
    '/ 3': (3, lambda w: w / 3),
    '/ 7': (7, lambda w: w / 7),
    '/ 10': (10, lambda w: w / 10),
    '/ 21': (21, lambda w: w / 21),
    '/ 30': (30, lambda w: w / 30),
    '* 0.1': (10, lambda w: w * 0.1),
    '* (1 / 3)': (3, lambda w: w * (1 / 3)),
}
TANKS = 12


def emptied(wholes, parts, start):
    """Tanks that a series of moves empties into their sinks: tank i holds `wholes[i]`, and at
    `start + k / 3` h the k-th move takes its part of the whole (`whole / 7`, for example)."""
    members, lines = [], {}
    for i, (whole, part) in enumerate(zip(wholes, parts)):
        members += [
            b.parameter(f'whole{i}', whole, 'people'),
            b.stock(f'tank{i}', f'whole{i}', size=whole),
            b.stock(f'sink{i}', 0, size=whole),
        ]
        for k in range(PARTS[part][0]):
            lines.setdefault(k, []).append(f'move whole{i} {part} from tank{i} to sink{i}')
    events = [b.once_at(f'move{k}', f'{start + k / 3!r} h', *rows) for k, rows in sorted(lines.items())]
    return b.system(*members, *events, horizon=start + 12)


@pytest.mark.parametrize('seed', [1, 2])
def test_a_series_of_moves_that_takes_the_whole_leaves_a_stock_exactly_empty(seed):
    """The parts of each whole add up to the whole in exact arithmetic, so the tank is empty after
    the last move. In doubles the parts leave a residue of a few units in the last place in most
    tanks (the generator checks it), always below the tank's absolute tolerance, 1e-10 times its
    size. The last move takes the residue too: the tank is exactly zero, it never falls below zero,
    and the sink holds the whole within one rounding for each move."""
    rng = np.random.default_rng(seed)
    left, count = 0, 0
    for _ in range(10):
        wholes = [ratio(rng, 10**6) * 10 ** float(rng.integers(-6, 4)) for _ in range(TANKS)]
        parts = [str(rng.choice(list(PARTS))) for _ in range(TANKS)]
        start = ratio(rng, 10**6)
        for whole, part in zip(wholes, parts):
            moves, one = PARTS[part]
            residue = exact(whole) - moves * exact(one(whole))
            # The argument applies: the residue is below the tolerance of the tank.
            assert abs(residue) < Fraction(1, 10**10) * exact(whole)
            left += residue != 0
        count += TANKS
        trajectory = simulate(*model_of(emptied(wholes, parts, start)))
        for i, (whole, part) in enumerate(zip(wholes, parts)):
            moves = PARTS[part][0]
            bound = moves * EPS * exact(whole)
            for k in range(moves):
                # Between the moves k and k + 1, the tank holds (moves - k - 1) parts.
                held = trajectory.env_at(start + k / 3 + 1 / 6)[f's.tank{i}']
                assert held >= 0
                assert abs(exact(held) - exact(whole) * (moves - k - 1) / moves) <= bound
            end = trajectory.env_at(start + 12)
            assert end[f's.tank{i}'] == 0.0
            assert abs(exact(end[f's.sink{i}']) - exact(whole)) <= bound
    # The cases provoke the argument: plain arithmetic leaves a residue in most tanks.
    assert left >= count / 2


# ---- 2. The balance of a stock on a bound -----------------------------------------------------------


def shared_tank(demand, factors, start, top, fill_factor, order, rate='1'):
    """A tank with an inflow from outside and outflows that share it, each to its own tally. Flow i
    asks `demand * factors[i] * rate`; the inflow is the sum of the outflows, written as a sum,
    times `fill_factor`."""
    outflows = [
        b.flow(f'out{i}', b.move('tank', f'used{i}'), f'demand * {c!r} * {rate}')
        for i, c in enumerate(factors)
    ]
    fill = '(' + ' + '.join(f'demand * {c!r} * {rate}' for c in factors) + f') * {fill_factor!r}'
    return b.system(
        b.parameter('demand', demand, 'people/h', 0, 1e12),
        b.stock('tank', start, maximum=top, size=top),
        *(b.stock(f'used{i}', 0, kind='tally', size=None) for i in range(len(factors))),
        b.flow('fill', b.move(None, 'tank'), fill),
        *outflows,
        b.share('tank', '1e15 people/h', order),
        horizon=40,
        outputs=(b.output('used', 's.used0', 'people'),),
    )


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


@pytest.mark.parametrize('seed', [3, 4])
def test_a_stock_on_its_upper_or_its_lower_bound_stays_exactly_on_it(seed):
    """Full (it starts at its upper bound) with an inflow that equals its outflows in exact
    arithmetic, the tank stays exactly full. Empty, with an inflow of 0.9 times what the outflows
    ask, it stays exactly empty, and the outflows share the inflow by the order of the share. Each
    tally moves its exact rate times the time, within the residual that the balance may give it:
    32 units of roundoff of the size of the flows, as a rate. The tallies together hold what came
    in, within the same bound."""
    rng = np.random.default_rng(seed)
    for demand, factors, order in generated_tanks(rng, 20):
        top = demand * sum(factors)
        for start, fill_factor in ((top, 1.0), (0.0, 0.9)):
            trajectory = simulate(*model_of(shared_tank(demand, factors, start, top, fill_factor, order)))
            for at in (1.0, 40 / 3, 40.0):
                assert trajectory.env_at(at)['s.tank'] == start
            end = trajectory.env_at(40.0)
            rates = served(demand, factors, fill_factor, order)
            scale = 2 * exact(fill_factor) * sum(exact(demand) * exact(c) for c in factors)
            bound = 64 * exact(EPS) * scale * 40
            for i, rate in enumerate(rates):
                assert abs(exact(end[f's.used{i}']) - rate * 40) <= bound
            total = sum(exact(end[f's.used{i}']) for i in range(len(factors)))
            assert abs(total - sum(rates) * 40) <= bound


def test_an_empty_stock_with_an_inflow_above_its_outflows_by_roundoff_rises_by_that():
    """A residual above zero on the lower bound carries no stock past its bound, and the balance
    leaves it: it is a rate. The inflow is written as 0.1 + 0.2, which in doubles is more than the
    two outflows 0.1 and 0.2 together, by the exact difference of the three doubles (2.8e-17). The
    empty tank gets all that it gives and rises by that difference times the time; each tally
    holds its own rate times the time; and the three hold what came in."""
    text = b.system(
        b.stock('tank', 0, size=1),
        b.stock('used0', 0, kind='tally', size=1),
        b.stock('used1', 0, kind='tally', size=1),
        b.flow('fill', b.move(None, 'tank'), '0.1 people/h + 0.2 people/h'),
        b.flow('out0', b.move('tank', 'used0'), '0.1 people/h'),
        b.flow('out1', b.move('tank', 'used1'), '0.2 people/h'),
        b.share('tank', '1e15 people/h'),
        horizon=40,
    )
    end = simulate(*model_of(text)).env_at(40.0)
    inflow, first, second = exact(0.1 + 0.2), exact(0.1), exact(0.2)
    excess = inflow - first - second
    assert excess > 0
    # Each product and each sum of the run rounds once: a few units of roundoff of what came in.
    bound = 8 * exact(EPS) * inflow * 40
    assert end['s.tank'] > 0
    assert abs(exact(end['s.tank']) - excess * 40) <= bound
    assert abs(exact(end['s.used0']) - first * 40) <= bound
    assert abs(exact(end['s.used1']) - second * 40) <= bound
    total = exact(end['s.tank']) + exact(end['s.used0']) + exact(end['s.used1'])
    assert abs(total - inflow * 40) <= bound


# ---- 3. The short path of the closed form -----------------------------------------------------------


@pytest.fixture
def claims(monkeypatch):
    """The closed form with all of its work for each call, and what the short path said of the same
    call: [(the claim, whether the closed form gave the request back in each bit)]."""
    quick, closed, found, said = Allocation.served_in_full, Allocation.closed_form, [], []

    def recorded(self, *args):
        said.append(quick(self, *args))
        return False

    def full(self, a, bound, requested, adjustable):
        del said[:]
        out = closed(self, a, bound, requested, adjustable)
        if out is not None and said:
            found.append((said[0], out.tobytes() == requested.tobytes()))
        return out

    monkeypatch.setattr(Allocation, 'served_in_full', recorded)
    monkeypatch.setattr(Allocation, 'closed_form', full)
    return found


# The integral of the rate factor 1 + t / 30 h over the run of 20 h.
RISING = '(1 + t / 30 h)'
RISEN = Fraction(80, 3)


@pytest.mark.parametrize('seed', [5, 6])
def test_each_claim_of_a_full_service_is_what_the_closed_form_gives(seed, claims):
    """The rates rise with time, so the solver asks for the field many times. A tank, full or
    empty, whose inflow equals its outflows in exact arithmetic comes to the closed form whenever
    roundoff leaves an excess, and its units are served in full or cut by a few units in the last
    place: the hardest calls for the short path. An empty tank with 0.9 of what its outflows ask
    cuts a unit at each call. Whenever the short path says that every unit is served in full, the
    closed form gives the request back in each bit. Each tally moves its exact share of the
    integral of the rate, within the tolerance of the solver."""
    rng = np.random.default_rng(seed)
    for demand, factors, order in generated_tanks(rng, 12):
        top = demand * sum(factors)
        for start, fill_factor in ((top, 1.0), (0.0, 1.0), (0.0, 0.9)):
            text = shared_tank(demand, factors, start, top, fill_factor, order, rate=RISING)
            text = b.with_horizon(text, 20)
            end = simulate(*model_of(text)).env_at(20.0)
            assert end['s.tank'] == pytest.approx(start, abs=1e-9 * top)
            for i, rate in enumerate(served(demand, factors, fill_factor, order)):
                assert end[f's.used{i}'] == pytest.approx(float(rate * RISEN), rel=1e-7)
    assert [(claim, same) for claim, same in claims if claim and not same] == []
    # The cases have calls of both kinds.
    assert sum(claim for claim, _ in claims) > 10
    assert sum(not same for _, same in claims) > 100


# ---- 4. A stock face that runs out within the ulp of the time --------------------------------------


def draining(start, held, supply, drain, horizon, warehouse):
    """A closed model: at `start` a warehouse starts to supply a stock at `supply` and moves `held`
    into it. The stock drains to a store at `drain`, more than the supply, while it holds anything,
    and then passes the supply on. The event `empty` happens when the stock is empty."""
    return b.system(
        b.named('state', 'off', 'on'),
        b.stock('warehouse', warehouse, size=warehouse),
        b.stock('stock', 0, size=drain),
        b.stock('served', 0, size=warehouse),
        b.flow('supply', b.move('warehouse', 'stock'), f'{supply!r} people/h if state is "on" else 0'),
        b.flow(
            'serve',
            b.move('stock', 'served'),
            f'{drain!r} people/h if stock > 0 else {supply!r} people/h if state is "on" else 0',
        ),
        b.event(
            'begin',
            f'state is "off" and t >= {start!r} h',
            'state = "on"',
            f'move {held!r} people from warehouse to stock',
            once=False,
        ),
        b.event('empty', 'stock <= 0 and state is "on"'),
        horizon=horizon,
    )


@pytest.mark.parametrize('seed', [7, 8])
def test_a_stock_that_runs_out_within_the_ulp_of_the_time_reaches_zero_exactly(seed):
    """The stock runs out at start + held / (drain - supply). In half of the cases that is less than
    one ulp of the start after it: no later double is the time of the depletion. In the others the
    time of the depletion rounds, and the stock can keep a remainder that runs out within the ulp
    of the time. Either way the stock reaches zero exactly, every segment takes time, `empty`
    happens at the exact time within 4 units of roundoff of the time, the model holds what it held,
    and the store holds what came into the stock."""
    rng = np.random.default_rng(seed)
    for case in range(16):
        start = ratio(rng, 10**6)
        drain = ratio(rng, 10**4) * 10 ** float(rng.integers(-3, 4))
        supply = drain * float(rng.integers(1, 9)) / 10
        if case % 2:
            held = (drain - supply) * math.ulp(start) * float(rng.uniform(0.01, 1))
        else:
            held = (drain - supply) * ratio(rng, 1000)
        horizon = start + 2 * held / (drain - supply) + 1
        warehouse = 2 * supply * horizon + held
        trajectory = simulate(*model_of(draining(start, held, supply, drain, horizon, warehouse)))
        assert all(segment.start < segment.end for segment in trajectory._segments)
        runs_out = exact(start) + exact(held) / (exact(drain) - exact(supply))
        times = [entry['t'] for entry in trajectory.trace if entry['rule'] == 's.empty']
        assert len(times) == 1
        assert abs(exact(times[0]) - runs_out) <= 4 * exact(EPS) * runs_out
        end = trajectory.env_at(horizon)
        assert end['s.stock'] == 0.0
        # The store takes up to `drain` an hour, and each time of the run (the start, the depletion,
        # the horizon) is a double within a few units of roundoff of the time.
        stored = exact(held) + exact(supply) * (exact(horizon) - exact(start))
        bound = 8 * exact(EPS) * (stored + exact(drain) * exact(horizon))
        assert abs(exact(end['s.served']) - stored) <= bound
        last = 0.0
        for at in (start, float(runs_out), (float(runs_out) + horizon) / 2, horizon):
            now = trajectory.env_at(at)
            assert now['s.stock'] >= 0 and now['s.served'] >= last
            last = now['s.served']
            total = exact(now['s.warehouse']) + exact(now['s.stock']) + exact(now['s.served'])
            assert abs(total - exact(warehouse)) <= 8 * exact(EPS) * exact(warehouse)


# ---- 5. A stock that leaves its zero face -----------------------------------------------------------


def lifted(start, supply, drain, horizon, warehouse):
    """A closed model: an empty stock that a warehouse supplies at `supply` from `start`, and that
    drains at `drain` while it holds anything."""
    return b.system(
        b.named('state', 'off', 'on'),
        b.stock('warehouse', warehouse, size=warehouse),
        b.stock('stock', 0, size=supply),
        b.stock('served', 0, size=warehouse),
        b.flow('supply', b.move('warehouse', 'stock'), f'{supply!r} people/h if state is "on" else 0'),
        b.flow('serve', b.move('stock', 'served'), f'{drain!r} people/h if stock > 0 else 0'),
        b.event('begin', f'state is "off" and t >= {start!r} h', 'state = "on"', once=False),
        b.event('empty', 'stock <= 0 and state is "on"'),
        horizon=horizon,
    )


def drains(rng, supply, kind):
    """A drain close to the supply: a ratio of it, one ulp away from it, equal to it, or a part
    in n away from it."""
    if kind == 0:
        return supply * ratio(rng, 30)
    if kind == 1:
        return math.nextafter(supply, math.inf if rng.random() < 0.5 else 0.0)
    if kind == 2:
        return supply
    n = int(rng.integers(2, 10**6))
    return supply * (n + (1 if rng.random() < 0.5 else -1)) / n


@pytest.mark.parametrize('seed', [9, 10])
def test_a_stock_leaves_its_zero_face_when_the_field_above_it_points_up(seed):
    """At zero the stock gets the supply and gives nothing, so its rate there is the supply. Just
    above zero its rate is the supply less the drain. The stock leaves zero when that is above zero
    in exact arithmetic, and then holds (supply - drain) times the time; the model holds what it
    held. Else the field above zero does not point up, and the run stops: the face would chatter.
    The drains are one ulp from the supply, equal to it, or a part in a million from it."""
    rng = np.random.default_rng(seed)
    lifts = 0
    for case in range(24):
        start = ratio(rng, 10**6)
        supply = ratio(rng, 10**4) * 10 ** float(rng.integers(-3, 6))
        drain = drains(rng, supply, case % 4)
        horizon = start + ratio(rng, 100)
        warehouse = 2 * supply * horizon
        text = lifted(start, supply, drain, horizon, warehouse)
        if exact(supply) <= exact(drain):
            with pytest.raises(SimulationError, match='chattering'):
                simulate(*model_of(text))
            continue
        lifts += 1
        trajectory = simulate(*model_of(text))
        for at in ((start + horizon) / 2, horizon):
            now = trajectory.env_at(at)
            elapsed = exact(at) - exact(start)
            bound = 4 * exact(EPS) * exact(supply) * exact(at)
            assert abs(exact(now['s.stock']) - (exact(supply) - exact(drain)) * elapsed) <= bound
            assert abs(exact(now['s.served']) - exact(drain) * elapsed) <= bound
            total = exact(now['s.warehouse']) + exact(now['s.stock']) + exact(now['s.served'])
            assert abs(total - exact(warehouse)) <= 8 * exact(EPS) * exact(warehouse)
    assert 0 < lifts < 24


# ---- The closed-form times of events ----------------------------------------------------------------


def timed(first, delay1, delay2, switch, level, rate, threshold, tick, horizon):
    """Timers, delays and one crossing at a constant rate. `a` happens at `first`; `b` happens
    `delay1` after it, and `c` `delay2` after `b`. At `switch` a level of `level` starts to rise at
    `rate`; `crossed` happens when it reaches `threshold`, and a tally then rises at `tick`."""
    return b.system(
        b.named('state', 'off', 'on'),
        b.stock('level', level, size=threshold),
        b.stock('after', 0, kind='tally', size=tick * horizon),
        b.flow('rise', b.move(None, 'level'), f'{rate!r} people/h if state is "on" else 0'),
        b.flow('tick', b.move(None, 'after'), f'{tick!r} people/h if count(crossed) > 0 else 0'),
        b.event('a', f't >= {first!r} h'),
        b.event('b', 'count(a) > 0', after=f'{delay1!r} h'),
        b.event('c', 'count(b.done) > 0', after=f'{delay2!r} h'),
        b.event('switch', f't >= {switch!r} h', 'state = "on"'),
        b.event('crossed', f'level >= {threshold!r} people'),
        horizon=horizon,
    )


@pytest.mark.parametrize('seed', [11, 12])
def test_the_times_of_timers_delays_and_a_crossing_are_the_exact_times_within_their_roundoff(seed):
    """The exact times: a timer at its double; a delay after the time of the event before it, so
    `c` at first + delay1 + delay2; the crossing at switch + (threshold - level) / rate. The bounds
    are of the arithmetic of doubles, far inside the event time tolerance of 1e-8 h. Each sum of
    a delay rounds once, to half an ulp of a time no later than the event, so a chain of k delays
    is within k / 2 ulps. The crossing rounds the difference, the quotient and the sum, each to half
    a unit of roundoff of the threshold over the rate or of the time; each moment between the
    switch and the crossing ends a segment, and the level and the time there round once more. At the
    horizon the level and the tally are their exact values within 1e-13 of them."""
    rng = np.random.default_rng(seed)
    checked = 0
    for _ in range(80):
        scale = 10 ** float(rng.integers(0, 5))
        first, switch = ratio(rng, 1000) * scale, ratio(rng, 1000) * scale
        delay1, delay2 = ratio(rng, 1000) * scale / 10, ratio(rng, 1000) * scale / 10
        rate = ratio(rng, 10**4) * 10 ** float(rng.integers(-3, 4))
        level = ratio(rng, 1000) * rate
        threshold = level + rate * ratio(rng, 1000) * scale / 10
        tick = ratio(rng, 1000)
        crossing = exact(switch) + (exact(threshold) - exact(level)) / exact(rate)
        times = {
            's.a': exact(first),
            's.b': exact(first) + exact(delay1),
            's.c': exact(first) + exact(delay1) + exact(delay2),
            's.switch': exact(switch),
            's.crossed': crossing,
        }
        ordered = sorted(times.values())
        if min(later - earlier for earlier, later in pairwise(ordered)) < Fraction(1, 10**6):
            continue  # two events at one moment: the cases test times, not the order of a moment
        checked += 1
        horizon = float(max(ordered)) * 1.5 + 1
        trajectory = simulate(
            *model_of(timed(first, delay1, delay2, switch, level, rate, threshold, tick, horizon))
        )
        fired = {entry['rule']: entry['t'] for entry in trajectory.trace if entry['outcome']}
        assert fired['s.a'] == first and fired['s.switch'] == switch
        for name, delays in (('s.b', 1), ('s.c', 2)):
            ulp = exact(math.ulp(float(times[name])))
            assert abs(exact(fired[name]) - times[name]) <= Fraction(delays, 2) * ulp
        between = sum(exact(switch) < times[name] < crossing for name in ('s.a', 's.b', 's.c'))
        roundoff = exact(EPS) * (crossing + exact(threshold) / exact(rate))
        assert abs(exact(fired['s.crossed']) - crossing) <= (1 + between) * roundoff
        end = trajectory.env_at(horizon)
        risen = exact(level) + exact(rate) * (exact(horizon) - exact(switch))
        ticked = exact(tick) * (exact(horizon) - crossing)
        assert abs(exact(end['s.level']) - risen) <= Fraction(1, 10**13) * risen
        assert abs(exact(end['s.after']) - ticked) <= Fraction(1, 10**13) * ticked
    assert checked >= 70
