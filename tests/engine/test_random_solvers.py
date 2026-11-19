"""Small random programs with a declared solver, against the oracle (`tests/reference/`).

Each case has one to three tanks with bounds (some start empty or full), and flows that fill, drain
or pass water between them, each with a request that a stored value holds (`want`) and sometimes a
capacity. A provider's solver determines the rates of some of the flows: the flows that share a tank
with one of them are in its calculation too. Its relations are drawn from a limit on the sum of some
of its rates (a stored value of the provider) and an order between two of them; its objectives,
in written order, from the shortfall of a flow's request, a rate to make small, and a rate with a
capacity to make large. A stage of the provider may change the limit, and a stage of a tank a
request, at a whole or a half hour. Requests, capacities and limits are whole numbers and halves.

The oracle runs the same program in exact fractions. The levels of the tanks and the actual rates of
the flows at times that are no event of either run (a seventh of an hour past each half hour), and a
failure (an infeasible or an unbounded solve) with its time must agree.
"""

from __future__ import annotations

import random
from fractions import Fraction

import pytest

from napkin.engine import read, run
from napkin.program.build import (
    SINK,
    SOURCE,
    Builder,
    after,
    assign,
    constraint,
    event,
    flow,
    fmax,
    formula,
    fsum,
    given,
    local,
    maximize,
    minimize,
    named,
    q,
    solve_for,
    solver,
    start,
    this,
    value,
)
from napkin.program.config import Configuration, Request
from napkin.program.record import Key
from tests.reference.errors import NotCovered
from tests.reference.from_program import run_of, value_at

UNITS = {'h': {'time': 1}, 'L': {'volume': 1}}
HORIZON = 6
TIMES = [Fraction(k, 2) + Fraction(1, 7) for k in range(2 * HORIZON)]


def _half(rng, low, high):
    return Fraction(rng.randint(2 * low, 2 * high), 2)


def program(seed):
    """A random program with a declared solver (see the module), and the keys of the values to
    compare."""
    rng = random.Random(seed)
    b = Builder(UNITS)
    tanks = [f't{k}' for k in range(rng.randint(1, 3))]
    flows = []  # (tank, flow name)
    parts = {name: [] for name in tanks}
    for name in tanks:
        for k in range(rng.randint(1, 2)):
            kind = rng.choice(('fill', 'drain', 'pass') if len(tanks) > 1 else ('fill', 'drain'))
            capacity = q(_half(rng, 1, 4), 'L/h') if rng.random() < 0.5 else None
            want = f'want{k}'
            parts[name].append(value(want, 'L/h', _half(rng, 0, 4)))
            request = formula(getattr(this, want))
            if kind == 'fill':
                made = flow(f'f{k}', SOURCE, this.water, request=request, capacity=capacity)
            elif kind == 'drain':
                made = flow(f'f{k}', this.water, SINK, request=request, capacity=capacity)
            else:
                other = rng.choice([each for each in tanks if each != name])
                made = flow(f'f{k}', this.water, named(other).water, request=request, capacity=capacity)
            parts[name].append(made)
            flows.append((name, f'f{k}', capacity is not None))
            if rng.random() < 0.25:
                at = q(rng.choice((1, Fraction(3, 2), 2, 3)), 'h')
                parts[name].append(event(f'change{k}', after(at, assign(getattr(this, want), q(_half(rng, 0, 4), 'L/h')))))
    for name in tanks:
        cap = _half(rng, 4, 12) if rng.random() < 0.6 else None
        level = rng.choice((Fraction(0), _half(rng, 0, 8), cap if cap is not None else Fraction(3)))
        b.entity(name, value('water', 'L', min(level, cap) if cap is not None else level, lower=0, upper=cap), *parts[name])
    chosen = rng.sample(flows, rng.randint(1, min(3, len(flows))))
    names = {f'x{k}': (tank, made, capped) for k, (tank, made, capped) in enumerate(chosen)}
    solving = [given(key, getattr(named(tank), made)) for key, (tank, made, _) in names.items()]
    solving.append(given('limit', this.limit))
    solving += [solve_for(getattr(local, key).actual_rate) for key in names]
    rates = [getattr(local, key).actual_rate for key in names]
    if len(rates) > 1 and rng.random() < 0.7:
        solving.append(constraint(fsum_of(rates) <= local.limit))
    elif rng.random() < 0.5:
        solving.append(constraint(rates[0] <= local.limit))
    if len(rates) > 1 and rng.random() < 0.3:
        solving.append(constraint(rates[0] <= rates[1]))
    for _ in range(rng.randint(0, 3)):
        key = rng.choice(list(names))
        mine = getattr(local, key)
        what = rng.random()
        if what < 0.5:
            solving.append(minimize(fmax(q(0, 'L/h'), mine.request - mine.actual_rate)))
        elif what < 0.75 or not names[key][2]:
            solving.append(minimize(mine.actual_rate))
        else:
            solving.append(maximize(mine.actual_rate))
    provider = [value('limit', 'L/h', _half(rng, 1, 6)), solver('plan', *solving)]
    setup = []
    if rng.random() < 0.4:
        at = q(rng.choice((1, Fraction(3, 2), 2)), 'h')
        provider.append(event('change', after(at, assign(this.limit, q(_half(rng, 0, 6), 'L/h')))))
        setup.append(start(named('provider').change))
    b.entity('provider', *provider)
    for name in tanks:
        for part in parts[name]:
            if getattr(part, 'steps', None):
                setup.append(start(getattr(named(name), part.name)))
    b.setup(*setup)
    keys = [Key(name, ('water',)) for name in tanks]
    keys += [Key(tank, (made, 'actual_rate')) for tank, made, _ in flows]
    return b.finish(), keys


def fsum_of(rates):
    total = rates[0]
    for rate in rates[1:]:
        total = total + rate
    return total


def compare(seed):
    source, keys = program(seed)
    configuration = Configuration(Request(HORIZON))
    try:
        oracle, failed = run_of(source, configuration)
    except NotCovered:
        return
    record = run(source, configuration)
    if oracle is None:  # the setup fails
        assert record.failure is not None and record.failure.t == 0, (seed, str(failed))
        return
    if failed is not None:
        assert record.failure is not None, (seed, str(failed))
        assert record.failure.t == pytest.approx(float(oracle.view.t)), (seed, str(failed), record.failure)
        horizon = oracle.view.t
    else:
        assert record.failure is None, (seed, record.failure.detail('message'))
        horizon = Fraction(HORIZON)
    times = [time for time in TIMES if time < horizon]
    for key in keys:
        found = read(record, source, [key], [float(time) for time in times])[0].values
        for time, number in zip(times, found):
            expected = float(value_at(oracle, source, key, time))
            assert number == pytest.approx(expected, rel=1e-7, abs=1e-7), (seed, str(key), float(time))


@pytest.mark.parametrize('seed', range(100))
def test_a_small_random_program_with_a_solver_runs_as_the_oracle_does(seed):
    compare(seed)


@pytest.mark.deep
@pytest.mark.parametrize('seed', range(100, 1000))
def test_more_random_programs_with_a_solver_run_as_the_oracle_does(seed):
    compare(seed)
