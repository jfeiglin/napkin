"""The answer that a declared solver publishes (`declared.published`; re-audit row 06): each change
of the answer after the solve, the polish onto the bounds and rows that it holds and the clip to its
bounds, is a candidate that takes the place of the solver's checked answer only if it passes the
solve's end checks and is no worse on any rank (`solve.Answer.admits`).

Two rules, on the random solver programs of `test_random_solvers` (one to three tanks, flows of
which a provider's solver names some, limits, orders and objectives of shortfalls and rates):

1. at every solve, the published answer is no worse than the solver's on any rank: no written
   objective higher, no claim served a smaller fraction, and every row and bound held, each to the
   library's tolerance of the size of its terms, measured here from the problem's arrays alone. At a
   size of one litre, and of 1e-7 litres, where every rate is below the polish's tolerance of one
   canonical unit (`declared.NEAR`);
2. the same model written in L, mL and kL gives the same physical values.

Then the audit's two cases and their variants at smaller requests, worked by hand, and the same rule
in local sharing, whose snaps of roundoff are candidates too (`selection._kept`).
"""

from __future__ import annotations

from fractions import Fraction

import numpy as np
import pytest

from napkin.engine import read, run
from napkin.engine.timeline import declared
from napkin.program.build import (
    SINK,
    SOURCE,
    Builder,
    endpoint,
    flow,
    fmax,
    formula,
    given,
    local,
    minimize,
    named,
    q,
    solve_for,
    solver,
    this,
    value,
)
from napkin.program.config import Configuration, Request
from napkin.program.record import Key
from tests.engine.test_random_solvers import HORIZON, SCALES, TIMES, UNITS, program

KEPT = 1e-6  # an objective, a served fraction, a row or a bound is held to this of the size of its terms


def solves(monkeypatch, source):
    """The run of `source` to the horizon, and each of its solves as (arrays, the solver's answer,
    its levels, the published answer)."""
    found = []
    publish = declared.published

    def spy(arrays, answer):
        made = publish(arrays, answer)
        found.append((arrays, np.array(answer.x), np.asarray(answer.levels, dtype=float), np.array(made)))
        return made

    monkeypatch.setattr(declared, 'published', spy)
    return run(source, Configuration(Request(HORIZON))), found


def no_worse(arrays, raw, levels, made):
    """The ranks on which `made` is worse than `raw`, the solver's answer, beyond the tolerance: each
    as a short text."""
    worse = []
    scale = arrays.scale
    for k, (columns, values) in enumerate(arrays.objectives):
        size = np.abs(values) @ (np.abs(raw[columns]) + np.abs(made[columns]))
        if values @ made[columns] > values @ raw[columns] + KEPT * size + 1e-12 * (
            np.abs(values) @ scale[columns]
        ):
            worse.append(f'objective {k + 1}: {values @ made[columns]!r} after {values @ raw[columns]!r}')
    if len(levels):
        served = [np.minimum((arrays.F @ x) / arrays.request, 1.0) for x in (raw, made)]
        for i in np.flatnonzero(served[1] < np.minimum(served[0], levels) - KEPT * (1 + served[0])).tolist():
            worse.append(f'claim {i}: served {served[1][i]!r} after {served[0][i]!r}')
    if arrays.A.shape[0]:
        value = arrays.A @ made
        size = abs(arrays.A) @ (scale + np.abs(made))
        missed = np.maximum(arrays.row_lower - value, value - arrays.row_upper) > KEPT * size
        worse += [f'row {arrays.row_keys[i]!r}' for i in np.flatnonzero(missed).tolist()]
    outside = np.maximum(arrays.lower - made, made - arrays.upper) > KEPT * (scale + np.abs(made))
    worse += [f'unknown {arrays.keys[j]!r}' for j in np.flatnonzero(outside).tolist()]
    return worse


def published_never_worse(monkeypatch, seed, size):
    source, _ = program(seed, size=size)
    _, found = solves(monkeypatch, source)
    for arrays, raw, levels, made in found:
        assert not no_worse(arrays, raw, levels, made), (seed, size, no_worse(arrays, raw, levels, made))


@pytest.mark.parametrize('seed', range(40))
@pytest.mark.parametrize('size', [1, Fraction(1, 10**7)], ids=['litres', 'tiny'])
def test_the_published_answer_is_never_worse_than_the_solvers_on_any_rank(monkeypatch, seed, size):
    published_never_worse(monkeypatch, seed, size)


@pytest.mark.deep
@pytest.mark.parametrize('seed', range(40, 600))
@pytest.mark.parametrize('size', [1, Fraction(1, 10**7)], ids=['litres', 'tiny'])
def test_more_published_answers_are_never_worse_than_the_solvers(monkeypatch, seed, size):
    published_never_worse(monkeypatch, seed, size)


def physical(seed, unit):
    """The values of a random program written in `unit` at the times of `test_random_solvers`, in
    litres and hours, and how its run ended."""
    source, keys = program(seed, unit)
    record = run(source, Configuration(Request(HORIZON)))
    horizon = record.failure.t if record.failure is not None else HORIZON
    times = [float(time) for time in TIMES if time < horizon]
    factor = float(SCALES[unit])
    values = [tuple(v * factor for v in read(record, source, [key], times)[0].values) for key in keys]
    return values, None if record.failure is None else round(record.failure.t, 9)


