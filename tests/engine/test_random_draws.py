"""Small random programs with draws, against the oracle (`tests/reference/`).

Each case has a few machines, each with a level, a count and a state, a distribution of its own, and
an event `work` that one of its triggers or the setup starts. An occurrence may draw a local, wait a
drawn or a fixed delay, and run stages that add draws to its level, set its state to a categorical
draw, switch on a categorical draw or on a draw of the forecast of the member `boss` with guards on
its count, branch on its level, and start the work of another machine. A trigger on the clock passes a
draw of its capture, which each firing makes again. Half the cases are sampled under their seed, the
rest median runs.

The oracle runs the same program in exact fractions and keys each draw as the engine does, by its
seed, its site and its owner. The levels, counts and states at each half hour, the times of the
starts and the firings, every value that a draw gave, and a failure with its time must agree.
"""

from __future__ import annotations

import random
from fractions import Fraction

import pytest

from napkin.engine import read, run
from napkin.program.build import (
    Builder,
    add,
    after,
    assign,
    case,
    categorical,
    dist_of,
    draw,
    event,
    if_,
    local,
    named,
    param,
    q,
    reset_after,
    start,
    switch,
    t,
    this,
    uniform,
    value,
    when,
)
from napkin.program.config import SAMPLED, Configuration, Limits, Request
from napkin.program.record import Key
from tests.reference.errors import NotCovered
from tests.reference.from_program import run_of, traced, value_at

UNITS = {'h': {'time': 1}, 'L': {'volume': 1}}
HORIZON = 6
TIMES = [Fraction(k, 2) for k in range(2 * HORIZON + 1)]


def _weights(rng, names):
    """Weights in quarters that add up to one (the oracle takes probabilities), some of them zero."""
    cuts = sorted(rng.randint(0, 4) for _ in range(len(names) - 1))
    parts = [b - a for a, b in zip([0, *cuts], [*cuts, 4])]
    return {name: part / 4 for name, part in zip(names, parts)}


def program(seed):
    """A random program (see the module), and the keys of the values to compare."""
    rng = random.Random(seed)
    b = Builder(UNITS)
    state = b.enum('enum[A, B, C]', 'A', 'B', 'C')
    count = rng.randint(1, 3)
    machines = [f'm{k}' for k in range(count)]
    boss = b.entity(
        'boss', value('forecast', dist_of(state), categorical(state, **_weights(rng, ('A', 'B', 'C'))))
    )
    for name in machines:
        other = named(rng.choice(machines))
        statements = []
        for _ in range(rng.randint(1, 3)):
            what = rng.random()
            low = rng.randint(0, 3)
            if what < 0.2:
                statements.append(add(this.level, draw(uniform(low, low + rng.randint(1, 3), 'L'))))
            elif what < 0.3:
                statements.append(add(this.level, draw(this.speeds)))
            elif what < 0.4:
                statements.append(add(this.level, local.amount))
            elif what < 0.5:
                statements.append(
                    assign(this.state, draw(categorical(state, **_weights(rng, ('A', 'B', 'C')))))
                )
            elif what < 0.75:
                selector = (
                    draw(categorical(state, **_weights(rng, ('A', 'B', 'C'))))
                    if rng.random() < 0.6
                    else draw(boss.forecast)
                )
                cases = [
                    case(state.A, add(this.count, 1), when=this.count < rng.randint(0, 3)),
                    case(state.B, add(this.count, 10), assign(this.state, state.B)),
                ]
                if rng.random() < 0.5:
                    cases.append(
                        case(state.C, add(this.level, q(1, 'L')), when=this.count >= rng.randint(0, 2))
                    )
                statements.append(switch(selector, *cases, orelse=(add(this.count, 100),)))
            elif what < 0.85:
                mark = q(rng.randint(0, 6), 'L')
                statements.append(
                    if_(this.level >= mark, [add(this.count, 1)], [add(this.level, draw(this.speeds))])
                )
            else:
                statements.append(start(other.work, draw(uniform(0, 2, 'L'))))
        delay = draw(uniform(0.5, 2, 'h')) if rng.random() < 0.5 else q(rng.choice((0, 0.5, 1)), 'h')
        parts = [param('amount', 'L')]
        if rng.random() < 0.5:
            parts.append(value('first', 'L', draw(uniform(0, 1, 'L'))))
            statements.append(add(this.level, local.first))
        parts.append(after(delay, *statements))
        triggers = []
        if rng.random() < 0.6:
            capture = value('extra', 'L', draw(uniform(0, rng.randint(1, 4), 'L')))
            reset = reset_after(q(rng.choice((1, 2)), 'h'))
            triggers.append(
                when(
                    t >= q(rng.choice((1, 2)), 'h'),
                    start(this.work, local.extra),
                    captures=(capture,),
                    reset=reset,
                )
            )
        low = rng.randint(1, 3)
        b.entity(
            name,
            value('level', 'L', rng.randint(0, 4)),
            value('count', '', 0),
            value('state', state, state.A),
            value('speeds', None, uniform(low, low + 2, 'L')),
            event('work', *parts, *triggers),
        )
    b.setup(*[start(named(name).work, q(rng.randint(0, 2), 'L')) for name in machines if rng.random() < 0.7])
    keys = [Key(name, (field,)) for name in machines for field in ('level', 'count', 'state')]
    mode = {'mode': SAMPLED, 'seed': seed} if rng.random() < 0.5 else {}
    configuration = Configuration(Request(HORIZON), limits=Limits(max_active=8, max_occurrences=40), **mode)
    return b.finish(), configuration, keys, [f'{name}.work' for name in machines]


