"""The trail of a value is the same whatever else its report holds, and in whatever order (the readiness
audit of `8b3a01a`, row 16; `report._Trail`).

The rule, on random models whose formulas nest and depend on the time: a branch on `t`, on a stored
value that a stage changes, on a yes/no that a stage turns, on `since` and on `elapsed`, each over
formulas before it. A report of a random set of paths in a random order, at random times, with random
lags, gives each path the trail that a report of that path alone gives, at the same times with the
same lag. The expected trail is the one of the path alone: no other value of the report takes part.

Then the case that the property found, by hand: `outer` reads `mid` before 2 h and `other` after, and
`mid` reads `a` before 2 h and `src` after. Reported at 1 h and 3 h, `outer` reads `mid` only at 1 h,
where `mid` reads `a`, so `src` is not exercised for `outer`, whether `mid` is reported before it, after
it or not at all.
"""

from __future__ import annotations

import random

import pytest

from napkin.engine.report import Lag, report
from napkin.engine.timeline import run
from napkin.program.build import (
    BOOL,
    SOURCE,
    Builder,
    add,
    after,
    assign,
    elapsed,
    event,
    flow,
    fmax,
    fmin,
    formula,
    ifelse,
    named,
    q,
    rating,
    since,
    start,
    status,
    t,
    this,
    value,
)
from napkin.program.config import Configuration, Request

UNITS = {'h': {'time': 1}, 'L': {'volume': 1}}
HORIZON = 4
FORMULAS = 5
REPORTS = 6  # the random reports of each model


def condition(rng, k):
    """A random yes/no over the time, the stored values, the yes/nos, `since`, `elapsed` and the
    formulas before the k-th."""
    kind = rng.choice(['time', 'stored', 'flag', 'since', 'elapsed', 'formula'] if k else ['time', 'stored'])
    if kind == 'time':
        return t < q(rng.choice([0.5, 1, 1.5, 2, 2.5, 3]), 'h')
    if kind == 'stored':
        return getattr(this, f'n{rng.randrange(3)}') > q(rng.randint(0, 9), 'L')
    if kind == 'flag':
        return getattr(this, f'b{rng.randrange(2)}')
    if kind == 'since':
        return since(this.tick) >= q(rng.choice([0.5, 1, 2, 3]), 'h')
    if kind == 'elapsed':
        return elapsed(this.n0) >= q(rng.choice([0.5, 1, 2]), 'h')
    return getattr(this, f'f{rng.randrange(k)}') > q(rng.randint(0, 9), 'L')


def number(rng, k, depth):
    """A random number over the stored numbers, the tally and the formulas before the k-th, with
    choices on random conditions, sums, `min` and `max`."""
    if depth == 0 or rng.random() < 0.25:
        if k and rng.random() < 0.6:  # mostly a formula before it, so that the formulas nest
            return getattr(this, f'f{rng.randrange(k)}')
        name = rng.choice(['n0', 'n1', 'n2', 'tally'])
        return getattr(this, name) if rng.random() < 0.9 else q(rng.randint(0, 9), 'L')
    op = rng.choice(['if', 'if', 'add', 'min', 'max'])
    if op == 'if':
        return ifelse(condition(rng, k), number(rng, k, depth - 1), number(rng, k, depth - 1))
    left, right = number(rng, k, depth - 1), number(rng, k, depth - 1)
    return {'add': lambda: left + right, 'min': lambda: fmin(left, right), 'max': lambda: fmax(left, right)}[
        op
    ]()


def model(rng):
    """A member with three stored numbers, two yes/nos, a tally that fills at 1 L/h, a tick that
    starts at 0 h whose two stages change a number, turn a yes/no and add to another number at random
    times, nested formulas `f0`..`f4` and a status display of three cases."""
    b = Builder(UNITS)
    first, second = sorted(rng.sample([0.5, 1, 1.5, 2, 2.5, 3], 2))
    flags = [rng.random() < 0.5 for _ in range(2)]
    parts = [value(f'n{k}', 'L', rng.randint(0, 9)) for k in range(3)]
    parts += [value(f'b{k}', BOOL, flag) for k, flag in enumerate(flags)]
    parts += [value('tally', 'L', 0, lower=0), flow('fill', SOURCE, this.tally, request=q(1, 'L/h'))]
    parts.append(
        event(
            'tick',
            after(q(first, 'h'), assign(this.n0, q(rng.randint(0, 9), 'L')), assign(this.b0, not flags[0])),
            after(q(second - first, 'h'), add(this.n1, q(rng.randint(1, 4), 'L'))),
        )
    )
    parts += [value(f'f{k}', 'L', formula(number(rng, k, 3) + q(0, 'L'))) for k in range(FORMULAS)]
    parts.append(
        status(rating('failed', condition(rng, FORMULAS)), rating('ok', condition(rng, 2)), rating('ok'))
    )
    b.entity('m', *parts)
    b.setup(start(named('m').tick))
    return b.finish()


PATHS = [*(f'm.f{k}' for k in range(FORMULAS)), 'm.n0', 'm.tally', 'm.status']


def asked(rng):
    """A random report: some paths in a random order, some times, and a lag on some of the paths."""
    paths = rng.sample(PATHS, rng.randint(3, 6))
    times = sorted(rng.sample([0, 0.5, 1, 1.5, 2, 2.5, 3, 3.5, 4], rng.randint(2, 5)))
    lags = {}
    for path in paths:
        if path != 'm.status' and rng.random() < 0.3:
            shortest = rng.choice([0, 0.5, 1])
            lags[path] = Lag(shortest, shortest + rng.choice([0, 0.5, 1]))
    return paths, times, lags


@pytest.mark.parametrize('seed', range(80))
def test_the_trail_of_a_value_is_its_trail_in_a_report_of_it_alone(seed):
    rng = random.Random(seed)
    program = model(rng)
    configuration = Configuration(Request(HORIZON))
    record = run(program, configuration)
    assert record.failure is None, record.failure
    for _ in range(REPORTS):
        paths, times, lags = asked(rng)
        together = report(record, program, configuration, paths, times, lags)
        for found in together.values:
            lag = {found.path: lags[found.path]} if found.path in lags else {}
            (alone,) = report(record, program, configuration, [found.path], times, lag).values
            assert found.values == alone.values, (seed, paths, found.path)
            assert found.trail == alone.trail, (seed, paths, times, lags, found.path)


def nested():
    """`mid` reads `a` before 2 h and `src` after; `outer` reads `mid` before 2 h and `other` after."""
    b = Builder(UNITS)
    b.entity(
        'm',
        value('src', 'L', 1),
        value('a', 'L', 2),
        value('other', 'L', 3),
        value('mid', 'L', formula(ifelse(t < q(2, 'h'), this.a, this.src))),
        value('outer', 'L', formula(ifelse(t < q(2, 'h'), this.mid, this.other))),
    )
    return b.finish()


@pytest.mark.parametrize('paths', [['m.outer'], ['m.mid', 'm.outer'], ['m.outer', 'm.mid']])
def test_a_source_that_the_value_between_read_only_at_another_time_is_not_exercised(paths):
    program = nested()
    configuration = Configuration(Request(4))
    found = report(run(program, configuration), program, configuration, paths, [1, 3])
    (outer,) = [each for each in found.values if each.path == 'm.outer']
    assert outer.values == (2, 3)
    exercised = {used.origin: used.exercised for used in outer.trail}
    assert exercised == {'m.a': True, 'm.mid': True, 'm.other': True, 'm.outer': True, 'm.src': False}