def same_in_every_unit(seed):
    litres, ended = physical(seed, 'L')
    for unit in ('mL', 'kL'):
        found, other = physical(seed, unit)
        assert other == ended, (seed, unit, other, ended)
        for a, b in zip(found, litres):
            assert a == pytest.approx(b, rel=1e-9, abs=1e-12), (seed, unit)


@pytest.mark.parametrize('seed', range(40))
def test_the_same_model_in_litres_millilitres_and_kilolitres_gives_the_same_answer(seed):
    same_in_every_unit(seed)


@pytest.mark.deep
@pytest.mark.parametrize('seed', range(40, 400))
def test_more_models_give_the_same_answer_in_every_unit_of_volume(seed):
    same_in_every_unit(seed)


# ---- the audit's cases and their variants, worked by hand --------------------------------------------


def split(want, unit, claim, objective):
    """A tank that two pipes from outside fill, which a solver names, with a request of `want` L/h
    at its inflow (`claim`) or as the normalized loss max(0, want - one - two) / want that it
    minimizes first (`objective`), written in `unit`: the rates of the pipes, in L/h, and the loss."""
    factor = Fraction(want) / SCALES[unit]
    rate = q(factor, f'{unit}/h')
    b = Builder(UNITS)
    settings = {'inflow': endpoint(request=rate)} if claim else {}
    tank = b.entity('tank', value('water', unit, 0, lower=0, **settings))
    pipes = b.entity('pipes', flow('one', SOURCE, tank.water), flow('two', SOURCE, tank.water))
    loss = fmax(q(0, f'{unit}/h'), rate - local.one.actual_rate - local.two.actual_rate) / rate
    parts = [given('one', pipes.one), given('two', pipes.two)]
    parts += [solve_for(local.one.actual_rate), solve_for(local.two.actual_rate)]
    if objective:
        parts.append(minimize(loss))
    shown = (
        fmax(q(0, f'{unit}/h'), rate - named('pipes').one.actual_rate - named('pipes').two.actual_rate) / rate
    )
    b.entity('provider', solver('plan', *parts), value('loss', '', formula(shown)))
    source = b.finish()
    record = run(source, Configuration(Request(1)))
    assert record.failure is None, record.failure
    keys = [
        Key('pipes', ('one', 'actual_rate')),
        Key('pipes', ('two', 'actual_rate')),
        Key('provider', ('loss',)),
    ]
    one, two, found = (reading.values[0] for reading in read(record, source, keys, [0.5]))
    return one * float(SCALES[unit]), two * float(SCALES[unit]), found


@pytest.mark.parametrize('unit', ['L', 'mL', 'kL'])
@pytest.mark.parametrize('want', [5e-7, 5e-8, 5e-9])
@pytest.mark.parametrize(
    'claim, objective', [(True, False), (False, True), (True, True)], ids=['claim', 'loss', 'both']
)
def test_a_small_request_split_between_two_pipes_is_met_as_the_solver_meets_it(unit, want, claim, objective):
    """Re-audit row 06: the solver meets a request of 5e-7 L/h through two pipes, 2.5e-7 L/h each
    (the distance step splits what neither pipe asks for equally), and the polish once put both on
    their lower bound, which they are within 1e-6 L/h of: the tank's request unserved, and a
    normalized loss of 0 published as 1. Each change is now kept only where it serves the claim and
    the objective as the solver does, in any unit of volume and at smaller requests too."""
    one, two, loss = split(want, unit, claim, objective)
    assert one == pytest.approx(want / 2, rel=1e-9)
    assert two == pytest.approx(want / 2, rel=1e-9)
    assert loss == pytest.approx(0, abs=1e-9)


@pytest.mark.parametrize('small', [1e-13, 5e-13])
def test_local_sharing_keeps_a_small_delivery_in_a_large_part(small):
    """A [0, 0] junction whose outflow passes 1 L/h shares it proportionally between a delivery that
    asks 1 L/h and one that asks 1e-13 or 5e-13 L/h. By hand: each is served the fraction
    1 / (1 + small), so the small one gets small / (1 + small), which local sharing once snapped to
    zero as the roundoff of a part of 1 L/h."""
    b = Builder(UNITS)
    b.entity(
        'junction',
        value('water', 'L', 0, lower=0, upper=0, outflow=endpoint(capacity=q(1, 'L/h'))),
        flow('feed', SOURCE, this.water, capacity=q(2, 'L/h')),
        flow('big', this.water, SINK, request=q(1, 'L/h')),
        flow('small', this.water, SINK, request=q(small, 'L/h')),
    )
    source = b.finish()
    record = run(source, Configuration(Request(1)))
    assert record.failure is None, record.failure
    keys = [Key('junction', (name, 'actual_rate')) for name in ('big', 'small')]
    big, found = (reading.values[0] for reading in read(record, source, keys, [0.5]))
    assert big == pytest.approx(1 / (1 + small), rel=1e-12)
    assert found == pytest.approx(small / (1 + small), rel=1e-3, abs=0)