def compare(seed):
    source, configuration, keys, events = program(seed)
    try:
        oracle, failed = run_of(source, configuration)
    except NotCovered:
        return
    record = run(source, configuration)
    if oracle is None:
        assert record.failure is not None and record.failure.t == 0, (seed, str(failed))
        return
    if failed is not None:
        assert record.failure is not None, (seed, str(failed))
        assert record.failure.t == pytest.approx(float(oracle.view.t)), (seed, str(failed), record.failure)
        horizon = oracle.view.t - Fraction(1, 10**9)
    else:
        assert record.failure is None, (seed, record.failure.detail('message'))
        horizon = Fraction(HORIZON)
    for name in events:
        for kind, part in (('start', name), ('fire', f'{name}.when[0]')):
            found = [entry.t for entry in record.entries(kind, part) if entry.t < horizon]
            expected = [float(at) for at, _ in traced(oracle, kind, part) if at < horizon]
            assert found == pytest.approx(expected), (seed, kind, part)
    # Every value that a draw of the engine gave, by its key: the oracle's.
    given = {key: value for key, value in oracle.draws}
    for entry in record.trace:
        if entry.kind == 'draw' and entry.t < horizon:
            expected = given[f'{entry.part}|{entry.owner}']
            found = entry.detail('value')
            if isinstance(found, str):
                assert found == expected, (seed, entry)
            else:
                assert found == pytest.approx(float(expected), rel=1e-9), (seed, entry)
    times = [time for time in TIMES if time < horizon]
    for key in keys:
        found = read(record, source, [key], [float(time) for time in times])[0].values
        for time, number in zip(times, found):
            expected = value_at(oracle, source, key, time)
            if isinstance(expected, str):
                assert number == expected, (seed, str(key), float(time))
            else:
                assert number == pytest.approx(float(expected), rel=1e-9, abs=1e-9), (
                    seed,
                    str(key),
                    float(time),
                )


@pytest.mark.parametrize('seed', range(200))
def test_a_small_random_program_with_draws_runs_as_the_oracle_does(seed):
    compare(seed)


@pytest.mark.deep
@pytest.mark.parametrize('seed', range(200, 1200))
def test_more_random_programs_with_draws_run_as_the_oracle_does(seed):
    compare(seed)
